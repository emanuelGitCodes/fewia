"""Opt-in PostgreSQL concurrency checks for job submission."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from sqlalchemy import Connection, Engine, create_engine, delete, event, func, select
from sqlalchemy.orm import Session

from app.job_models import Job, JobOutbox
from app.models import User
from app.services.job_submission import create_job


@pytest.fixture()
def postgres_user() -> Iterator[tuple[Engine, int]]:
    url = require_test_database_url()
    engine = create_engine(
        url,
        connect_args={"options": "-c statement_timeout=15000 -c lock_timeout=10000"},
    )
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("The job concurrency test requires PostgreSQL.")
    user_id = -(uuid4().int % 2_000_000_000 + 1)
    with Session(engine) as session:
        session.add(User(id=user_id, display_name="job-concurrency-fixture"))
        session.commit()
    try:
        yield engine, user_id
    finally:
        with Session(engine) as session:
            jobs = select(Job.id).where(Job.user_id == user_id)
            session.execute(delete(JobOutbox).where(JobOutbox.job_id.in_(jobs)))
            session.execute(delete(Job).where(Job.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()
        engine.dispose()


def test_concurrent_requests_create_one_job_and_one_outbox(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    start = Barrier(2)

    def synchronize_inserts(
        mapper: object, connection: Connection, target: Job
    ) -> None:
        if target.user_id == user_id:
            start.wait(timeout=10)

    def submit() -> tuple[str, bool]:
        with Session(engine) as session:
            job, created = create_job(
                session, user_id, "agent", "same", {"meal": "tacos"}
            )
            job_id = job.id
            session.commit()
            return job_id, created

    event.listen(Job, "before_insert", synchronize_inserts)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(Job, "before_insert", synchronize_inserts)
    assert results[0][0] == results[1][0]
    assert sorted(created for _, created in results) == [False, True]
    with Session(engine) as session:
        jobs = select(Job.id).where(Job.user_id == user_id)
        assert (
            session.scalar(
                select(func.count()).select_from(Job).where(Job.user_id == user_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(JobOutbox)
                .where(JobOutbox.job_id.in_(jobs))
            )
            == 1
        )


def test_caller_rollback_removes_job_and_outbox(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        job, created = create_job(session, user_id, "sync", "rollback", {})
        assert created
        job_id = job.id
        session.rollback()
    with Session(engine) as observer:
        assert observer.get(Job, job_id) is None
        assert (
            observer.scalar(select(JobOutbox.id).where(JobOutbox.job_id == job_id))
            is None
        )
