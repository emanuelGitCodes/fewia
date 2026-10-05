import argparse
import json
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import FrameType
from typing import NoReturn, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.agent.provider import LLMProvider
from app.db import SessionLocal
from app.job_models import Job
from app.provider_runtime import build_bedrock, build_plaid
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    load_provider_settings,
)
from app.providers.job_transport import build_job_queue, build_job_sender
from app.providers.job_transport_settings import load_job_transport
from app.services.agent_jobs import make_agent_handler
from app.services.chat_job import ChatJobInput
from app.services.job_consumer import process_one
from app.services.job_delivery import JobHandler, JobQueue
from app.services.job_recovery import recover_jobs
from app.services.outbox_publisher import JobSender, PublicationError, publish_pending
from app.services.plan_job import PlanJobInput
from app.services.sync_job import SyncJobInput, make_sync_handler

_OUTCOMES = (
    "empty invalid busy retry lease_lost handler_failed succeeded terminal exhausted"
).split()
_BACKOFF_SECONDS = 1
_BEDROCK_UNAVAILABLE = "bedrock_unavailable"
QueueFactory = Callable[[str, str], JobQueue]
SenderFactory = Callable[[str], JobSender]
Processor = Callable[[sessionmaker[Session], JobQueue, str, JobHandler], str]
NowFn = Callable[[], datetime]
WaitFn = Callable[[float], object]


def job_replay_safe(job: Job) -> bool:
    payload = job.payload
    if not isinstance(payload, dict):
        return False
    operation = payload.get("operation")
    model: type[PlanJobInput | ChatJobInput | SyncJobInput] | None
    if job.kind == "agent" and operation is None:
        model = PlanJobInput
    elif job.kind == "agent" and operation == "chat":
        model = ChatJobInput
    elif job.kind == "sync" and operation == "plaid_sync":
        model = SyncJobInput
    else:
        model = None
    if model is None:
        return False
    try:
        model.model_validate(payload)
    except ValidationError:
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _bedrock_provider(settings: GroceryProviderSettings) -> LLMProvider | None:
    if settings.bedrock_model_id is None:
        return None
    provider: LLMProvider | None = None
    try:
        provider = build_bedrock(settings)
    except ProviderConfigurationError:
        pass
    if provider is None:
        print(json.dumps({"status": _BEDROCK_UNAVAILABLE}), file=sys.stderr)
        return None
    return provider


def _default_handler(factory: sessionmaker[Session], kind: str) -> JobHandler:
    settings = load_provider_settings()
    if kind == "sync":
        return make_sync_handler(factory, build_plaid(settings))
    return make_agent_handler(factory, _bedrock_provider(settings))


def run_publisher(
    factory: sessionmaker[Session],
    sender: JobSender,
    stop: threading.Event,
    *,
    idle_seconds: float = 0.2,
) -> None:
    while not stop.is_set():
        try:
            published = publish_pending(factory, sender, limit=20)
        except PublicationError:
            stop.wait(_BACKOFF_SECONDS)
            continue
        if published == 0:
            stop.wait(idle_seconds)


def run_worker(
    factory: sessionmaker[Session],
    queue: JobQueue,
    sender: JobSender,
    handler: JobHandler,
    stop: threading.Event,
    *,
    processor: Processor | None = None,
    now: NowFn | None = None,
    wait: WaitFn | None = None,
    counts: dict[str, int] | None = None,
    kind: str = "agent",
) -> dict[str, int]:
    selected_processor = process_one if processor is None else processor
    selected_now = _utc_now if now is None else now
    selected_wait: WaitFn = stop.wait if wait is None else wait
    if counts is None:
        counts = {outcome: 0 for outcome in _OUTCOMES}
    recorded: list[BaseException] = []

    def run_outbox_thread() -> None:
        try:
            run_publisher(factory, sender, stop)
        except Exception as exc:  # noqa: BLE001
            recorded.append(exc)
            stop.set()

    thread = threading.Thread(
        target=run_outbox_thread,
        name="outbox-publisher",
        daemon=True,
    )
    thread.start()
    try:
        while not stop.is_set():
            recover_jobs(factory, job_replay_safe, now=selected_now())
            if stop.is_set():
                break
            outcome = selected_processor(factory, queue, kind, handler)
            if outcome not in counts:
                raise RuntimeError("unsupported worker outcome")
            counts[outcome] += 1
            if outcome == "empty":
                selected_wait(_BACKOFF_SECONDS)
    finally:
        stop.set()
        thread.join(5)
    if recorded:
        raise RuntimeError("outbox publisher failed")
    return counts


def _write_result(status: str, counts: dict[str, int]) -> None:
    print(json.dumps({"status": status, "counts": counts}, sort_keys=True))


class _WorkerParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Worker arguments are invalid")


def main(
    argv: Sequence[str] | None = None,
    *,
    factory: sessionmaker[Session] | None = None,
    consumer_factory: QueueFactory | None = None,
    sender_factory: SenderFactory | None = None,
    processor: Processor | None = None,
    handler: JobHandler | None = None,
    stop: threading.Event | None = None,
    now: NowFn | None = None,
    wait: WaitFn | None = None,
) -> int:
    parser = _WorkerParser(description="Process jobs.")
    parser.add_argument("--transport", choices=("local", "aws"))
    parser.add_argument("--endpoint")
    parser.add_argument("--kind", choices=("agent", "sync"), default="agent")
    counts = {outcome: 0 for outcome in _OUTCOMES}
    try:
        args = parser.parse_args(argv)
        transport = load_job_transport(mode=args.transport, endpoint=args.endpoint)
        if transport.mode == "aws" and (
            consumer_factory is not None or sender_factory is not None
        ):
            raise ValueError("Legacy factories require local transport")
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception:  # noqa: BLE001
        _write_result("worker_failed", counts)
        return 1
    selected_factory = SessionLocal if factory is None else factory
    selected_stop = threading.Event() if stop is None else stop
    signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {signum: signal.getsignal(signum) for signum in signals}

    def request_stop(signum: int, frame: FrameType | None) -> None:
        selected_stop.set()

    status = "stopped"
    exit_code = 0
    try:
        for signum in previous_handlers:
            signal.signal(signum, request_stop)
        selected_handler = (
            handler
            if handler is not None
            else _default_handler(selected_factory, args.kind)
        )
        queue = (
            build_job_queue(transport, args.kind)
            if consumer_factory is None
            else consumer_factory(cast(str, transport.endpoint), args.kind)
        )
        sender = (
            build_job_sender(transport)
            if sender_factory is None
            else sender_factory(cast(str, transport.endpoint))
        )
        run_worker(
            selected_factory,
            queue,
            sender,
            selected_handler,
            selected_stop,
            processor=processor,
            now=now,
            wait=wait,
            counts=counts,
            kind=args.kind,
        )
    except KeyboardInterrupt:
        status = "stopped"
    except Exception:  # noqa: BLE001
        status = "worker_failed"
        exit_code = 1
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
    _write_result(status, counts)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
