import argparse
import json
import signal
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import FrameType

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.db import SessionLocal
from app.job_models import Job
from app.providers.local_sqs import LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer
from app.services.job_consumer import process_one
from app.services.job_delivery import JobHandler, JobQueue
from app.services.job_recovery import recover_jobs
from app.services.outbox_publisher import JobSender, PublicationError, publish_pending
from app.services.plan_job import PlanJobInput, plan_job

_OUTCOMES = (
    "empty invalid busy retry lease_lost handler_failed succeeded terminal exhausted"
).split()
_BACKOFF_SECONDS = 1
QueueFactory = Callable[[str, str], JobQueue]
SenderFactory = Callable[[str], JobSender]
Processor = Callable[[sessionmaker[Session], JobQueue, str, JobHandler], str]
NowFn = Callable[[], datetime]
WaitFn = Callable[[float], object]


def agent_plan_replay_safe(job: Job) -> bool:
    if job.kind != "agent":
        return False
    try:
        PlanJobInput.model_validate(job.payload)
    except ValidationError:
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
) -> dict[str, int]:
    selected_processor = process_one if processor is None else processor
    selected_now = _utc_now if now is None else now
    selected_wait: WaitFn = stop.wait if wait is None else wait
    if counts is None:
        counts = {outcome: 0 for outcome in _OUTCOMES}
    while not stop.is_set():
        recover_jobs(factory, agent_plan_replay_safe, now=selected_now())
        if stop.is_set():
            break
        try:
            publish_pending(factory, sender, limit=1)
        except PublicationError:
            selected_wait(_BACKOFF_SECONDS)
            continue
        if stop.is_set():
            break
        outcome = selected_processor(factory, queue, "agent", handler)
        if outcome not in counts:
            raise RuntimeError("unsupported worker outcome")
        counts[outcome] += 1
        if outcome == "empty":
            selected_wait(_BACKOFF_SECONDS)
    return counts


def _write_result(status: str, counts: dict[str, int]) -> None:
    print(json.dumps({"status": status, "counts": counts}, sort_keys=True))


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
    parser = argparse.ArgumentParser(description="Process local agent jobs.")
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args(argv)
    counts = {outcome: 0 for outcome in _OUTCOMES}
    selected_factory = SessionLocal if factory is None else factory
    selected_handler = plan_job if handler is None else handler
    selected_stop = threading.Event() if stop is None else stop
    selected_consumer = (
        LocalSqsConsumer if consumer_factory is None else consumer_factory
    )
    selected_sender = LocalSqsSender if sender_factory is None else sender_factory
    signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {signum: signal.getsignal(signum) for signum in signals}

    def request_stop(signum: int, frame: FrameType | None) -> None:
        selected_stop.set()

    status = "stopped"
    exit_code = 0
    try:
        for signum in previous_handlers:
            signal.signal(signum, request_stop)
        run_worker(
            selected_factory,
            selected_consumer(args.endpoint, "agent"),
            selected_sender(args.endpoint),
            selected_handler,
            selected_stop,
            processor=processor,
            now=now,
            wait=wait,
            counts=counts,
        )
    except KeyboardInterrupt:
        status = "stopped"
    except Exception:
        status = "worker_failed"
        exit_code = 1
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
    _write_result(status, counts)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
