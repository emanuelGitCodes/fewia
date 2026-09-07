"""Recover durable jobs without replaying unsafe provider work."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.job_models import Job, JobOutbox

_BATCH_MAX = 100
_ATTEMPTS_MAX = 100
_MIN_AGE_MAX = 86_400
_EXHAUSTED = "attempts_exhausted"
_RECOVERY_REQUIRED = "recovery_required"


def _aware_utc(now: datetime) -> datetime:
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.tzinfo.utcoffset(now) is None
    ):
        raise ValueError("now must be a timezone-aware datetime")
    return now.astimezone(UTC)


def _bound_int(value: object, name: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def recover_jobs(
    factory: sessionmaker[Session],
    replay_safe: Callable[[Job], bool],
    *,
    now: datetime,
    limit: int = 20,
    max_attempts: int = 3,
    min_age_seconds: int = 300,
) -> int:
    """Recover bounded, stale jobs in one transaction."""
    if not callable(replay_safe):
        raise TypeError("replay_safe must be callable")
    now = _aware_utc(now)
    limit = _bound_int(limit, "limit", _BATCH_MAX)
    max_attempts = _bound_int(max_attempts, "max_attempts", _ATTEMPTS_MAX)
    min_age_seconds = _bound_int(min_age_seconds, "min_age_seconds", _MIN_AGE_MAX)
    age_boundary = now - timedelta(seconds=min_age_seconds)
    eligible = or_(
        and_(Job.status == "running", Job.lease_expires_at <= now),
        and_(Job.status == "queued", JobOutbox.published_at <= age_boundary),
    )
    query = (
        select(Job, JobOutbox)
        .join(JobOutbox, JobOutbox.job_id == Job.id)
        .where(eligible, JobOutbox.published_at.is_not(None))
        .order_by(Job.created_at, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    with factory.begin() as session:
        rows = session.execute(query).tuples().all()
        for job, outbox in rows:
            if job.attempts >= max_attempts:
                job.status = "failed"
                job.error_code = _EXHAUSTED
                job.lease_token = None
                job.lease_expires_at = None
                continue
            if not replay_safe(job):
                job.status = "failed"
                job.error_code = _RECOVERY_REQUIRED
                job.lease_token = None
                job.lease_expires_at = None
                continue
            job.status = "queued"
            job.lease_token = None
            job.lease_expires_at = None
            outbox.published_at = None
        return len(rows)
