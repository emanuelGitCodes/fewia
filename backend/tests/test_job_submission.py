"""Test atomic durable job submission and idempotency behavior."""

import sqlite3
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    Connection,
    Engine,
    create_engine,
    delete,
    event,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.job_models import Job, JobOutbox
from app.plan_models import PlanRevision
from app.security_models import QuotaCounter
from app.services import job_submission
from app.services.job_submission import (
    IdempotencyConflict,
    JobConflict,
    JobInputInvalid,
    JobUnavailable,
    create_job,
    find_job,
    reuse_job,
    submit_job,
)
from app.services.security_admission import AdmissionLimitError, OwnerUnavailableError

JobKind = Literal["sync", "agent"]


@pytest.mark.parametrize("outcome", ["none", "gone", "conflict", "match"])
def test_reuse_job_commits_only_a_match(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    session = Mock(spec=Session)
    session.no_autoflush = nullcontext()
    job = Job(payload={"meal": "tacos"})
    lookup = Mock(return_value=None if outcome == "none" else job)
    if outcome == "gone":
        lookup.side_effect = [job, None]
    monkeypatch.setattr(job_submission, "find_job", lookup)
    owner_check = Mock()
    monkeypatch.setattr(job_submission, "require_active_owner", owner_check)
    matches = Mock(return_value=outcome == "match")

    if outcome == "conflict":
        with pytest.raises(JobConflict):
            reuse_job(cast(Session, session), 1, "agent", "key", matches)
    else:
        result = reuse_job(cast(Session, session), 1, "agent", "key", matches)
        assert result is (job if outcome == "match" else None)

    lookup.assert_called_with(session, 1, "agent", "key", request_namespace=None)
    assert lookup.call_count == (1 if outcome == "none" else 2)
    if outcome in {"none", "gone"}:
        matches.assert_not_called()
    else:
        matches.assert_called_once_with(job.payload)
    if outcome == "none":
        owner_check.assert_not_called()
    else:
        owner_check.assert_called_once_with(session, 1)
    if outcome == "gone":
        session.rollback.assert_called_once_with()
    else:
        session.rollback.assert_not_called()
    if outcome == "match":
        session.commit.assert_called_once_with()
    else:
        session.commit.assert_not_called()


def test_submit_job_commits_created_job_and_outbox(
    job_engine: Engine, job_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user(job_session)
    commit = Mock(wraps=job_session.commit)
    monkeypatch.setattr(job_session, "commit", commit)
    payload: dict[str, object] = {"meal": "tacos"}

    job = submit_job(job_session, 1, "agent", "created", payload, payload.__eq__)

    commit.assert_called_once_with()
    with Session(job_engine) as observer:
        stored = observer.get(Job, job.id)
        assert stored is not None
        assert stored.payload == payload
        assert count_rows(observer, Job) == 1
        assert count_rows(observer, JobOutbox) == 1


@pytest.mark.parametrize("error_type", [IdempotencyConflict, IntegrityError])
def test_submit_job_commits_matching_race_winner(
    job_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    session = job_session
    seed_user(session)
    commit = Mock(wraps=session.commit)
    monkeypatch.setattr(session, "commit", commit)
    payload: dict[str, object] = {"meal": "tacos"}
    winner = Job(payload=payload)
    error = (
        IntegrityError("INSERT", {}, RuntimeError())
        if error_type is IntegrityError
        else IdempotencyConflict()
    )
    create = Mock(side_effect=error)
    lookup = Mock(side_effect=[None, winner])
    monkeypatch.setattr(job_submission, "create_job", create)
    monkeypatch.setattr(job_submission, "find_job", lookup)
    matches = Mock(return_value=True)

    job = submit_job(session, 1, "agent", "key", payload, matches)

    assert job is winner
    create.assert_called_once_with(session, 1, "agent", "key", payload)
    assert lookup.call_count == 2
    lookup.assert_called_with(session, 1, "agent", "key", request_namespace="plan")
    matches.assert_called_once_with(winner.payload)
    commit.assert_called_once_with()


@pytest.mark.parametrize(
    ("error", "has_winner", "expected"),
    [
        (IntegrityError("INSERT", {}, RuntimeError()), False, JobUnavailable),
        (IntegrityError("INSERT", {}, RuntimeError()), True, JobConflict),
        (IdempotencyConflict(), False, JobConflict),
        (IdempotencyConflict(), True, JobConflict),
        (ValueError(), False, JobInputInvalid),
    ],
)
def test_submit_job_errors_do_not_commit(
    job_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    has_winner: bool,
    expected: type[Exception],
) -> None:
    session = job_session
    seed_user(session)
    commit = Mock(wraps=session.commit)
    monkeypatch.setattr(session, "commit", commit)
    winner = Job(payload={"meal": "beans"}) if has_winner else None
    lookup = Mock(side_effect=[None, winner])
    matches = Mock(return_value=False)
    monkeypatch.setattr(job_submission, "create_job", Mock(side_effect=error))
    monkeypatch.setattr(job_submission, "find_job", lookup)

    with pytest.raises(expected):
        submit_job(session, 1, "agent", "key", {}, matches)

    commit.assert_not_called()
    if isinstance(error, IdempotencyConflict | IntegrityError):
        assert lookup.call_count == 2
    else:
        assert lookup.call_count == 1
    lookup.assert_called_with(session, 1, "agent", "key", request_namespace="plan")
    if winner is None or type(error) is ValueError:
        matches.assert_not_called()
    else:
        matches.assert_called_once_with(winner.payload)


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
        tables=[
            models.User.__table__,
            Job.__table__,
            JobOutbox.__table__,
            QuotaCounter.__table__,
            PlanRevision.__table__,
        ],
    )
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(
            test_engine,
            tables=[
                models.User.__table__,
                Job.__table__,
                JobOutbox.__table__,
                QuotaCounter.__table__,
                PlanRevision.__table__,
            ],
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


def test_find_job_matches_user_kind_and_request_key(job_session: Session) -> None:
    seed_user(job_session)
    job, created = create_job(job_session, 1, "sync", "lookup-key", {"page": 1})
    assert created is True
    job_session.commit()

    found = find_job(job_session, 1, "sync", "lookup-key")

    assert found is not None
    assert found.id == job.id
    assert find_job(job_session, 1, "agent", "lookup-key") is None


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


def test_plan_and_chat_keys_coexist_and_replay_independently(
    job_session: Session,
) -> None:
    seed_user(job_session)
    plan_payload: dict[str, object] = {"operation": "plan", "meal": "tacos"}
    chat_payload: dict[str, object] = {"operation": "chat", "message": "tacos"}
    plan = submit_job(
        job_session, 1, "agent", "chat:same", plan_payload, plan_payload.__eq__
    )
    chat = submit_job(
        job_session, 1, "agent", "chat:same", chat_payload, chat_payload.__eq__
    )
    assert plan.id != chat.id
    assert plan.request_key == chat.request_key == "chat:same"
    assert plan.request_namespace == "plan"
    assert chat.request_namespace == "chat"
    for namespace, payload, expected in (
        ("plan", plan_payload, plan.id),
        ("chat", chat_payload, chat.id),
    ):
        reused = reuse_job(
            job_session,
            1,
            "agent",
            "chat:same",
            payload.__eq__,
            request_namespace=namespace,
        )
        assert reused is not None and reused.id == expected
        replay = submit_job(
            job_session, 1, "agent", "chat:same", payload, payload.__eq__
        )
        assert replay.id == expected
    assert count_rows(job_session, JobOutbox) == 2
    assert job_session.scalar(select(func.sum(QuotaCounter.count))) == 2


def test_replay_at_capacity_consumes_no_mutation_and_conflict_leaves_no_rows(
    job_session: Session,
) -> None:
    seed_user(job_session)
    first = submit_job(job_session, 1, "agent", "first", {"value": 1}, lambda _: True)
    submit_job(job_session, 1, "sync", "second", {}, lambda _: True)
    submit_job(job_session, 1, "agent", "third", {}, lambda _: True)
    counter = job_session.scalar(select(QuotaCounter))
    assert counter is not None
    counter.count = 60
    job_session.commit()
    replay = submit_job(
        job_session,
        1,
        "agent",
        "first",
        {"value": 1, "snapshot": 2},
        lambda payload: payload.get("value") == 1,
    )
    assert replay.id == first.id
    with pytest.raises(JobConflict):
        submit_job(job_session, 1, "agent", "first", {}, lambda _: False)
    with pytest.raises(AdmissionLimitError):
        submit_job(job_session, 1, "sync", "fourth", {}, lambda _: True)
    job_session.commit()
    assert count_rows(job_session, Job) == count_rows(job_session, JobOutbox) == 3
    assert job_session.scalar(select(func.sum(QuotaCounter.count))) == 60


@pytest.mark.parametrize("age_seconds", [59, 60])
def test_rolling_agent_limit_spans_operations_and_excludes_old_jobs(
    job_session: Session, monkeypatch: pytest.MonkeyPatch, age_seconds: int
) -> None:
    seed_user(job_session)
    now = datetime(2026, 11, 12, 12, 34, 15, tzinfo=UTC)
    monkeypatch.setattr(job_submission, "database_utc_now", lambda _: now)
    for index in range(20):
        job, _ = create_job(
            job_session,
            1,
            "agent",
            f"existing-{index}",
            {"operation": "chat" if index % 2 else "plan"},
        )
        job.status = "succeeded"
        job.created_at = now - timedelta(seconds=age_seconds)
    job_session.commit()
    if age_seconds == 59:
        with pytest.raises(AdmissionLimitError) as caught:
            submit_job(job_session, 1, "agent", "new", {}, lambda _: True)
        assert caught.value.retry_after == 60
        expected = 20
    else:
        submit_job(job_session, 1, "agent", "new", {}, lambda _: True)
        expected = 21
    job_session.commit()
    assert count_rows(job_session, Job) == expected
    assert count_rows(job_session, JobOutbox) == expected
    mutation_count = job_session.scalar(select(func.sum(QuotaCounter.count))) or 0
    assert mutation_count == expected - 20


@pytest.mark.parametrize("status", ["disabled", "deleting", "missing"])
def test_unavailable_submission_leaves_no_job_or_quota(
    job_session: Session, status: str
) -> None:
    if status != "missing":
        seed_user(job_session)
        owner = job_session.get(models.User, 1)
        assert owner is not None
        owner.status = status
        job_session.commit()
    with pytest.raises(OwnerUnavailableError):
        submit_job(job_session, 1, "sync", "denied", {}, lambda _: True)
    job_session.commit()
    assert count_rows(job_session, Job) == count_rows(job_session, JobOutbox) == 0
    assert job_session.scalar(select(func.count()).select_from(QuotaCounter)) == 0


def test_full_mutation_quota_rolls_back_new_job_and_outbox(
    job_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user(job_session)
    now = datetime(2026, 11, 12, 12, 34, 15, tzinfo=UTC)
    monkeypatch.setattr(job_submission, "database_utc_now", lambda _: now)
    job_session.add(
        QuotaCounter(
            action="mutation",
            scope="user",
            scope_key=1,
            minute_start=now.replace(second=0),
            count=60,
            expires_at=now.replace(second=0) + timedelta(minutes=1),
        )
    )
    job_session.commit()
    with pytest.raises(AdmissionLimitError):
        submit_job(job_session, 1, "agent", "denied", {}, lambda _: True)
    job_session.commit()
    assert count_rows(job_session, Job) == count_rows(job_session, JobOutbox) == 0
    assert job_session.scalar(select(func.sum(QuotaCounter.count))) == 60


@pytest.mark.parametrize("table", ["JOBS", "JOB_OUTBOX", "QUOTA_COUNTERS"])
def test_service_storage_failure_rolls_back_all_admission_rows(
    job_engine: Engine, table: str
) -> None:
    with Session(job_engine) as session:
        seed_user(session)
        session.commit()

    def fail_insert(
        connection: Connection,
        cursor: sqlite3.Cursor,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith(f"INSERT INTO {table} "):
            raise RuntimeError("Synthetic storage failure.")

    event.listen(job_engine, "before_cursor_execute", fail_insert)
    try:
        with Session(job_engine) as session:
            with pytest.raises(RuntimeError, match="Synthetic storage failure"):
                submit_job(session, 1, "agent", "failure", {}, lambda _: True)
            session.commit()
    finally:
        event.remove(job_engine, "before_cursor_execute", fail_insert)
    with Session(job_engine) as observer:
        assert count_rows(observer, Job) == count_rows(observer, JobOutbox) == 0
        assert observer.scalar(select(func.count()).select_from(QuotaCounter)) == 0


def test_reuse_refreshes_payload_after_owner_lock(
    job_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user(job_session)
    job, _ = create_job(job_session, 1, "agent", "refresh", {"value": "old"})
    job_session.commit()
    assert job.payload == {"value": "old"}
    require_owner = job_submission.require_active_owner

    def change_before_lock(session: Session, user_id: int) -> None:
        session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(payload={"value": "new"})
            .execution_options(synchronize_session=False)
        )
        require_owner(session, user_id)

    monkeypatch.setattr(job_submission, "require_active_owner", change_before_lock)
    with pytest.raises(JobConflict):
        reuse_job(job_session, 1, "agent", "refresh", lambda p: p["value"] == "old")
    assert job.payload == {"value": "new"}


@pytest.mark.parametrize(
    ("kind", "payload", "namespace"),
    [
        ("sync", {}, "plan"),
        ("agent", {"operation": "chat"}, "plan"),
        ("agent", {}, "chat"),
    ],
)
def test_namespace_constraint_rejects_explicit_mismatch(
    job_session: Session, kind: str, payload: dict[str, object], namespace: str
) -> None:
    seed_user(job_session)
    job_session.commit()
    with pytest.raises(IntegrityError), job_session.begin_nested():
        job_session.execute(
            Job.__table__.insert().values(
                user_id=1,
                kind=kind,
                request_namespace=namespace,
                request_key="wrong-namespace",
                payload=payload,
            )
        )
    assert count_rows(job_session, Job) == 0


@pytest.mark.parametrize(
    "violation",
    [
        "valid",
        "foreign_previous",
        "queued_previous",
        "sync_previous",
        "missing_previous",
        "foreign_revision",
        "missing_revision",
        "wrong_embedded_id",
        "stale_snapshot",
        "unknown_field",
    ],
)
def test_chat_submission_checks_current_owned_references(
    job_session: Session, violation: str
) -> None:
    seed_user(job_session)
    seed_user(job_session, 2)
    previous, _ = create_job(
        job_session,
        2 if violation == "foreign_previous" else 1,
        "sync" if violation == "sync_previous" else "agent",
        "previous",
        {},
    )
    previous.status = "queued" if violation == "queued_previous" else "succeeded"
    revision = PlanRevision(
        id=uuid4(),
        user_id=2 if violation == "foreign_revision" else 1,
        snapshot={"meals": [], "pantry_ingredient_ids": []},
    )
    job_session.add(revision)
    job_session.commit()
    embedded_id = uuid4() if violation == "wrong_embedded_id" else revision.id
    payload: dict[str, object] = {
        "operation": "chat",
        "message": "Plan dinner",
        "monthly_limit_cents": 10000,
        "spending": {
            "period": "2026-11-01",
            "posted_cents": 0,
            "pending_cents": 0,
            "refreshed_at": "2026-11-12T12:00:00+00:00",
        },
        "spending_source": "manual",
        "previous_job_id": (
            str(uuid4()) if violation == "missing_previous" else previous.id
        ),
        "plan_revision_id": (
            str(uuid4()) if violation == "missing_revision" else str(revision.id)
        ),
        "plan_revision": {
            "id": str(embedded_id),
            "snapshot": {
                "meals": [],
                "pantry_ingredient_ids": [],
                "plan_cap_cents": 0 if violation == "stale_snapshot" else None,
            },
        },
    }
    if violation == "unknown_field":
        payload["unknown"] = "raw input"
    if violation != "valid":
        with pytest.raises(JobInputInvalid):
            submit_job(job_session, 1, "agent", "chat:refs", payload, payload.__eq__)
        job_session.commit()
        assert count_rows(job_session, Job) == count_rows(job_session, JobOutbox) == 1
        assert job_session.scalar(select(func.count()).select_from(QuotaCounter)) == 0
        return
    accepted = submit_job(job_session, 1, "agent", "chat:refs", payload, payload.__eq__)
    accepted_id = accepted.id
    job_session.execute(delete(JobOutbox).where(JobOutbox.job_id == previous.id))
    job_session.delete(previous)
    job_session.delete(revision)
    job_session.commit()
    replay = submit_job(job_session, 1, "agent", "chat:refs", payload, payload.__eq__)
    assert replay.id == accepted_id
    assert job_session.scalar(select(func.sum(QuotaCounter.count))) == 1
