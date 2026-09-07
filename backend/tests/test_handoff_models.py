"""Test shopping handoff metadata and SQLite constraints."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import (
    CheckConstraint,
    Connection,
    DateTime,
    Engine,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.handoff_models import ShoppingHandoff

FORBIDDEN_COLUMNS = {
    "access_token",
    "user_token",
    "raw_response",
    "provider_payload",
    "checkout_url",
    "order_id",
    "payment_token",
}


@pytest.fixture()
def handoff_engine() -> Iterator[Engine]:
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

    tables = [models.User.__table__, ShoppingHandoff.__table__]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def handoff_session(handoff_engine: Engine) -> Iterator[Session]:
    connection: Connection = handoff_engine.connect()
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


def add_handoff(
    session: Session,
    *,
    user_id: int = 1,
    request_hash: str = "hash-1",
    request_payload: dict[str, object] | None = None,
    state: str | None = None,
    attempt_token: str | None = None,
    attempts: int | None = None,
    started_at: datetime | None = None,
    url: str | None = None,
    error_code: str | None = None,
) -> ShoppingHandoff:
    payload: dict[str, object] = (
        {"line_items": ["beans"]} if request_payload is None else request_payload
    )
    handoff = ShoppingHandoff(
        user_id=user_id,
        request_hash=request_hash,
        request_payload=payload,
    )
    if state is not None:
        handoff.state = state
    if attempt_token is not None:
        handoff.attempt_token = attempt_token
    if attempts is not None:
        handoff.attempts = attempts
    if started_at is not None:
        handoff.started_at = started_at
    if url is not None:
        handoff.url = url
    if error_code is not None:
        handoff.error_code = error_code
    session.add(handoff)
    session.flush()
    return handoff


def test_handoff_columns_types_and_timezone_config() -> None:
    table = ShoppingHandoff.__table__
    assert isinstance(table.c.id.type, String)
    assert table.c.id.type.length == 36
    assert table.c.request_payload.nullable is False
    assert table.c.state.nullable is False
    assert table.c.attempts.nullable is False
    assert table.c.created_at.nullable is False
    for name in (
        "started_at",
        "retry_authorized_at",
        "expires_at",
        "created_at",
    ):
        column_type = table.c[name].type
        assert isinstance(column_type, DateTime)
        assert column_type.timezone is True
    assert FORBIDDEN_COLUMNS.isdisjoint(table.columns.keys())


def test_handoff_constraints_match_the_schema_contract() -> None:
    table = ShoppingHandoff.__table__
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    check_sql = [str(check.sqltext) for check in checks]
    assert any("prepared" in sql and "uncertain" in sql for sql in check_sql)
    assert any("attempts >= 0" in sql for sql in check_sql)
    assert any(
        "dispatching" in sql and "attempt_token" in sql and "started_at" in sql
        for sql in check_sql
    )
    assert any("succeeded" in sql and "url" in sql for sql in check_sql)
    assert any(
        constraint.name == "uq_shopping_handoffs_user_request_hash"
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    foreign_keys = {
        (foreign_key.parent.name, foreign_key.target_fullname)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for foreign_key in constraint.elements
    }
    assert ("user_id", "users.id") in foreign_keys
    assert [column.name for column in table.primary_key.columns] == ["id"]


def test_handoff_defaults_and_payload_round_trip(handoff_session: Session) -> None:
    seed_user(handoff_session)
    payload: dict[str, object] = {
        "line_item_measurements": [{"name": "beans", "quantity": 2}]
    }
    handoff = add_handoff(handoff_session, request_payload=payload)
    assert UUID(handoff.id)
    assert handoff.state == "prepared"
    assert handoff.attempts == 0
    assert handoff.created_at is not None
    assert handoff.attempt_token is None
    assert handoff.url is None
    assert handoff.error_code is None
    assert handoff.started_at is None
    assert handoff.retry_authorized_at is None
    assert handoff.expires_at is None
    handoff_session.expire_all()
    stored = handoff_session.get(ShoppingHandoff, handoff.id)
    assert stored is not None
    assert stored.request_payload == payload


def test_ownership_foreign_key_rejects_unknown_users(
    handoff_session: Session,
) -> None:
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(handoff_session, user_id=999)


def test_request_hash_is_unique_per_user(handoff_session: Session) -> None:
    seed_user(handoff_session, 1)
    seed_user(handoff_session, 2)
    add_handoff(handoff_session, user_id=1, request_hash="same-hash")
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(handoff_session, user_id=1, request_hash="same-hash")
    add_handoff(handoff_session, user_id=2, request_hash="same-hash")


@pytest.mark.parametrize(
    "state",
    ["prepared", "dispatching", "succeeded", "failed", "uncertain"],
)
def test_valid_states_are_persisted(handoff_session: Session, state: str) -> None:
    seed_user(handoff_session)
    started = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    token = "attempt-1" if state == "dispatching" else None
    started_at = started if state == "dispatching" else None
    url = "https://example.test/list" if state == "succeeded" else None
    handoff = add_handoff(
        handoff_session,
        request_hash=f"valid-{state}",
        state=state,
        attempt_token=token,
        started_at=started_at,
        url=url,
    )
    assert handoff.state == state


@pytest.mark.parametrize("state", ["done", "PREPARED", "running"])
def test_invalid_states_are_rejected(handoff_session: Session, state: str) -> None:
    seed_user(handoff_session)
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(handoff_session, request_hash=f"invalid-{state}", state=state)


def test_negative_attempts_are_rejected(handoff_session: Session) -> None:
    seed_user(handoff_session)
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(handoff_session, attempts=-1)


def test_request_payload_is_required(handoff_session: Session) -> None:
    seed_user(handoff_session)
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            handoff_session.add(
                ShoppingHandoff(user_id=1, request_hash="missing-payload")
            )
            handoff_session.flush()


def test_dispatching_requires_token_and_started_at(handoff_session: Session) -> None:
    seed_user(handoff_session)
    started = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(
                handoff_session,
                request_hash="dispatch-missing-token",
                state="dispatching",
                started_at=started,
            )
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(
                handoff_session,
                request_hash="dispatch-missing-started",
                state="dispatching",
                attempt_token="attempt-1",
            )


def test_succeeded_requires_url(handoff_session: Session) -> None:
    seed_user(handoff_session)
    with pytest.raises(IntegrityError):
        with handoff_session.begin_nested():
            add_handoff(handoff_session, state="succeeded")


def test_sqlite_creates_timezone_aware_datetime_columns(
    handoff_engine: Engine,
) -> None:
    inspected = inspect(handoff_engine).get_columns(ShoppingHandoff.__tablename__)
    columns = {column["name"]: column for column in inspected}
    for name in (
        "started_at",
        "retry_authorized_at",
        "expires_at",
        "created_at",
    ):
        assert isinstance(ShoppingHandoff.__table__.c[name].type, DateTime)
        assert ShoppingHandoff.__table__.c[name].type.timezone is True
        assert name in columns
