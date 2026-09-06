"""Test committed outbox publication and marker transactions."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.db import Base
from app.job_models import Job, JobOutbox
from app.services.outbox_publisher import PublicationError, publish_pending


@pytest.fixture()
def outbox_engine(tmp_path: Path) -> Iterator[Engine]:
    """Give each test an isolated SQLite engine with explicit transactions."""
    database_path = tmp_path / "outbox.db"
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
def factory(outbox_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=outbox_engine, expire_on_commit=False)


class RecordingSender:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_on_call = fail_on_call

    def send(self, kind: str, job_id: str) -> None:
        self.calls.append((kind, job_id))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("sender failed")


def count_rows(session: Session, table: type[Job] | type[JobOutbox]) -> int:
    return int(session.scalar(select(func.count()).select_from(table)) or 0)


def seed_user(factory: sessionmaker[Session], user_id: int = 1) -> None:
    with factory.begin() as session:
        session.add(models.User(id=user_id, display_name=f"User {user_id}"))


def seed_outbox(
    factory: sessionmaker[Session],
    *,
    user_id: int = 1,
    kind: str = "sync",
    request_key: str | None = None,
    payload: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> tuple[str, str]:
    job_id = str(uuid4())
    outbox_id = str(uuid4())
    with factory.begin() as session:
        if session.get(models.User, user_id) is None:
            session.add(models.User(id=user_id, display_name=f"User {user_id}"))
            session.flush()
        job = Job(
            id=job_id,
            user_id=user_id,
            kind=kind,
            request_key=request_key or job_id,
            payload=payload or {},
        )
        session.add(job)
        session.flush()
        session.add(JobOutbox(id=outbox_id, job_id=job_id, created_at=created_at))
    return job_id, outbox_id


def outbox_marker(factory: sessionmaker[Session], outbox_id: str) -> datetime | None:
    with factory() as session:
        row = session.get(JobOutbox, outbox_id)
        assert row is not None
        return row.published_at


def test_uncommitted_jobs_are_not_published(
    outbox_engine: Engine, factory: sessionmaker[Session]
) -> None:
    with Session(outbox_engine) as caller:
        caller.add(models.User(id=1, display_name="User 1"))
        caller.flush()
        job = Job(
            user_id=1,
            kind="sync",
            request_key="uncommitted",
            payload={"state": "pending"},
        )
        caller.add(job)
        caller.flush()
        caller.add(JobOutbox(job_id=job.id))
        caller.flush()

        sender = RecordingSender()
        assert publish_pending(factory, sender) == 0
        assert sender.calls == []


def test_successful_publication_marks_once_and_sends_kind_and_job_id(
    factory: sessionmaker[Session],
) -> None:
    job_id, outbox_id = seed_outbox(
        factory,
        kind="agent",
        payload={"kind": "sync", "job_id": "payload-value"},
    )
    sender = RecordingSender()

    assert publish_pending(factory, sender) == 1
    assert sender.calls == [("agent", job_id)]
    assert outbox_marker(factory, outbox_id) is not None

    assert publish_pending(factory, sender) == 0
    assert sender.calls == [("agent", job_id)]


def test_sender_failure_rolls_back_marker_and_keeps_earlier_success(
    factory: sessionmaker[Session],
) -> None:
    first_job, first_outbox = seed_outbox(
        factory,
        request_key="first",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second_job, second_outbox = seed_outbox(
        factory,
        request_key="second",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    failing_sender = RecordingSender(fail_on_call=2)

    with pytest.raises(PublicationError) as raised:
        publish_pending(factory, failing_sender, limit=2)

    assert raised.value.published == 1
    assert raised.value.failed == 1
    assert failing_sender.calls == [("sync", first_job), ("sync", second_job)]
    assert outbox_marker(factory, first_outbox) is not None
    assert outbox_marker(factory, second_outbox) is None

    retry_sender = RecordingSender()
    assert publish_pending(factory, retry_sender) == 1
    assert retry_sender.calls == [("sync", second_job)]
    assert outbox_marker(factory, second_outbox) is not None


def test_oldest_failure_does_not_starve_later_records(
    factory: sessionmaker[Session],
) -> None:
    first_job, first_outbox = seed_outbox(
        factory,
        request_key="failed-first",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second_job, second_outbox = seed_outbox(
        factory,
        request_key="successful-second",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    sender = RecordingSender(fail_on_call=1)

    with pytest.raises(PublicationError) as raised:
        publish_pending(factory, sender, limit=2)

    assert raised.value.published == 1
    assert raised.value.failed == 1
    assert sender.calls == [("sync", first_job), ("sync", second_job)]
    assert outbox_marker(factory, first_outbox) is None
    assert outbox_marker(factory, second_outbox) is not None


def test_commit_failure_after_send_causes_a_duplicate_retry(
    outbox_engine: Engine, factory: sessionmaker[Session]
) -> None:
    job_id, outbox_id = seed_outbox(factory)
    commit_should_fail = True

    def fail_one_commit(connection: Connection) -> None:
        del connection
        nonlocal commit_should_fail
        if commit_should_fail:
            commit_should_fail = False
            raise RuntimeError("commit failed")

    event.listen(outbox_engine, "commit", fail_one_commit)
    first_sender = RecordingSender()
    try:
        with pytest.raises(RuntimeError, match="commit failed"):
            publish_pending(factory, first_sender)
    finally:
        event.remove(outbox_engine, "commit", fail_one_commit)

    assert first_sender.calls == [("sync", job_id)]
    assert outbox_marker(factory, outbox_id) is None

    retry_sender = RecordingSender()
    assert publish_pending(factory, retry_sender) == 1
    assert retry_sender.calls == [("sync", job_id)]
    assert outbox_marker(factory, outbox_id) is not None


def test_limit_publishes_oldest_records_first(
    factory: sessionmaker[Session],
) -> None:
    first_job, first_outbox = seed_outbox(
        factory,
        request_key="oldest",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second_job, second_outbox = seed_outbox(
        factory,
        request_key="middle",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    third_job, third_outbox = seed_outbox(
        factory,
        request_key="newest",
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    sender = RecordingSender()

    assert publish_pending(factory, sender, limit=2) == 2
    assert sender.calls == [("sync", first_job), ("sync", second_job)]
    assert outbox_marker(factory, first_outbox) is not None
    assert outbox_marker(factory, second_outbox) is not None
    assert outbox_marker(factory, third_outbox) is None

    assert publish_pending(factory, sender, limit=1) == 1
    assert sender.calls == [
        ("sync", first_job),
        ("sync", second_job),
        ("sync", third_job),
    ]


@pytest.mark.parametrize("limit", [0, -1, 101, 1.0, True, "1"])
def test_limit_must_be_a_strict_integer_from_one_to_one_hundred(
    factory: sessionmaker[Session], limit: object
) -> None:
    sender = RecordingSender()
    with pytest.raises(ValueError):
        publish_pending(factory, sender, limit=limit)  # type: ignore[arg-type]


def test_outbox_marker_is_not_written_when_send_raises(
    factory: sessionmaker[Session],
) -> None:
    _, outbox_id = seed_outbox(factory)
    sender = RecordingSender(fail_on_call=1)

    with pytest.raises(PublicationError) as raised:
        publish_pending(factory, sender)

    assert raised.value.published == 0
    assert raised.value.failed == 1
    assert outbox_marker(factory, outbox_id) is None
