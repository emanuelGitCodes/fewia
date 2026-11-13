"""Create durable jobs and commit accepted submissions."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.plan_revision import PlanSnapshot
from app.job_models import Job, JobOutbox
from app.plan_models import PlanRevision
from app.services.chat_job import ChatJobInput
from app.services.security_admission import (
    AdmissionLimitError,
    database_utc_now,
    require_active_owner,
    reserve_action,
)

_NEW_ADMISSION_LOCK = 72419638715482901


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
    *,
    request_namespace: str | None = None,
) -> Job | None:
    with session.no_autoflush:
        job = find_job(
            session, user_id, kind, request_key, request_namespace=request_namespace
        )
        if job is None:
            return None
        require_active_owner(session, user_id)
        job = find_job(
            session, user_id, kind, request_key, request_namespace=request_namespace
        )
        if job is None:
            session.rollback()
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
        _validate_request(kind, request_key, payload)
    except (TypeError, ValueError):
        raise JobInputInvalid from None
    namespace = _namespace(kind, payload)
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _NEW_ADMISSION_LOCK}
        )
    require_active_owner(session, user_id)
    existing = find_job(
        session, user_id, kind, request_key, request_namespace=namespace
    )
    if existing is not None:
        if not matches(existing.payload):
            raise JobConflict
        session.commit()
        return existing
    try:
        with session.begin_nested():
            if namespace == "chat":
                _validate_chat_references(session, user_id, payload)
            job, created = create_job(session, user_id, kind, request_key, payload)
            if created:
                current = database_utc_now(session)
                job.created_at = current
                session.flush()
                _check_admission(session, user_id, kind, current)
                reserve_action(session, user_id, "mutation", now=current)
            elif not matches(job.payload):
                raise JobConflict
    except (IdempotencyConflict, IntegrityError) as exc:
        winner = find_job(
            session, user_id, kind, request_key, request_namespace=namespace
        )
        if winner is not None and matches(winner.payload):
            job = winner
        elif isinstance(exc, IntegrityError) and winner is None:
            raise JobUnavailable from None
        else:
            raise JobConflict from None
    except (TypeError, ValueError):
        raise JobInputInvalid from None
    session.commit()
    return job


def _validate_chat_references(
    session: Session, user_id: int, payload: dict[str, object]
) -> None:
    if all(
        payload.get(field) is None
        for field in ("previous_job_id", "plan_revision_id", "plan_revision")
    ):
        return
    parsed = ChatJobInput.model_validate(payload)
    if parsed.previous_job_id is not None:
        previous = session.scalar(
            select(Job.id).where(
                Job.id == str(parsed.previous_job_id),
                Job.user_id == user_id,
                Job.kind == "agent",
                Job.status == "succeeded",
            )
        )
        if previous is None:
            raise JobInputInvalid("Job references are unavailable.")
    embedded = parsed.plan_revision
    revision_ids = {
        revision_id
        for revision_id in (
            parsed.plan_revision_id,
            None if embedded is None else embedded.id,
        )
        if revision_id is not None
    }
    if len(revision_ids) > 1:
        raise JobInputInvalid("Job references are unavailable.")
    for revision_id in revision_ids:
        revision = session.scalar(
            select(PlanRevision)
            .where(PlanRevision.id == revision_id, PlanRevision.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        if revision is None or (
            embedded is not None
            and PlanSnapshot.model_validate(revision.snapshot) != embedded.snapshot
        ):
            raise JobInputInvalid("Job references are unavailable.")


def _check_admission(
    session: Session,
    user_id: int,
    kind: Literal["sync", "agent"],
    current: datetime,
) -> None:
    active = (
        select(func.count())
        .select_from(Job)
        .where(Job.status.in_(("queued", "running")))
    )
    if (session.scalar(active.where(Job.user_id == user_id)) or 0) > 3:
        raise AdmissionLimitError(60)
    if (session.scalar(active) or 0) > 200:
        raise AdmissionLimitError(60)
    if kind == "agent":
        recent = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.user_id == user_id,
                Job.kind == "agent",
                Job.created_at > current - timedelta(seconds=60),
            )
        )
        if (recent or 0) > 20:
            raise AdmissionLimitError(60)


def _namespace(kind: str, payload: dict[str, object]) -> str:
    if kind == "sync":
        return "sync"
    return "chat" if payload.get("operation") == "chat" else "plan"


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
    *,
    request_namespace: str | None = None,
) -> Job | None:
    return session.scalar(
        select(Job)
        .where(
            Job.user_id == user_id,
            Job.kind == kind,
            Job.request_namespace == (request_namespace or _namespace(kind, {})),
            Job.request_key == request_key,
        )
        .execution_options(populate_existing=True)
    )


def _validate_request(kind: str, request_key: str, payload: dict[str, object]) -> str:
    if kind not in {"sync", "agent"}:
        raise ValueError("kind must be sync or agent")
    if (
        not isinstance(request_key, str)
        or not request_key.strip()
        or len(request_key) > 128
    ):
        raise ValueError("request_key must contain 1 to 128 nonblank characters")
    return _canonical(payload)


def create_job(
    session: Session,
    user_id: int,
    kind: Literal["sync", "agent"],
    request_key: str,
    payload: dict[str, object],
) -> tuple[Job, bool]:
    """Flush one job and outbox, or return an identical existing request."""
    canonical = _validate_request(kind, request_key, payload)
    namespace = _namespace(kind, payload)
    existing = find_job(
        session, user_id, kind, request_key, request_namespace=namespace
    )
    if existing is None:
        try:
            with session.begin_nested():
                job = Job(
                    user_id=user_id,
                    kind=kind,
                    request_namespace=namespace,
                    request_key=request_key,
                    payload=json.loads(canonical),
                )
                session.add(job)
                session.flush()
                session.add(JobOutbox(job_id=job.id))
                session.flush()
            return job, True
        except IntegrityError:
            existing = find_job(
                session, user_id, kind, request_key, request_namespace=namespace
            )
            if existing is None:
                raise
    if _canonical(existing.payload) != canonical:
        raise IdempotencyConflict("request_key already identifies different content")
    return existing, False
