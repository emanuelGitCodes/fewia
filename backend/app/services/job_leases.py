"""Claim, renew, and complete job leases with atomic SQL updates."""

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import and_, case, or_, update
from sqlalchemy.orm import Session

from app.job_models import Job

_LEASE_MAX = 3600
_ATTEMPTS_MAX = 100
_EXHAUSTED = "attempts_exhausted"


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


def claim_job(
    session: Session,
    job_id: str,
    *,
    now: datetime,
    lease_seconds: int = 60,
    max_attempts: int = 3,
) -> str | None:
    """Return a fresh lease token, or None when the job is not claimable."""
    now = _aware_utc(now)
    lease_seconds = _bound_int(lease_seconds, "lease_seconds", _LEASE_MAX)
    max_attempts = _bound_int(max_attempts, "max_attempts", _ATTEMPTS_MAX)
    eligible = or_(
        Job.status == "queued",
        and_(Job.status == "running", Job.lease_expires_at <= now),
    )
    token = token_urlsafe(32)
    claimed = session.scalar(
        update(Job)
        .where(Job.id == job_id, eligible, Job.attempts < max_attempts)
        .values(
            status="running",
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            attempts=Job.attempts + 1,
        )
        .execution_options(synchronize_session=False)
        .returning(Job.lease_token)
    )
    if claimed is not None:
        return claimed
    session.execute(
        update(Job)
        .where(Job.id == job_id, eligible, Job.attempts >= max_attempts)
        .values(
            status="failed",
            error_code=_EXHAUSTED,
            lease_token=None,
            lease_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    return None


def renew_lease(
    session: Session,
    job_id: str,
    token: str,
    *,
    now: datetime,
    lease_seconds: int = 60,
) -> bool:
    """Extend an unexpired running lease when the token matches."""
    now = _aware_utc(now)
    lease_seconds = _bound_int(lease_seconds, "lease_seconds", _LEASE_MAX)
    candidate_expiry = now + timedelta(seconds=lease_seconds)
    renewed = session.scalar(
        update(Job)
        .where(
            Job.id == job_id,
            Job.lease_token == token,
            Job.status == "running",
            Job.lease_expires_at > now,
        )
        .values(
            lease_expires_at=case(
                (Job.lease_expires_at >= candidate_expiry, Job.lease_expires_at),
                else_=candidate_expiry,
            )
        )
        .execution_options(synchronize_session=False)
        .returning(Job.id)
    )
    return renewed is not None


def finish_job(
    session: Session,
    job_id: str,
    token: str,
    *,
    now: datetime,
    result: dict[str, object] | None = None,
    error_code: str | None = None,
) -> bool:
    """Mark a held job terminal and clear its lease fields."""
    now = _aware_utc(now)
    values: dict[str, object] = {
        "status": "failed" if error_code is not None else "succeeded",
        "error_code": error_code,
        "lease_token": None,
        "lease_expires_at": None,
    }
    if result is not None:
        values["result"] = result
    finalized = session.scalar(
        update(Job)
        .where(
            Job.id == job_id,
            Job.lease_token == token,
            Job.status == "running",
            Job.lease_expires_at > now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
        .returning(Job.id)
    )
    return finalized is not None
