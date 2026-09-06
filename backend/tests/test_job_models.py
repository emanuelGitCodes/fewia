"""Test durable job and outbox persistence rules."""

import sqlite3
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.job_models import Job, JobOutbox


@pytest.fixture()
def job_engine() -> Iterator[Engine]:
    """Give each test an isolated SQLite database with foreign keys enabled."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(
        dbapi_connection: sqlite3.Connection, connection_record: object
    ) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
def job_session(job_engine: Engine) -> Iterator[Session]:
    """Give each test a transaction-scoped SQLAlchemy session."""
    connection: Connection = job_engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection)
    try:
        yield test_session
    finally:
        test_session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def seed_user(session: Session, user_id: int = 1) -> None:
    session.add(models.User(id=user_id, display_name=f"User {user_id}"))
    session.flush()


def test_job_models_are_registered_with_app_models() -> None:
    assert models.Job is Job
    assert models.JobOutbox is JobOutbox


def test_job_and_outbox_have_persisted_defaults(job_session: Session) -> None:
    seed_user(job_session)
    job = Job(
        user_id=1,
        kind="sync",
        request_key="sync-1",
        payload={"cursor": None},
    )
    job_session.add(job)
    job_session.flush()

    assert UUID(job.id)
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.created_at is not None
    assert job.result is None
    assert job.error_code is None
    assert job.lease_token is None
    assert job.lease_expires_at is None

    outbox = JobOutbox(job_id=job.id)
    job_session.add(outbox)
    job_session.flush()

    assert UUID(outbox.id)
    assert outbox.created_at is not None
    assert outbox.published_at is None

    stored_job = job_session.get(Job, job.id)
    stored_outbox = job_session.get(JobOutbox, outbox.id)
    assert stored_job is not None
    assert stored_job.status == "queued"
    assert stored_job.attempts == 0
    assert stored_outbox is not None


def test_request_key_is_unique_per_user_and_kind(job_session: Session) -> None:
    seed_user(job_session, 1)
    seed_user(job_session, 2)
    first = Job(
        user_id=1,
        kind="sync",
        request_key="same-request",
        payload={"page": 1},
    )
    job_session.add(first)
    job_session.flush()

    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(
                Job(
                    user_id=1,
                    kind="sync",
                    request_key="same-request",
                    payload={"page": 1},
                )
            )
            job_session.flush()

    job_session.add(
        Job(
            user_id=2,
            kind="sync",
            request_key="same-request",
            payload={"page": 1},
        )
    )
    job_session.add(
        Job(
            user_id=1,
            kind="agent",
            request_key="same-request",
            payload={"page": 1},
        )
    )
    job_session.flush()


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed"])
def test_valid_job_statuses_are_persisted(job_session: Session, status: str) -> None:
    seed_user(job_session)
    job = Job(
        user_id=1,
        kind="sync",
        request_key=f"valid-status-{status}",
        status=status,
        payload={},
    )
    job_session.add(job)
    job_session.flush()
    assert job.status == status


@pytest.mark.parametrize("kind", ["unknown", "SYNC"])
def test_invalid_job_kind_is_rejected(job_session: Session, kind: str) -> None:
    seed_user(job_session)
    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(
                Job(
                    user_id=1,
                    kind=kind,
                    request_key=f"invalid-kind-{kind}",
                    payload={},
                )
            )
            job_session.flush()


@pytest.mark.parametrize("status", ["done", "QUEUED"])
def test_invalid_job_status_is_rejected(job_session: Session, status: str) -> None:
    seed_user(job_session)
    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(
                Job(
                    user_id=1,
                    kind="sync",
                    request_key=f"invalid-status-{status}",
                    status=status,
                    payload={},
                )
            )
            job_session.flush()


def test_negative_attempts_are_rejected(job_session: Session) -> None:
    seed_user(job_session)
    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(
                Job(
                    user_id=1,
                    kind="sync",
                    request_key="negative-attempts",
                    attempts=-1,
                    payload={},
                )
            )
            job_session.flush()


def test_payload_is_required(job_session: Session) -> None:
    seed_user(job_session)
    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(
                Job(
                    user_id=1,
                    kind="sync",
                    request_key="missing-payload",
                )
            )
            job_session.flush()


def test_one_outbox_row_can_exist_for_each_job(job_session: Session) -> None:
    seed_user(job_session)
    job = Job(
        user_id=1,
        kind="agent",
        request_key="agent-1",
        payload={"question": "plan meals"},
    )
    job_session.add(job)
    job_session.flush()
    job_session.add(JobOutbox(job_id=job.id))
    job_session.flush()

    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(JobOutbox(job_id=job.id))
            job_session.flush()


def test_foreign_keys_reject_orphan_jobs_and_outbox_rows(
    job_session: Session,
) -> None:
    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(
                Job(
                    user_id=999,
                    kind="sync",
                    request_key="orphan-job",
                    payload={},
                )
            )
            job_session.flush()

    with pytest.raises(IntegrityError):
        with job_session.begin_nested():
            job_session.add(JobOutbox(job_id=str(uuid4())))
            job_session.flush()


def test_json_payload_and_result_round_trip(job_session: Session) -> None:
    seed_user(job_session)
    payload = {
        "question": "Build a taco-night list",
        "servings": 6,
        "preferences": {"vegetarian": False, "excluded": ["shellfish"]},
        "ingredients": ["beans", "rice", "tomatoes"],
        "budget_cents": 6000,
    }
    result = {
        "items": [{"name": "black beans", "quantity": 2}],
        "estimated_total_cents": 4250,
        "warnings": ["sample price"],
    }
    job = Job(
        user_id=1,
        kind="agent",
        request_key="json-round-trip",
        payload=payload,
        result=result,
    )
    job_session.add(job)
    job_session.flush()
    job_session.expire_all()

    stored_job = job_session.get(Job, job.id)
    assert stored_job is not None
    assert stored_job.payload == payload
    assert stored_job.result == result


def test_job_and_outbox_roll_back_in_one_transaction(job_engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="abort job transaction"):
        with Session(job_engine) as session:
            with session.begin():
                seed_user(session)
                job = Job(
                    user_id=1,
                    kind="sync",
                    request_key="rolled-back-job",
                    payload={"cursor": "next"},
                )
                session.add(job)
                session.flush()
                session.add(JobOutbox(job_id=job.id))
                session.flush()
                raise RuntimeError("abort job transaction")

    with Session(job_engine) as verification_session:
        job_count = verification_session.scalar(select(func.count()).select_from(Job))
        outbox_count = verification_session.scalar(
            select(func.count()).select_from(JobOutbox)
        )
        assert job_count == 0
        assert outbox_count == 0
