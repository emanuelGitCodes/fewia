"""Test atomic durable job submission and idempotency behavior."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.job_models import Job, JobOutbox
from app.services.job_submission import IdempotencyConflict, create_job

JobKind = Literal["sync", "agent"]


@pytest.fixture()
def job_engine(tmp_path: Path) -> Iterator[Engine]:
    """Give each test an isolated SQLite engine with explicit transactions."""
    database_path = tmp_path / "jobs.db"
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
        dbapi_connection.execute("PRAGMA busy_timeout=5000")

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
def job_session(job_engine: Engine) -> Iterator[Session]:
    """Give each test a session that leaves transaction control to the test."""
    session = Session(job_engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def seed_user(session: Session, user_id: int = 1) -> None:
    session.add(models.User(id=user_id, display_name=f"User {user_id}"))
    session.flush()


def count_rows(session: Session, table: type[Job] | type[JobOutbox]) -> int:
    return int(session.scalar(select(func.count()).select_from(table)) or 0)


def submit(
    session: Session,
    user_id: int,
    kind: JobKind,
    request_key: str,
    payload: dict[str, object],
) -> tuple[Job, bool]:
    return create_job(session, user_id, kind, request_key, payload)


def test_submission_flushes_both_rows_without_committing(
    job_engine: Engine,
) -> None:
    with Session(job_engine) as caller:
        seed_user(caller)
        job, created = submit(caller, 1, "sync", "sync-1", {"cursor": None})

        assert created is True
        assert UUID(job.id)
        assert job.status == "queued"
        assert job.attempts == 0
        assert job.payload == {"cursor": None}
        outbox = caller.scalar(select(JobOutbox).where(JobOutbox.job_id == job.id))
        assert outbox is not None

        with Session(job_engine) as observer:
            assert count_rows(observer, Job) == 0
            assert count_rows(observer, JobOutbox) == 0

        caller.commit()

    with Session(job_engine) as observer:
        assert count_rows(observer, Job) == 1
        assert count_rows(observer, JobOutbox) == 1


def test_replay_returns_existing_job_and_preserves_caller_writes(
    job_session: Session,
) -> None:
    seed_user(job_session)
    first, first_created = submit(
        job_session, 1, "agent", "agent-1", {"question": "plan meals"}
    )
    assert first_created is True
    job_session.commit()

    seed_user(job_session, 2)
    replay, replay_created = submit(
        job_session, 1, "agent", "agent-1", {"question": "plan meals"}
    )

    assert replay_created is False
    assert replay.id == first.id
    assert job_session.get(models.User, 2) is not None
    assert count_rows(job_session, Job) == 1
    assert count_rows(job_session, JobOutbox) == 1
    job_session.commit()


def test_conflicting_replay_raises_for_true_and_one(
    job_session: Session,
) -> None:
    seed_user(job_session)
    first, _ = submit(job_session, 1, "sync", "same-key", {"enabled": True})
    job_session.commit()

    with pytest.raises(IdempotencyConflict):
        submit(job_session, 1, "sync", "same-key", {"enabled": 1})

    stored = job_session.get(Job, first.id)
    assert stored is not None
    assert stored.payload == {"enabled": True}
    assert count_rows(job_session, Job) == 1
    assert count_rows(job_session, JobOutbox) == 1


def test_nested_dictionary_reordering_is_the_same_replay(
    job_session: Session,
) -> None:
    seed_user(job_session)
    first_payload = {"request": {"b": [1, 2], "a": {"y": 2, "x": 1}}}
    reordered_payload = {"request": {"a": {"x": 1, "y": 2}, "b": [1, 2]}}
    first, _ = submit(job_session, 1, "agent", "nested-key", first_payload)
    job_session.commit()

    replay, created = submit(job_session, 1, "agent", "nested-key", reordered_payload)

    assert created is False
    assert replay.id == first.id
    job_session.commit()


def test_request_key_scope_includes_user_and_kind(job_session: Session) -> None:
    seed_user(job_session, 1)
    seed_user(job_session, 2)
    first, _ = submit(job_session, 1, "sync", "scoped-key", {"page": 1})
    second, second_created = submit(job_session, 2, "sync", "scoped-key", {"page": 1})
    third, third_created = submit(job_session, 1, "agent", "scoped-key", {"page": 1})
    job_session.commit()

    assert second_created is True
    assert third_created is True
    assert len({first.id, second.id, third.id}) == 3
    assert count_rows(job_session, Job) == 3
    assert count_rows(job_session, JobOutbox) == 3


@pytest.mark.parametrize("kind", ["", "invalid", "SYNC"])
def test_invalid_kind_is_rejected(job_session: Session, kind: str) -> None:
    seed_user(job_session)
    with pytest.raises(ValueError):
        submit(job_session, 1, cast(JobKind, kind), "valid-key", {})


@pytest.mark.parametrize("request_key", ["", " ", "\t\n", "x" * 129])
def test_invalid_request_key_is_rejected(
    job_session: Session, request_key: str
) -> None:
    seed_user(job_session)
    with pytest.raises(ValueError):
        submit(job_session, 1, "sync", request_key, {})


def test_request_key_accepts_128_characters(job_session: Session) -> None:
    seed_user(job_session)
    job, created = submit(job_session, 1, "sync", "x" * 128, {})
    assert created is True
    assert job.request_key == "x" * 128


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_json_values_are_rejected(job_session: Session, value: float) -> None:
    seed_user(job_session)
    with pytest.raises(ValueError):
        submit(job_session, 1, "sync", "nonfinite", {"value": value})


def test_non_json_payload_is_rejected(job_session: Session) -> None:
    seed_user(job_session)
    with pytest.raises((TypeError, ValueError)):
        submit(job_session, 1, "sync", "non-json", {"value": object()})


def test_wrong_user_foreign_key_is_rejected(job_engine: Engine) -> None:
    with Session(job_engine) as caller:
        with pytest.raises(IntegrityError):
            submit(caller, 999, "sync", "unknown-user", {})
        caller.rollback()

    with Session(job_engine) as observer:
        assert count_rows(observer, Job) == 0
        assert count_rows(observer, JobOutbox) == 0


def test_outbox_insert_failure_leaves_no_job_orphan(job_engine: Engine) -> None:
    with Session(job_engine) as caller:
        seed_user(caller)

        def fail_outbox_insert(
            connection: Connection,
            cursor: sqlite3.Cursor,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            del connection, cursor, parameters, context, executemany
            if statement.lstrip().upper().startswith("INSERT INTO JOB_OUTBOX"):
                raise RuntimeError("outbox insert failed")

        event.listen(job_engine, "before_cursor_execute", fail_outbox_insert)
        try:
            with pytest.raises(RuntimeError, match="outbox insert failed"):
                submit(caller, 1, "agent", "outbox-failure", {})
        finally:
            event.remove(job_engine, "before_cursor_execute", fail_outbox_insert)
        caller.rollback()

    with Session(job_engine) as observer:
        assert count_rows(observer, Job) == 0
        assert count_rows(observer, JobOutbox) == 0


def test_unique_race_replays_competing_job_with_nested_savepoint(
    job_engine: Engine,
) -> None:
    rival_job_id = str(uuid4())
    rival_outbox_id = str(uuid4())
    payload = {"page": 1}
    with Session(job_engine) as setup:
        seed_user(setup)
        setup.commit()

    injected = False

    def insert_competing_job(
        connection: Connection,
        cursor: sqlite3.Cursor,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal injected
        del cursor, parameters, context, executemany
        if injected or not statement.lstrip().upper().startswith("SELECT"):
            return
        if "FROM JOBS" not in statement.upper():
            return
        injected = True
        connection.execute(
            Job.__table__.insert().values(
                id=rival_job_id,
                user_id=1,
                kind="sync",
                request_key="race-key",
                payload=payload,
            )
        )
        connection.execute(
            JobOutbox.__table__.insert().values(
                id=rival_outbox_id,
                job_id=rival_job_id,
            )
        )

    event.listen(job_engine, "after_cursor_execute", insert_competing_job)
    try:
        with Session(job_engine) as caller:
            replay, created = submit(caller, 1, "sync", "race-key", payload)
            assert created is False
            assert replay.id == rival_job_id
            caller.commit()
    finally:
        event.remove(job_engine, "after_cursor_execute", insert_competing_job)

    with Session(job_engine) as observer:
        assert count_rows(observer, Job) == 1
        assert count_rows(observer, JobOutbox) == 1


def test_unrelated_integrity_error_is_rethrown(job_engine: Engine) -> None:
    with Session(job_engine) as setup:
        seed_user(setup)
        setup.commit()

    def fail_job_insert(
        connection: Connection,
        cursor: sqlite3.Cursor,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, context, executemany
        if statement.lstrip().upper().startswith("INSERT INTO JOBS"):
            raise IntegrityError("unrelated constraint", parameters, RuntimeError())

    event.listen(job_engine, "before_cursor_execute", fail_job_insert)
    try:
        with Session(job_engine) as caller:
            with pytest.raises(IntegrityError, match="unrelated constraint"):
                submit(caller, 1, "sync", "unrelated-error", {})
            caller.rollback()
    finally:
        event.remove(job_engine, "before_cursor_execute", fail_job_insert)

    with Session(job_engine) as observer:
        assert count_rows(observer, Job) == 0
        assert count_rows(observer, JobOutbox) == 0
