"""Check action admission on SQLite fixtures and disposable PostgreSQL."""

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from queue import Queue
from threading import Barrier, Event
from time import monotonic, sleep
from typing import Literal, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.security_models import QuotaCounter
from app.services.security_admission import (
    MUTATION_USER_LIMIT,
    RETAILER_GLOBAL_LIMIT,
    RETAILER_USER_LIMIT,
    AdmissionLimitError,
    OwnerUnavailableError,
    reserve_action,
)
from tests.conftest import require_test_database_url
from tests.test_runtime_database_policy import _safe_target

Action = Literal["mutation", "retailer"]
QuotaDatabase = tuple[Engine, list[int]]
_NOW = datetime(2026, 11, 12, 12, 34, 15, 250000, tzinfo=UTC)
_MINUTE = _NOW.replace(second=0, microsecond=0)
_TABLE = QuotaCounter.__table__


@pytest.fixture()
def sqlite_quota_database() -> Iterator[Engine]:
    engine = sa.create_engine("sqlite:///:memory:")

    @sa.event.listens_for(engine, "connect")
    def set_fixture_clock(
        connection: sqlite3.Connection, connection_record: object
    ) -> None:
        del connection_record

        def current_timestamp() -> str:
            return _NOW.strftime("%Y-%m-%d %H:%M:%S")

        connection.create_function("current_timestamp", 0, current_timestamp)

    try:
        User.__table__.create(engine)
        _TABLE.create(engine)
        with Session(engine) as session:
            session.add(User(id=1, display_name="Synthetic SQLite admission owner"))
            session.commit()
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def quota_database() -> Iterator[QuotaDatabase]:
    url = require_test_database_url()
    _safe_target(url)
    engine = sa.create_engine(
        sa.engine.make_url(url).set(drivername="postgresql+psycopg"),
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=10000 -c lock_timeout=5000",
        },
    )
    owners: list[int] = []
    try:
        try:
            with engine.begin() as connection:
                assert sa.inspect(connection).has_table("quota_counters")
                connection.execute(_TABLE.delete())
                while len(owners) < 11:
                    owner = connection.scalar(
                        insert(User)
                        .values(
                            id=(uuid4().int >> 66) + 1,
                            display_name="Synthetic admission owner",
                            status="active",
                        )
                        .on_conflict_do_nothing(index_elements=["id"])
                        .returning(User.id)
                    )
                    if owner is not None:
                        owners.append(owner)
            yield engine, owners
        finally:
            with engine.begin() as connection:
                connection.execute(_TABLE.delete())
                connection.execute(sa.delete(User).where(User.id.in_(owners)))
    finally:
        engine.dispose()


def _seed(
    session: Session,
    action: Action,
    scope: str,
    scope_key: int,
    count: int,
) -> None:
    session.execute(
        _TABLE.insert().values(
            action=action,
            scope=scope,
            scope_key=scope_key,
            minute_start=_MINUTE,
            expires_at=_MINUTE + timedelta(minutes=1),
            count=count,
        )
    )


def _counts(session: Session) -> dict[tuple[str, str, int], int]:
    return {
        (row.action, row.scope, row.scope_key): row.count
        for row in session.execute(
            sa.select(
                _TABLE.c.action, _TABLE.c.scope, _TABLE.c.scope_key, _TABLE.c.count
            ).where(_TABLE.c.minute_start == _MINUTE)
        )
    }


def test_admission_defaults_and_safe_error() -> None:
    assert (MUTATION_USER_LIMIT, RETAILER_USER_LIMIT, RETAILER_GLOBAL_LIMIT) == (
        60,
        10,
        100,
    )
    error = AdmissionLimitError(0)
    assert error.status_code == 429
    assert error.retry_after == 1
    assert str(error) == "Action limit reached. Try again later."
    owner_error = OwnerUnavailableError()
    assert owner_error.status_code == 403
    assert str(owner_error) == "Action owner is unavailable."


@pytest.mark.parametrize("action", ["mutation", "retailer"])
def test_sqlite_repeated_reservations_share_one_minute_counter(
    sqlite_quota_database: Engine, action: Action
) -> None:
    with Session(sqlite_quota_database) as session:
        for current in (
            None,
            _NOW,
            _NOW.astimezone(timezone(timedelta(hours=-5))),
            None,
        ):
            reserve_action(session, 1, action, now=current)
            session.commit()
        rows = session.execute(
            sa.select(
                _TABLE.c.scope,
                _TABLE.c.scope_key,
                _TABLE.c.minute_start,
                _TABLE.c.expires_at,
                _TABLE.c.count,
            ).order_by(_TABLE.c.scope)
        ).all()
        minute = _MINUTE.replace(tzinfo=None)
        expected = [("user", 1, minute, minute + timedelta(minutes=1), 4)]
        if action == "retailer":
            expected.insert(0, ("global", 0, minute, minute + timedelta(minutes=1), 4))
        assert rows == expected


