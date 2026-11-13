"""Opt-in PostgreSQL concurrency checks for job leases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_job_consumer import FakeQueue, body

from app.job_models import Job
from app.models import User
from app.services.job_consumer import process_one
from app.services.job_leases import claim_job, finish_job, renew_lease
from app.services.job_submission import create_job

pytest_plugins = ["test_job_submission_postgres"]

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("other_kind", ["agent", "sync"])
def test_concurrent_jobs_share_one_owner_lease_and_queue_visibility(
    postgres_user: tuple[Engine, int], other_kind: str
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        first, _ = create_job(session, user_id, "agent", "first-owner-lease", {})
        second, _ = create_job(session, user_id, other_kind, "second-owner-lease", {})
        ids = [first.id, second.id]
        session.commit()
    start = Barrier(2)

    def claim(job_id: str) -> str | None:
        with Session(engine) as session:
            start.wait(timeout=10)
            token = claim_job(session, job_id, now=T0)
            session.commit()
            return token

    with ThreadPoolExecutor(max_workers=2) as executor:
        tokens = list(executor.map(claim, ids))
    assert sum(token is not None for token in tokens) == 1
    blocked_id = ids[tokens.index(None)]
    winner_id = ids[1 - tokens.index(None)]
    winner_token = tokens[1 - tokens.index(None)]
    assert winner_token is not None
    with Session(engine) as session:
        blocked = session.get(Job, blocked_id)
        assert blocked is not None
        assert blocked.status == "queued" and blocked.attempts == 0
        blocked_kind = blocked.kind
        assert (
            session.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.user_id == user_id,
                    Job.status == "running",
                    Job.lease_expires_at > T0,
                )
            )
            == 1
        )
    queue = FakeQueue(body(blocked_id))

    def handler(payload: dict[str, object], heartbeat: object) -> dict[str, object]:
        raise AssertionError("A busy owner cannot invoke the handler.")

    factory = sessionmaker(engine, expire_on_commit=False)
    assert process_one(factory, queue, blocked_kind, handler, now=lambda: T0) == "busy"
    assert queue.extensions == 1 and queue.acknowledgments == 0
    with Session(engine) as session:
        next_token = claim_job(session, blocked_id, now=T0 + timedelta(seconds=60))
        assert next_token is not None
        assert claim_job(session, winner_id, now=T0 + timedelta(seconds=60)) is None
        assert not renew_lease(
            session, winner_id, winner_token, now=T0 + timedelta(seconds=59)
        )
        session.commit()
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.user_id == user_id,
                    Job.status == "running",
                    Job.lease_expires_at > T0 + timedelta(seconds=60),
                )
            )
            == 1
        )


@pytest.mark.parametrize("status", ["disabled", "deleting"])
def test_inactive_owner_jobs_cannot_be_claimed(
    postgres_user: tuple[Engine, int], status: str
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        job, _ = create_job(session, user_id, "agent", "inactive-owner", {})
        job_id = job.id
        owner = session.get(User, user_id)
        assert owner is not None
        owner.status = status
        session.commit()
        assert claim_job(session, job_id, now=T0) is None
        session.commit()
        session.refresh(job)
        assert job.status == "queued" and job.attempts == 0


def test_concurrent_claims_one_winner_and_stale_token_fencing(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        job, created = create_job(
            session, user_id, "agent", "lease-race", {"meal": "tacos"}
        )
        assert created is True
        job_id = job.id
        session.commit()

    start = Barrier(2)

    def claim_at(claim_time: datetime) -> str | None:
        start.wait(timeout=10)
        with Session(engine) as session:
            token = claim_job(session, job_id, now=claim_time, lease_seconds=60)
            session.commit()
            return token

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(claim_at, T0) for _ in range(2)]
        tokens = [future.result(timeout=20) for future in futures]

    winners = [token for token in tokens if token is not None]
    assert len(winners) == 1
    assert tokens.count(None) == 1
    winner = winners[0]
    renew_now = T0 + timedelta(seconds=10)

    with Session(engine) as session:
        stored = session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "running"
        assert stored.attempts == 1
        assert stored.lease_token == winner
        assert renew_lease(session, job_id, "stale-token", now=renew_now) is False
        assert finish_job(session, job_id, "stale-token", now=renew_now) is False
        assert (
            renew_lease(session, job_id, winner, now=renew_now, lease_seconds=60)
            is True
        )
        session.commit()

    start.reset()

    reclaim_at = renew_now + timedelta(seconds=60)

    def reclaim_job() -> str | None:
        start.wait(timeout=10)
        with Session(engine) as session:
            token = claim_job(session, job_id, now=reclaim_at, lease_seconds=60)
            session.commit()
            return token

    with ThreadPoolExecutor(max_workers=2) as executor:
        reclaim_futures = [executor.submit(reclaim_job) for _ in range(2)]
        reclaim_tokens = [future.result(timeout=20) for future in reclaim_futures]

    reclaim_winners = [token for token in reclaim_tokens if token is not None]
    assert len(reclaim_winners) == 1
    assert reclaim_tokens.count(None) == 1
    reclaimed_winner = reclaim_winners[0]
    assert reclaimed_winner != winner

    with Session(engine) as session:
        stale = session.get(Job, job_id)
        assert stale is not None
        assert stale.status == "running"
        assert stale.attempts == 2
        assert stale.lease_token == reclaimed_winner
        assert renew_lease(session, job_id, winner, now=reclaim_at) is False
        assert finish_job(session, job_id, winner, now=reclaim_at) is False

    with Session(engine) as caller:
        assert (
            renew_lease(
                caller,
                job_id,
                reclaimed_winner,
                now=reclaim_at + timedelta(seconds=1),
                lease_seconds=60,
            )
            is True
        )
        caller.rollback()

    with Session(engine) as observer:
        stored = observer.get(Job, job_id)
        assert stored is not None
        assert stored.lease_expires_at is not None
        assert stored.lease_expires_at == reclaim_at + timedelta(seconds=60)

    with Session(engine) as caller:
        assert (
            finish_job(
                caller,
                job_id,
                reclaimed_winner,
                now=reclaim_at + timedelta(seconds=2),
                result={"ok": True},
            )
            is True
        )
        caller.rollback()

    with Session(engine) as observer:
        stored = observer.get(Job, job_id)
        assert stored is not None
        assert stored.status == "running"
        assert stored.lease_token == reclaimed_winner

    with Session(engine) as session:
        stored = session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "running"
        assert stored.lease_token == reclaimed_winner

    with Session(engine) as session:
        assert (
            finish_job(
                session,
                job_id,
                reclaimed_winner,
                now=reclaim_at + timedelta(seconds=2),
                result={"ok": True},
            )
            is True
        )
        session.commit()

    with Session(engine) as session:
        stored = session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.result == {"ok": True}
        assert stored.lease_token is None
        assert stored.lease_expires_at is None
        assert (
            renew_lease(session, job_id, winner, now=reclaim_at + timedelta(seconds=3))
            is False
        )
        assert (
            finish_job(session, job_id, winner, now=reclaim_at + timedelta(seconds=3))
            is False
        )
        session.commit()
