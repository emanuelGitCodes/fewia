"""Fence database writes with the current job lease."""

import hashlib
import re
from collections.abc import Callable
from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.job_effect_models import JobEffect
from app.job_models import Job
from app.services.evidence_contract import canonical_json
from app.services.job_delivery import JobContext, LeaseLost
from app.services.security_admission import database_utc_now, require_active_owner

_CONFLICT = "Job effect input conflicts."
_REFERENCE = "Job effect reference is invalid."


class JobEffectConflict(ValueError):
    pass


def input_digest(inputs: object) -> str:
    return hashlib.sha256(canonical_json(inputs).encode("utf-8")).hexdigest()


def fence_job(session: Session, context: JobContext) -> Job:
    """Lock the active owner and job before any effect lookup or write.

    Callers MUST keep provider and heartbeat calls outside this transaction.
    Effect callbacks MUST perform database writes only and MUST NOT commit.
    """
    with session.no_autoflush:
        require_active_owner(session, context.user_id)
        job = session.scalar(
            select(Job)
            .where(Job.id == context.job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current = database_utc_now(session)
        expiry = None if job is None else job.lease_expires_at
        if expiry is not None and expiry.utcoffset() is None:
            if session.get_bind().dialect.name != "sqlite":
                raise LeaseLost
            expiry = expiry.replace(tzinfo=UTC)
        if (
            job is None
            or job.user_id != context.user_id
            or job.status != "running"
            or job.lease_token != context.lease_token
            or job.attempts != context.attempt
            or expiry is None
            or expiry <= current
        ):
            raise LeaseLost
        return job


def _reference(value: dict[str, object]) -> dict[str, object]:
    valid = False
    kind = value.get("kind")
    if not isinstance(kind, str):
        raise ValueError(_REFERENCE)
    if kind in {"evidence", "proposal"} and set(value) == {"kind", "id"}:
        ident = value["id"]
        if isinstance(ident, str):
            if kind == "evidence":
                valid = re.fullmatch(r"[0-9a-f]{64}", ident) is not None
            else:
                try:
                    valid = str(UUID(ident)) == ident
                except ValueError:
                    valid = False
    if kind == "sync" and set(value) == {"kind", "changed_count"}:
        count = value["changed_count"]
        valid = type(count) is int and 0 <= count <= 2_147_483_647
    if not valid or len(canonical_json(value)) > 1024:
        raise ValueError(_REFERENCE)
    return dict(value)


def read_effect(
    session: Session, context: JobContext, effect_key: str, digest: str
) -> dict[str, object] | None:
    """Read a reference after the caller fences the job in this transaction."""
    row = session.get(JobEffect, (context.job_id, effect_key))
    if row is None:
        return None
    if row.user_id != context.user_id or row.input_digest != digest:
        raise JobEffectConflict(_CONFLICT)
    return _reference(row.result_reference)


def apply_effect(
    factory: sessionmaker[Session],
    context: JobContext,
    effect_key: str,
    inputs: object,
    write: Callable[[Session], dict[str, object]],
) -> dict[str, object]:
    if re.fullmatch(r"(?:evidence|proposal|sync):[0-9]{1,6}", effect_key) is None:
        raise ValueError("Job effect key is invalid.")
    digest = input_digest(inputs)
    with factory.begin() as session:
        fence_job(session, context)
        previous = read_effect(session, context, effect_key, digest)
        if previous is not None:
            return previous
        result = _reference(write(session))
        session.add(
            JobEffect(
                job_id=context.job_id,
                effect_key=effect_key,
                user_id=context.user_id,
                input_digest=digest,
                result_reference=result,
            )
        )
        session.flush()
        return result
