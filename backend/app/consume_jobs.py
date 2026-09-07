import argparse
import json
import signal
from collections.abc import Callable, Sequence
from types import FrameType

from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.db import SessionLocal
from app.providers.local_sqs_consumer import LocalSqsConsumer
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


def main(
    argv: Sequence[str] | None = None,
    *,
    factory: sessionmaker[Session] | None = None,
    consumer_factory: QueueFactory | None = None,
    processor: Processor | None = None,
    handler: JobHandler | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Process bounded local agent jobs.")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--max-messages", type=_bounded_count, default=20)
    args = parser.parse_args(argv)
    counts = {outcome: 0 for outcome in _OUTCOMES}
    selected_factory = SessionLocal if factory is None else factory
    consumer = LocalSqsConsumer if consumer_factory is None else consumer_factory
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
        queue = consumer(args.endpoint, "agent")
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
