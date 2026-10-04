"""Publish one bounded batch of pending jobs."""

import argparse
import json
from collections.abc import Sequence
from typing import NoReturn

from app import models  # noqa: F401
from app.db import SessionLocal
from app.providers.job_transport import build_job_sender
from app.providers.job_transport_settings import load_job_transport
from app.services.outbox_publisher import publish_pending


class _PublisherParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Publisher arguments are invalid")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _PublisherParser(description="Publish pending jobs.")
    parser.add_argument("--transport", choices=("local", "aws"))
    parser.add_argument("--endpoint")
    parser.add_argument("--limit", type=int, default=20)
    try:
        args = parser.parse_args(argv)
        if not 1 <= args.limit <= 100:
            raise ValueError("limit MUST be an integer from 1 to 100")
        transport = load_job_transport(mode=args.transport, endpoint=args.endpoint)
        count = publish_pending(SessionLocal, build_job_sender(transport), args.limit)
    except SystemExit as exc:
        return int(exc.code or 0)
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted"}))
        return 130
    except Exception:  # noqa: BLE001
        print(json.dumps({"status": "publish_failed"}))
        return 1
    print(f"published={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
