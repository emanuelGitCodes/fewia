"""Publish committed outbox records with at-least-once delivery."""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.job_models import Job, JobOutbox


class JobSender(Protocol):
    """Send with bounded network timeouts and no payload logging."""

    def send(self, kind: str, job_id: str) -> None: ...


class PublicationError(RuntimeError):
    def __init__(self, published: int, failed: int) -> None:
        self.published = published
        self.failed = failed
        super().__init__(f"published={published} failed={failed}")


def publish_pending(
    factory: sessionmaker[Session], sender: JobSender, limit: int = 20
) -> int:
    """Commit each publication marker only after its send succeeds."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    published = 0
    failed_ids: set[str] = set()
    for _ in range(limit):
        with factory.begin() as session:
            row = session.execute(
                select(JobOutbox, Job.kind)
                .join(Job, Job.id == JobOutbox.job_id)
                .where(JobOutbox.published_at.is_(None))
                .where(JobOutbox.id.not_in(failed_ids))
                .order_by(JobOutbox.created_at, JobOutbox.id)
                .with_for_update(skip_locked=True, of=JobOutbox)
                .limit(1)
            ).first()
            if row is None:
                break
            outbox, kind = row
            try:
                sender.send(kind, outbox.job_id)
            except Exception:  # noqa: BLE001
                failed_ids.add(outbox.id)
                continue
            outbox.published_at = datetime.now(UTC)
        published += 1
    if failed_ids:
        raise PublicationError(published, len(failed_ids))
    return published
