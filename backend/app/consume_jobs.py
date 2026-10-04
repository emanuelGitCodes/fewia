import argparse
import json
import signal
from collections.abc import Callable, Sequence
from types import FrameType
from typing import NoReturn, cast

from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.db import SessionLocal
from app.providers.job_transport import build_job_queue
from app.providers.job_transport_settings import load_job_transport
from app.services.job_consumer import process_one
from app.services.job_delivery import JobHandler, JobQueue
from app.services.plan_job import plan_job

_OUTCOMES = (
    "empty invalid busy retry lease_lost handler_failed succeeded terminal exhausted"
).split()
_BOUND_ERROR = "max-messages MUST be an integer from 1 to 10000"
QueueFactory = Callable[[str, str], JobQueue]
Processor = Callable[[sessionmaker[Session], JobQueue, str, JobHandler], str]


def _bounded_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(_BOUND_ERROR) from error
    if count < 1 or count > 10_000:
        raise argparse.ArgumentTypeError(_BOUND_ERROR)
    return count


def _write_result(status: str, counts: dict[str, int]) -> None:
    print(json.dumps({"status": status, "counts": counts}, sort_keys=True))


class _ConsumerParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Consumer arguments are invalid")


def main(
    argv: Sequence[str] | None = None,
    *,
    factory: sessionmaker[Session] | None = None,
    consumer_factory: QueueFactory | None = None,
    processor: Processor | None = None,
    handler: JobHandler | None = None,
) -> int:
    parser = _ConsumerParser(description="Process bounded agent jobs.")
    parser.add_argument("--transport", choices=("local", "aws"))
    parser.add_argument("--endpoint")
    parser.add_argument("--max-messages", type=_bounded_count, default=20)
    counts = {outcome: 0 for outcome in _OUTCOMES}
    try:
        args = parser.parse_args(argv)
        transport = load_job_transport(mode=args.transport, endpoint=args.endpoint)
        if transport.mode == "aws" and consumer_factory is not None:
            raise ValueError("Legacy factories require local transport")
    except SystemExit as exc:
        return int(exc.code or 0)
    except KeyboardInterrupt:
        _write_result("stopped", counts)
        return 0
    except Exception:  # noqa: BLE001
        _write_result("worker_failed", counts)
        return 1
    selected_factory = SessionLocal if factory is None else factory
    selected_processor = process_one if processor is None else processor
    selected_handler = plan_job if handler is None else handler
    stop_requested = False
    signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {signum: signal.getsignal(signum) for signum in signals}

    def request_stop(signum: int, frame: FrameType | None) -> None:
        nonlocal stop_requested
        stop_requested = True

    status = "max_messages"
    exit_code = 0
    try:
        for signum in previous_handlers:
            signal.signal(signum, request_stop)
        queue = (
            build_job_queue(transport, "agent")
            if consumer_factory is None
            else consumer_factory(cast(str, transport.endpoint), "agent")
        )
        for _ in range(args.max_messages):
            if stop_requested:
                status = "stopped"
                break
            outcome = selected_processor(
                selected_factory, queue, "agent", selected_handler
            )
            if outcome not in counts:
                raise RuntimeError("unsupported worker outcome")
            counts[outcome] += 1
            if outcome == "empty":
                status = "empty"
                break
        if stop_requested:
            status = "stopped"
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
