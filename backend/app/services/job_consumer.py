from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.job_models import Job
from app.services.heartbeat import Heartbeat
from app.services.job_delivery import (
    JobHandler,
    JobQueue,
    LeaseLost,
    RetryableJobError,
    _job_id,
    _json_object,
)
from app.services.job_leases import claim_job, finish_job, renew_lease


def process_one(
    factory: sessionmaker[Session],
    queue: JobQueue,
    kind: str,
    handler: JobHandler,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    if kind not in {"sync", "agent"}:
        raise ValueError("kind must be sync or agent")
    message = queue.receive()
    if message is None:
        return "empty"
    job_id = _job_id(message.body)
    if job_id is None:
        return "invalid"

    action = "claimed"
    token: str | None = None
    payload: dict[str, object] | None = None
    with factory.begin() as session:
        job = session.get(Job, job_id)
        if job is None or job.kind != kind:
            return "invalid"
        claim_time = now()
        token = claim_job(session, job_id, now=claim_time)
        if token is None:
            session.refresh(job)
            active_expiry = job.lease_expires_at
            if active_expiry is not None and active_expiry.tzinfo is None:
                active_expiry = active_expiry.replace(tzinfo=UTC)
            active = (
                job.status == "running"
                and active_expiry is not None
                and active_expiry > claim_time.astimezone(UTC)
            )
            if job.status in {"succeeded", "failed"}:
                action = (
                    "exhausted"
                    if job.error_code == "attempts_exhausted"
                    else "terminal"
                )
            elif active or job.status == "running":
                action = "busy"
            else:
                action = "invalid"
        else:
            payload = _json_object(job.payload)

    if action in {"terminal", "exhausted"}:
        queue.acknowledge(message)
        return action
    if action == "busy":
        queue.extend(message, 120)
        return "busy"
    if action == "invalid":
        return "invalid"
    assert token is not None and payload is not None

    def renew() -> None:
        with factory.begin() as session:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SET LOCAL lock_timeout = '5s'"))
                session.execute(text("SET LOCAL statement_timeout = '10s'"))
            if not renew_lease(session, job_id, token, now=now()):
                raise LeaseLost
        queue.extend(message, 120)

    def finalize(
        result: dict[str, object] | None = None, error_code: str | None = None
    ) -> bool:
        with factory.begin() as session:
            return finish_job(
                session, job_id, token, now=now(), result=result, error_code=error_code
            )

    try:
        with Heartbeat(renew) as heartbeat:
            result = _json_object(handler(payload, heartbeat))
            heartbeat()
    except RetryableJobError:
        queue.extend(message, 120)
        return "retry"
    except LeaseLost:
        return "lease_lost"
    except Exception:
        try:
            renew()
        except Exception:
            return "lease_lost"
        if not finalize(error_code="handler_failed"):
            return "lease_lost"
        queue.acknowledge(message)
        return "handler_failed"

    if not finalize(result=result):
        return "lease_lost"
    queue.acknowledge(message)
    return "succeeded"
