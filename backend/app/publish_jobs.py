"""Publish one bounded batch of pending local jobs."""

import argparse

from app import models  # noqa: F401
from app.db import SessionLocal
from app.providers.local_sqs import LocalSqsSender
from app.services.outbox_publisher import publish_pending


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish pending jobs to local Floci.")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    count = publish_pending(SessionLocal, LocalSqsSender(args.endpoint), args.limit)
    print(f"published={count}")


if __name__ == "__main__":
    main()