@pytest.mark.parametrize("action", ["mutation", "retailer"])
@pytest.mark.parametrize("status", ["missing", "disabled", "deleting"])
def test_sqlite_unavailable_owner_preserves_counters(
    sqlite_quota_database: Engine, action: Action, status: str
) -> None:
    with Session(sqlite_quota_database) as session:
        reserve_action(session, 1, "mutation")
        owner_id = 2 if status == "missing" else 1
        if status != "missing":
            session.execute(sa.update(User).where(User.id == 1).values(status=status))
        session.commit()
        before = _counts(session)
        assert before == {("mutation", "user", 1): 1}
        with pytest.raises(OwnerUnavailableError) as caught:
            reserve_action(session, owner_id, action)
        assert str(caught.value) == "Action owner is unavailable."
        session.commit()
        assert _counts(session) == before
        assert session.scalar(sa.select(sa.func.count()).select_from(_TABLE)) == 1


@pytest.mark.parametrize("dialect", ["mysql", "oracle", "mssql", "unknown"])
def test_unsupported_dialect_fails_before_sql(dialect: str) -> None:
    session = Mock(spec=Session)
    session.get_bind.return_value.dialect.name = dialect
    with pytest.raises(RuntimeError) as caught:
        reserve_action(cast(Session, session), 1, "retailer")
    assert str(caught.value) == "Action admission is unavailable."
    session.get_bind.assert_called_once_with()
    session.execute.assert_not_called()
    session.scalar.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("action", ["mutation", "retailer"])
@pytest.mark.parametrize("status", ["missing", "disabled", "deleting"])
def test_unavailable_owner_creates_no_counters(
    quota_database: QuotaDatabase, action: Action, status: str
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        if status == "missing":
            session.execute(sa.delete(User).where(User.id == owners[0]))
        else:
            session.execute(
                sa.update(User).where(User.id == owners[0]).values(status=status)
            )
        session.commit()
        with pytest.raises(OwnerUnavailableError) as caught:
            reserve_action(session, owners[0], action, now=_NOW)
        assert caught.value.status_code == 403
        assert str(caught.value) == "Action owner is unavailable."
        assert _counts(session) == {}
        session.commit()
    with Session(quota_engine) as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(_TABLE)) == 0


