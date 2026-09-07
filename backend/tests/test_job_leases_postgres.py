"""Opt-in PostgreSQL concurrency checks for job leases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.job_models import Job
from app.services.job_leases import claim_job, finish_job, renew_lease
from app.services.job_submission import create_job

pytest_plugins = ["test_job_submission_postgres"]

T0 = datetime(2026, 1, 1, tzinfo=UTC)


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
