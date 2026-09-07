"""Test bounded durable job recovery."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.db import Base
from app.job_models import Job, JobOutbox
from app.services.job_recovery import recover_jobs

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture()
def recovery_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "recovery.db"
    test_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        isolation_level=None,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(
        dbapi_connection: sqlite3.Connection, connection_record: object
    ) -> None:
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(test_engine, "begin")
    def begin_sqlite_transaction(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(
        test_engine,
        tables=[models.User.__table__, Job.__table__, JobOutbox.__table__],
    )
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(
            test_engine,
            tables=[models.User.__table__, Job.__table__, JobOutbox.__table__],
        )
        test_engine.dispose()


@pytest.fixture()
def recovery_factory(recovery_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=recovery_engine, expire_on_commit=False)


def seed_job(
    factory: sessionmaker[Session],
    *,
    status: str = "running",
    attempts: int = 1,
    lease_expires_at: datetime | None = NOW - timedelta(seconds=1),
    lease_token: str | None = "lease",
    published_at: datetime | None = NOW - timedelta(seconds=600),
    created_at: datetime | None = None,
) -> tuple[str, str]:
    job_id = str(uuid4())
    outbox_id = str(uuid4())
    with factory.begin() as session:
        if session.get(models.User, 1) is None:
            session.add(models.User(id=1, display_name="Test user"))
            session.flush()
        job = Job(
            id=job_id,
            user_id=1,
            kind="sync",
            request_key=job_id,
            status=status,
            payload={},
            attempts=attempts,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            created_at=created_at,
        )
        session.add(job)
        session.flush()
        session.add(
            JobOutbox(
                id=outbox_id,
                job_id=job_id,
                published_at=published_at,
                created_at=created_at,
            )
        )
    return job_id, outbox_id


def load_job(factory: sessionmaker[Session], job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def load_outbox(factory: sessionmaker[Session], outbox_id: str) -> JobOutbox:
    with factory() as session:
        outbox = session.get(JobOutbox, outbox_id)
        assert outbox is not None
        return outbox


def test_final_attempt_crash_fails_without_classifier(
    recovery_factory: sessionmaker[Session],
) -> None:
    job_id, outbox_id = seed_job(recovery_factory, attempts=3)
    classifier = cast(Callable[[Job], bool], lambda job: pytest.fail(job.id))

    assert recover_jobs(recovery_factory, classifier, now=NOW, max_attempts=3) == 1

    job = load_job(recovery_factory, job_id)
    assert job.status == "failed"
    assert job.error_code == "attempts_exhausted"
    assert job.lease_token is None
    assert job.lease_expires_at is None
    assert load_outbox(recovery_factory, outbox_id).published_at is not None


def test_safe_replay_requeues_and_unpublishes(
    recovery_factory: sessionmaker[Session],
) -> None:
    job_id, outbox_id = seed_job(recovery_factory, attempts=2)

    assert recover_jobs(recovery_factory, lambda job: True, now=NOW) == 1

    job = load_job(recovery_factory, job_id)
    assert job.status == "queued"
    assert job.attempts == 2
    assert job.lease_token is None
    assert job.lease_expires_at is None
    assert load_outbox(recovery_factory, outbox_id).published_at is None


def test_unsafe_replay_fails_without_republication(
    recovery_factory: sessionmaker[Session],
) -> None:
    job_id, outbox_id = seed_job(recovery_factory)

    assert recover_jobs(recovery_factory, lambda job: False, now=NOW) == 1

    job = load_job(recovery_factory, job_id)
    assert job.status == "failed"
    assert job.error_code == "recovery_required"
    assert job.lease_token is None
    assert job.lease_expires_at is None
    assert load_outbox(recovery_factory, outbox_id).published_at is not None


def test_pending_outbox_is_preserved(
    recovery_factory: sessionmaker[Session],
) -> None:
    job_id, outbox_id = seed_job(recovery_factory, published_at=None)

    assert recover_jobs(recovery_factory, lambda job: True, now=NOW) == 0

    job = load_job(recovery_factory, job_id)
    assert job.status == "running"
    assert job.lease_token == "lease"
    assert load_outbox(recovery_factory, outbox_id).published_at is None


def test_queued_age_boundary_is_inclusive(
    recovery_factory: sessionmaker[Session],
) -> None:
    old_id, old_outbox = seed_job(
        recovery_factory,
        status="queued",
        lease_expires_at=None,
        lease_token=None,
        published_at=NOW - timedelta(seconds=300),
        created_at=NOW - timedelta(seconds=2),
    )
    new_id, new_outbox = seed_job(
        recovery_factory,
        status="queued",
        lease_expires_at=None,
        lease_token=None,
        published_at=NOW - timedelta(seconds=299),
        created_at=NOW - timedelta(seconds=1),
    )

    assert recover_jobs(recovery_factory, lambda job: True, now=NOW) == 1
    assert load_job(recovery_factory, old_id).status == "queued"
    assert load_outbox(recovery_factory, old_outbox).published_at is None
    assert load_job(recovery_factory, new_id).status == "queued"
    assert load_outbox(recovery_factory, new_outbox).published_at is not None


@pytest.mark.parametrize("status", ["running", "succeeded", "failed"])
def test_active_and_terminal_jobs_are_untouched(
    recovery_factory: sessionmaker[Session], status: str
) -> None:
    lease_expires_at = NOW + timedelta(seconds=1) if status == "running" else None
    lease_token = "active" if status == "running" else None
    job_id, outbox_id = seed_job(
        recovery_factory,
        status=status,
        lease_expires_at=lease_expires_at,
        lease_token=lease_token,
    )

    assert recover_jobs(recovery_factory, lambda job: True, now=NOW) == 0

    job = load_job(recovery_factory, job_id)
    assert job.status == status
    assert job.lease_token == lease_token
    assert load_outbox(recovery_factory, outbox_id).published_at is not None


def test_classifier_exception_rolls_back_all_recovery_changes(
    recovery_factory: sessionmaker[Session],
) -> None:
    first_id, first_outbox = seed_job(
        recovery_factory, created_at=NOW - timedelta(seconds=2)
    )
    second_id, second_outbox = seed_job(
        recovery_factory, created_at=NOW - timedelta(seconds=1)
    )

    def classify(job: Job) -> bool:
        if job.id == second_id:
            raise RuntimeError("classifier failed")
        return True

    with pytest.raises(RuntimeError, match="classifier failed"):
        recover_jobs(recovery_factory, classify, now=NOW, limit=2)

    for job_id, outbox_id in ((first_id, first_outbox), (second_id, second_outbox)):
        job = load_job(recovery_factory, job_id)
        assert job.status == "running"
        assert job.lease_token == "lease"
        assert load_outbox(recovery_factory, outbox_id).published_at is not None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("limit", True),
        ("limit", 0),
        ("limit", 101),
        ("max_attempts", False),
        ("max_attempts", 0),
        ("max_attempts", 101),
        ("min_age_seconds", True),
        ("min_age_seconds", 0),
        ("min_age_seconds", 86_401),
    ],
)
def test_integer_controls_are_positive_bounded(
    recovery_factory: sessionmaker[Session], name: str, value: object
) -> None:
    controls: dict[str, object] = {name: value}
    with pytest.raises(ValueError, match=name):
        recover_jobs(
            recovery_factory,
            lambda job: True,
            now=NOW,
            **cast(dict[str, int], controls),
        )


def test_now_must_be_timezone_aware(
    recovery_factory: sessionmaker[Session],
) -> None:
    for invalid_now in (
        datetime(2026, 1, 1),
        cast(datetime, "not a datetime"),
    ):
        with pytest.raises(ValueError, match="timezone-aware"):
            recover_jobs(recovery_factory, lambda job: True, now=invalid_now)


def test_replay_classifier_is_required(
    recovery_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(TypeError, match="callable"):
        recover_jobs(
            recovery_factory,
            cast(Callable[[Job], bool], None),
            now=NOW,
        )


def test_selection_is_ordered_and_bounded(
    recovery_factory: sessionmaker[Session],
) -> None:
    first_id, first_outbox = seed_job(
        recovery_factory, created_at=NOW - timedelta(seconds=3)
    )
    second_id, second_outbox = seed_job(
        recovery_factory, created_at=NOW - timedelta(seconds=2)
    )
    third_id, third_outbox = seed_job(
        recovery_factory, created_at=NOW - timedelta(seconds=1)
    )
    seen: list[str] = []

    def classify(job: Job) -> bool:
        seen.append(job.id)
        return True

    assert recover_jobs(recovery_factory, classify, now=NOW, limit=2) == 2
    assert seen == [first_id, second_id]
    assert load_outbox(recovery_factory, first_outbox).published_at is None
    assert load_outbox(recovery_factory, second_outbox).published_at is None
    assert load_job(recovery_factory, third_id).status == "running"
    assert load_outbox(recovery_factory, third_outbox).published_at is not None
