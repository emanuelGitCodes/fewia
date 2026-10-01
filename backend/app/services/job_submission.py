"""Create durable jobs and commit accepted submissions."""

import json
from collections.abc import Callable
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.job_models import Job, JobOutbox


class IdempotencyConflict(ValueError):
    """The request key already identifies different content."""


class JobConflict(Exception):
    """The request key identifies different caller fields."""


class JobUnavailable(Exception):
    """The job cannot be stored."""


class JobInputInvalid(Exception):
    """The job request contains invalid parameters."""


def reuse_job(
    session: Session,
    user_id: int,
    kind: Literal["sync", "agent"],
    request_key: str,
    matches: Callable[[dict[str, object]], bool],
) -> Job | None:
    job = find_job(session, user_id, kind, request_key)
    if job is None:
        return None
    if not matches(job.payload):
        raise JobConflict
    session.commit()
    return job


def submit_job(
    session: Session,
    user_id: int,
    kind: Literal["sync", "agent"],
    request_key: str,
    payload: dict[str, object],
    matches: Callable[[dict[str, object]], bool],
) -> Job:
    try:
        job, _created = create_job(session, user_id, kind, request_key, payload)
    except (IdempotencyConflict, IntegrityError) as exc:
        winner = find_job(session, user_id, kind, request_key)
        if winner is not None and matches(winner.payload):
            job = winner
        elif isinstance(exc, IntegrityError) and winner is None:
            raise JobUnavailable from None
        else:
            raise JobConflict from None
    except ValueError:
        raise JobInputInvalid from None
    session.commit()
    return job


def _validate_keys(value: object) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for child in value.values():
            _validate_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_keys(child)


def _canonical(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    _validate_keys(payload)
    return encoded


def find_job(
    session: Session,
    user_id: int,
    kind: Literal["sync", "agent"],
    request_key: str,
) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.user_id == user_id, Job.kind == kind, Job.request_key == request_key
        )
    )


def create_job(
    session: Session,
    user_id: int,
    kind: Literal["sync", "agent"],
    request_key: str,
    payload: dict[str, object],
) -> tuple[Job, bool]:
    """Flush one job and outbox, or return an identical existing request."""
    if kind not in {"sync", "agent"}:
        raise ValueError("kind must be sync or agent")
    if (
        not isinstance(request_key, str)
        or not request_key.strip()
        or len(request_key) > 128
    ):
        raise ValueError("request_key must contain 1 to 128 nonblank characters")
    canonical = _canonical(payload)
    existing = find_job(session, user_id, kind, request_key)
    if existing is None:
        try:
            with session.begin_nested():
                job = Job(
                    user_id=user_id,
                    kind=kind,
                    request_key=request_key,
                    payload=json.loads(canonical),
                )
                session.add(job)
                session.flush()
                session.add(JobOutbox(job_id=job.id))
                session.flush()
            return job, True
        except IntegrityError:
            existing = find_job(session, user_id, kind, request_key)
            if existing is None:
                raise
    if _canonical(existing.payload) != canonical:
        raise IdempotencyConflict("request_key already identifies different content")
    return existing, False