def test_mutation_allows_sixty_then_refuses_without_changes(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        for _ in range(60):
            reserve_action(session, owners[0], "mutation", now=_NOW)
        before = _counts(session)
        assert before == {("mutation", "user", owners[0]): 60}
        with pytest.raises(AdmissionLimitError) as caught:
            reserve_action(session, owners[0], "mutation", now=_NOW)
        assert caught.value.retry_after == 45
        assert _counts(session) == before
        reserve_action(session, owners[1], "mutation", now=_NOW)
        assert _counts(session)[("mutation", "user", owners[1])] == 1
        session.commit()


def test_retailer_owner_limit_preserves_global_count(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        for _ in range(10):
            reserve_action(session, owners[0], "retailer", now=_NOW)
        before = _counts(session)
        assert before == {
            ("retailer", "global", 0): 10,
            ("retailer", "user", owners[0]): 10,
        }
        with pytest.raises(AdmissionLimitError):
            reserve_action(session, owners[0], "retailer", now=_NOW)
        session.commit()
    with Session(quota_engine) as session:
        assert _counts(session) == before
        reserve_action(session, owners[1], "retailer", now=_NOW)
        assert _counts(session)[("retailer", "global", 0)] == 11


def test_full_owner_without_global_row_creates_no_global_row(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        _seed(session, "retailer", "user", owners[0], 10)
        with pytest.raises(AdmissionLimitError):
            reserve_action(session, owners[0], "retailer", now=_NOW)
        session.commit()
    with Session(quota_engine) as session:
        assert _counts(session) == {("retailer", "user", owners[0]): 10}


def test_global_retailer_limit_creates_no_refused_owner_row(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        for owner in owners[:10]:
            for _ in range(10):
                reserve_action(session, owner, "retailer", now=_NOW)
        before = _counts(session)
        assert before[("retailer", "global", 0)] == 100
        assert len(before) == 11
        with pytest.raises(AdmissionLimitError) as caught:
            reserve_action(session, owners[10], "retailer", now=_NOW)
        assert str(caught.value) == "Action limit reached. Try again later."
        session.commit()
    with Session(quota_engine) as session:
        assert _counts(session) == before


@pytest.mark.parametrize(
    ("second", "microsecond", "expected"),
    [(0, 0, 60), (0, 1, 60), (15, 250000, 45), (59, 0, 1), (59, 999999, 1)],
)
def test_retry_after_rounds_up_to_the_next_minute(
    quota_database: QuotaDatabase, second: int, microsecond: int, expected: int
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        _seed(session, "mutation", "user", owners[0], 60)
        with pytest.raises(AdmissionLimitError) as caught:
            reserve_action(
                session,
                owners[0],
                "mutation",
                now=_NOW.replace(second=second, microsecond=microsecond),
            )
        assert caught.value.retry_after == expected


def test_next_minute_and_timezone_share_utc_buckets(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        _seed(session, "mutation", "user", owners[0], 60)
        following = (_MINUTE + timedelta(minutes=1)).astimezone(
            timezone(timedelta(hours=-5))
        )
        reserve_action(session, owners[0], "mutation", now=following)
        reserve_action(session, owners[0], "mutation", now=following.astimezone(UTC))
        statement = sa.select(
            _TABLE.c.minute_start, _TABLE.c.expires_at, _TABLE.c.count
        ).order_by(_TABLE.c.minute_start)
        rows = session.execute(statement).all()
        assert rows == [
            (_MINUTE, _MINUTE + timedelta(minutes=1), 60),
            (_MINUTE + timedelta(minutes=1), _MINUTE + timedelta(minutes=2), 2),
        ]


def test_default_clock_uses_database_time_with_non_utc_session(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        session.execute(sa.text("SET LOCAL TIME ZONE 'America/New_York'"))
        before = session.scalar(sa.select(sa.func.clock_timestamp()))
        assert isinstance(before, datetime)
        reserve_action(session, owners[0], "mutation")
        after = session.scalar(sa.select(sa.func.clock_timestamp()))
        assert isinstance(after, datetime)
        minute = session.scalar(sa.select(_TABLE.c.minute_start))
        assert isinstance(minute, datetime)
        assert before.astimezone(UTC).replace(second=0, microsecond=0) <= minute
        assert minute <= after.astimezone(UTC).replace(second=0, microsecond=0)


def test_helper_does_not_commit_or_publish_uncommitted_counts(
    quota_database: QuotaDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        commit = Mock(side_effect=AssertionError("The caller owns commit."))
        monkeypatch.setattr(session, "commit", commit)
        reserve_action(session, owners[0], "retailer", now=_NOW)
        assert len(_counts(session)) == 2
        with Session(quota_engine) as observer:
            assert _counts(observer) == {}
        commit.assert_not_called()
        session.rollback()
    with Session(quota_engine) as session:
        assert _counts(session) == {}
        reserve_action(session, owners[0], "retailer", now=_NOW)
        assert _counts(session)[("retailer", "global", 0)] == 1


def test_refusal_does_not_flush_pending_counter_rows(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        _seed(session, "mutation", "user", owners[0], 60)
        pending = QuotaCounter(
            action="retailer",
            scope="user",
            scope_key=owners[1],
            minute_start=_MINUTE,
            expires_at=_MINUTE + timedelta(minutes=1),
        )
        session.add(pending)
        with pytest.raises(AdmissionLimitError):
            reserve_action(session, owners[0], "mutation", now=_NOW)
        assert pending in session.new
        assert _counts(session) == {("mutation", "user", owners[0]): 60}


@pytest.mark.parametrize("action", ["mutation", "retailer"])
def test_action_limits_are_independent(
    quota_database: QuotaDatabase, action: Action
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        _seed(session, "mutation", "user", owners[0], 59)
        _seed(session, "retailer", "user", owners[0], 9)
        _seed(session, "retailer", "global", 0, 99)
        reserve_action(session, owners[0], action, now=_NOW)
        counts = _counts(session)
        assert counts[("mutation", "user", owners[0])] == (
            60 if action == "mutation" else 59
        )
        assert counts[("retailer", "user", owners[0])] == (
            10 if action == "retailer" else 9
        )


@pytest.mark.parametrize("boundary", ["mutation", "owner", "global", "empty"])
def test_concurrent_reservations_serialize_at_the_boundary(
    quota_database: QuotaDatabase, boundary: str
) -> None:
    quota_engine, owners = quota_database
    action: Action = "mutation" if boundary in {"mutation", "empty"} else "retailer"
    with Session(quota_engine) as session:
        if boundary == "mutation":
            _seed(session, "mutation", "user", owners[0], 59)
        elif boundary == "owner":
            _seed(session, "retailer", "user", owners[0], 9)
            _seed(session, "retailer", "global", 0, 9)
        elif boundary == "global":
            _seed(session, "retailer", "global", 0, 99)
        session.commit()
    barrier = Barrier(4)

    def attempt(owner: int) -> bool:
        with Session(quota_engine) as session:
            barrier.wait(timeout=10)
            try:
                reserve_action(session, owner, action, now=_NOW)
            except AdmissionLimitError:
                session.commit()
                return False
            session.commit()
            return True

    contenders = owners[:4] if boundary == "global" else [owners[0]] * 4
    with ThreadPoolExecutor(max_workers=4) as executor:
        admitted = list(executor.map(attempt, contenders))
    assert sum(admitted) == (4 if boundary == "empty" else 1)
    with Session(quota_engine) as session:
        counts = _counts(session)
        if boundary in {"mutation", "empty"}:
            assert counts == {
                ("mutation", "user", owners[0]): 4 if boundary == "empty" else 60
            }
        elif boundary == "owner":
            assert counts == {
                ("retailer", "user", owners[0]): 10,
                ("retailer", "global", 0): 10,
            }
        else:
            assert counts[("retailer", "global", 0)] == 100
            assert len(counts) == 2
            assert sum(value for key, value in counts.items() if key[1] == "user") == 1


def _wait_for_blocker(session: Session, waiter: int, blocker: int) -> None:
    deadline = monotonic() + 3
    while monotonic() < deadline:
        blockers = session.scalar(sa.select(sa.func.pg_blocking_pids(waiter)))
        if blockers is not None and blocker in blockers:
            return
        sleep(0.01)
    pytest.fail("The owner transaction did not block the waiting transaction.")


@pytest.mark.parametrize("action", ["mutation", "retailer"])
def test_disable_waits_for_caller_then_later_admission_rejects(
    quota_database: QuotaDatabase, action: Action
) -> None:
    quota_engine, owners = quota_database
    backend_pids: Queue[int] = Queue()
    disabled = Event()
    release_disable = Event()

    def disable() -> None:
        with Session(quota_engine) as session:
            pid = session.scalar(sa.select(sa.func.pg_backend_pid()))
            assert isinstance(pid, int)
            backend_pids.put(pid)
            session.execute(
                sa.update(User).where(User.id == owners[0]).values(status="disabled")
            )
            disabled.set()
            assert release_disable.wait(timeout=10)
            session.commit()

    def admit() -> None:
        with Session(quota_engine) as session:
            owner = session.get(User, owners[0])
            assert owner is not None and owner.status == "active"
            pid = session.scalar(sa.select(sa.func.pg_backend_pid()))
            assert isinstance(pid, int)
            backend_pids.put(pid)
            reserve_action(session, owners[0], action, now=_NOW)
            session.commit()

    with (
        ThreadPoolExecutor(max_workers=2) as executor,
        Session(quota_engine) as session,
    ):
        reserve_action(session, owners[0], action, now=_NOW)
        before = _counts(session)
        owner_pid = session.scalar(sa.select(sa.func.pg_backend_pid()))
        assert isinstance(owner_pid, int)
        disabling = executor.submit(disable)
        try:
            disable_pid = backend_pids.get(timeout=10)
            _wait_for_blocker(session, disable_pid, owner_pid)
            assert not disabled.is_set()
            session.commit()
            assert disabled.wait(timeout=10)
            admitting = executor.submit(admit)
            _wait_for_blocker(session, backend_pids.get(timeout=10), disable_pid)
            release_disable.set()
            disabling.result(timeout=10)
            with pytest.raises(OwnerUnavailableError):
                admitting.result(timeout=10)
        finally:
            release_disable.set()
            session.rollback()
    with Session(quota_engine) as session:
        assert _counts(session) == before
        assert session.scalar(sa.select(User.status).where(User.id == owners[0])) == (
            "disabled"
        )


@pytest.mark.parametrize(
    ("action", "scope", "key", "count"),
    [
        ("mutation", "global", 0, 1),
        ("retailer", "global", 1, 1),
        ("retailer", "user", 0, 1),
        ("mutation", "user", -1, 1),
        ("unknown", "user", 1, 1),
        ("retailer", "other", 1, 1),
        ("mutation", "user", 1, 0),
        ("mutation", "user", 1, -1),
    ],
)
def test_database_rejects_invalid_counter_rows(
    quota_database: QuotaDatabase, action: str, scope: str, key: int, count: int
) -> None:
    quota_engine, _ = quota_database
    with Session(quota_engine) as session, pytest.raises(IntegrityError):
        session.execute(
            _TABLE.insert().values(
                action=action,
                scope=scope,
                scope_key=key,
                count=count,
                minute_start=_MINUTE,
                expires_at=_MINUTE + timedelta(minutes=1),
            )
        )


def test_database_rejects_duplicate_counter_buckets(
    quota_database: QuotaDatabase,
) -> None:
    quota_engine, owners = quota_database
    with Session(quota_engine) as session:
        _seed(session, "mutation", "user", owners[0], 1)
        with pytest.raises(IntegrityError):
            _seed(session, "mutation", "user", owners[0], 1)
