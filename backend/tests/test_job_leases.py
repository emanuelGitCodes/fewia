"""Test atomic job lease claim, renew, and completion rules."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_job_submission import seed_user

from app.job_models import Job
from app.services.job_leases import claim_job, finish_job, renew_lease
from app.services.job_submission import create_job

pytest_plugins = ["test_job_submission"]

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def queued_job(job_session: Session) -> Job:
    seed_user(job_session)
    job, created = create_job(job_session, 1, "agent", "lease-1", {"meal": "tacos"})
    assert created is True
    job_session.flush()
    return job


def load_job(session: Session, job_id: str) -> Job:
    session.expire_all()
    stored = session.get(Job, job_id)
    assert stored is not None
    return stored


def assert_lease_time_matches_stored(
    stored: datetime | None, expected: datetime
) -> None:
    assert stored is not None
    if stored.tzinfo is None:
        assert stored == expected.replace(tzinfo=None)
    else:
        assert stored.astimezone(UTC) == expected


def test_claim_returns_opaque_token_and_increments_attempts(
    queued_job: Job, job_session: Session
) -> None:
    token = claim_job(job_session, queued_job.id, now=T0)
    stored = load_job(job_session, queued_job.id)

    assert token is not None
    assert token != ""
    assert stored.status == "running"
    assert stored.attempts == 1
    assert stored.lease_token == token
    assert_lease_time_matches_stored(
        stored.lease_expires_at, T0 + timedelta(seconds=60)
    )


def test_duplicate_claim_of_active_job_returns_none(
    queued_job: Job, job_session: Session
) -> None:
    first = claim_job(job_session, queued_job.id, now=T0)
    second = claim_job(job_session, queued_job.id, now=T0 + timedelta(seconds=30))
    stored = load_job(job_session, queued_job.id)

    assert first is not None
    assert second is None
    assert stored.lease_token == first
    assert stored.attempts == 1


def test_missing_job_returns_none(job_session: Session) -> None:
    seed_user(job_session)
    assert claim_job(job_session, str(uuid4()), now=T0) is None
    assert job_session.scalar(select(Job)) is None


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_terminal_job_is_not_claimed(
    queued_job: Job, job_session: Session, status: str
) -> None:
    queued_job.status = status
    queued_job.error_code = "prior" if status == "failed" else None
    job_session.flush()

    assert claim_job(job_session, queued_job.id, now=T0) is None
    stored = load_job(job_session, queued_job.id)
    assert stored.status == status
    assert stored.attempts == 0
    assert stored.lease_token is None


def test_expiry_boundary_rejects_renew_and_allows_reclaim(
    queued_job: Job, job_session: Session
) -> None:
    first = claim_job(job_session, queued_job.id, now=T0, lease_seconds=60)
    expiry = T0 + timedelta(seconds=60)
    assert first is not None
    assert (
        claim_job(
            job_session,
            queued_job.id,
            now=expiry - timedelta(seconds=1),
        )
        is None
    )
    assert renew_lease(job_session, queued_job.id, first, now=expiry) is False
    assert finish_job(job_session, queued_job.id, first, now=expiry) is False

    second = claim_job(job_session, queued_job.id, now=expiry, lease_seconds=60)
    stored = load_job(job_session, queued_job.id)

    assert second is not None
    assert second != first
    assert stored.attempts == 2
    assert stored.lease_token == second


def test_attempt_limit_fails_eligible_job_without_token(
    queued_job: Job, job_session: Session
) -> None:
    tokens: list[str] = []
    now = T0
    for _ in range(3):
        token = claim_job(job_session, queued_job.id, now=now, max_attempts=3)
        assert token is not None
        tokens.append(token)
        now = now + timedelta(seconds=60)

    assert claim_job(job_session, queued_job.id, now=now, max_attempts=3) is None
    stored = load_job(job_session, queued_job.id)
    assert stored.status == "failed"
    assert stored.error_code == "attempts_exhausted"
    assert stored.attempts == 3
    assert stored.lease_token is None
    assert stored.lease_expires_at is None
    assert len(set(tokens)) == 3


def test_wrong_and_stale_tokens_cannot_renew_or_finish(
    queued_job: Job, job_session: Session
) -> None:
    first = claim_job(job_session, queued_job.id, now=T0)
    assert first is not None
    held = claim_job(
        job_session, queued_job.id, now=T0 + timedelta(seconds=60), lease_seconds=60
    )
    assert held is not None
    later = T0 + timedelta(seconds=90)

    assert renew_lease(job_session, queued_job.id, first, now=later) is False
    assert finish_job(job_session, queued_job.id, first, now=later) is False
    assert renew_lease(job_session, queued_job.id, "not-the-token", now=later) is False
    assert finish_job(job_session, queued_job.id, "not-the-token", now=later) is False
    stored = load_job(job_session, queued_job.id)
    assert stored.status == "running"
    assert stored.lease_token == held


def test_successful_renew_extends_unexpired_lease(
    queued_job: Job, job_session: Session
) -> None:
    token = claim_job(job_session, queued_job.id, now=T0, lease_seconds=60)
    assert token is not None
    later = T0 + timedelta(seconds=30)
    assert (
        renew_lease(
            job_session,
            queued_job.id,
            token,
            now=later,
            lease_seconds=60,
        )
        is True
    )
    stored = load_job(job_session, queued_job.id)
    assert_lease_time_matches_stored(
        stored.lease_expires_at, later + timedelta(seconds=60)
    )
    assert stored.lease_token == token
    assert (
        claim_job(job_session, queued_job.id, now=later + timedelta(seconds=59)) is None
    )


def test_renew_does_not_shorten_existing_unexpired_lease(
    queued_job: Job, job_session: Session
) -> None:
    token = claim_job(job_session, queued_job.id, now=T0, lease_seconds=60)
    assert token is not None
    holder_expiry = T0 + timedelta(seconds=60)

    assert (
        renew_lease(
            job_session,
            queued_job.id,
            token,
            now=T0 + timedelta(seconds=10),
            lease_seconds=1,
        )
        is True
    )
    stored = load_job(job_session, queued_job.id)
    assert_lease_time_matches_stored(stored.lease_expires_at, holder_expiry)
    assert (
        renew_lease(
            job_session,
            queued_job.id,
            token,
            now=T0 + timedelta(seconds=20),
            lease_seconds=120,
        )
        is True
    )
    stored = load_job(job_session, queued_job.id)
    assert_lease_time_matches_stored(
        stored.lease_expires_at, T0 + timedelta(seconds=140)
    )


def test_successful_finish_marks_succeeded_and_clears_lease(
    queued_job: Job, job_session: Session
) -> None:
    token = claim_job(job_session, queued_job.id, now=T0)
    assert token is not None
    payload: dict[str, object] = {"items": ["beans"]}
    assert finish_job(job_session, queued_job.id, token, now=T0, result=payload) is True
    stored = load_job(job_session, queued_job.id)
    assert stored.status == "succeeded"
    assert stored.result == payload
    assert stored.error_code is None
    assert stored.lease_token is None
    assert stored.lease_expires_at is None
    assert finish_job(job_session, queued_job.id, token, now=T0) is False


def test_error_code_marks_failed_and_clears_lease(
    queued_job: Job, job_session: Session
) -> None:
    token = claim_job(job_session, queued_job.id, now=T0)
    assert token is not None
    assert (
        finish_job(
            job_session,
            queued_job.id,
            token,
            now=T0,
            result={"partial": True},
            error_code="provider_timeout",
        )
        is True
    )
    stored = load_job(job_session, queued_job.id)
    assert stored.status == "failed"
    assert stored.error_code == "provider_timeout"
    assert stored.result == {"partial": True}
    assert stored.lease_token is None
    assert stored.lease_expires_at is None


def test_caller_rollback_discards_claim(job_engine: Engine) -> None:
    with Session(job_engine) as setup:
        seed_user(setup)
        job, _ = create_job(setup, 1, "sync", "rollback-lease", {})
        setup.commit()
        job_id = job.id

    with Session(job_engine) as caller:
        token = claim_job(caller, job_id, now=T0)
        assert token is not None
        caller.rollback()

    with Session(job_engine) as observer:
        stored = observer.get(Job, job_id)
        assert stored is not None
        assert stored.status == "queued"
        assert stored.attempts == 0
        assert stored.lease_token is None
        assert stored.lease_expires_at is None


def test_invalid_now_and_integer_controls_are_rejected(
    queued_job: Job, job_session: Session
) -> None:
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        claim_job(job_session, queued_job.id, now=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        renew_lease(job_session, queued_job.id, "token", now=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        finish_job(job_session, queued_job.id, "token", now=naive)
    with pytest.raises(ValueError, match="lease_seconds"):
        claim_job(job_session, queued_job.id, now=T0, lease_seconds=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_attempts"):
        claim_job(job_session, queued_job.id, now=T0, max_attempts=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="lease_seconds"):
        renew_lease(job_session, queued_job.id, "token", now=T0, lease_seconds=0)
    with pytest.raises(ValueError, match="max_attempts"):
        claim_job(job_session, queued_job.id, now=T0, max_attempts=101)
    with pytest.raises(ValueError, match="lease_seconds"):
        claim_job(job_session, queued_job.id, now=T0, lease_seconds=3601)


def test_claim_normalizes_offset_datetimes_to_utc(
    queued_job: Job, job_session: Session
) -> None:
    offset = timezone(timedelta(hours=-5))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=offset)
    token = claim_job(job_session, queued_job.id, now=now, lease_seconds=60)
    stored = load_job(job_session, queued_job.id)
    assert token is not None
    assert_lease_time_matches_stored(
        stored.lease_expires_at, datetime(2026, 6, 1, 17, 1, tzinfo=UTC)
    )
