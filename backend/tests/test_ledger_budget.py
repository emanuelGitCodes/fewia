"""Test grocery spending loads from the Plaid ledger."""

import sqlite3
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.plaid_models import PlaidItem, PlaidTransaction
from app.services.ledger_budget import (
    SpendingUnavailable,
    _integral_cents,
    _month_end,
    _stored_utc,
    load_spending,
)

NEW_YORK = ZoneInfo("America/New_York")
PERIOD = date(2026, 9, 1)
OLD = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
NEW = datetime(2026, 9, 2, 15, 0, tzinfo=UTC)


@pytest.fixture()
def ledger_engine() -> Iterator[Engine]:
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

    tables = [
        models.User.__table__,
        PlaidItem.__table__,
        PlaidTransaction.__table__,
    ]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def ledger_session(ledger_engine: Engine) -> Iterator[Session]:
    connection: Connection = ledger_engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection)
    try:
        yield test_session
    finally:
        test_session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def add_user(session: Session, user_id: int) -> None:
    session.add(models.User(id=user_id, display_name=f"user-{user_id}"))
    session.flush()


def as_utc(value: datetime | None) -> datetime:
    assert value is not None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def add_item(
    session: Session,
    *,
    item_id: str,
    user_id: int,
    cursor: str | None = "cursor-1",
    last_synced_at: datetime | None = NEW,
) -> None:
    session.add(
        PlaidItem(
            id=item_id,
            user_id=user_id,
            provider_item_id=item_id,
            credential_ref="plaid-item-ref",
            cursor=cursor,
            last_synced_at=None if last_synced_at is None else as_utc(last_synced_at),
        )
    )
    session.flush()


def add_txn(
    session: Session,
    *,
    item_id: str,
    transaction_id: str,
    amount_cents: int,
    transaction_date: date,
    pending: bool = False,
    is_grocery: bool = True,
    currency: str = "USD",
) -> None:
    session.add(
        PlaidTransaction(
            item_id=item_id,
            transaction_id=transaction_id,
            account_id="acct-1",
            amount_cents=amount_cents,
            currency=currency,
            transaction_date=transaction_date,
            pending=pending,
            is_grocery=is_grocery,
            classification_version="v1",
        )
    )
    session.flush()


def complete_owner(session: Session, user_id: int = 1, item_id: str = "item-1") -> None:
    add_user(session, user_id)
    add_item(session, item_id=item_id, user_id=user_id)


def test_multiple_items_use_oldest_sync_time(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_item(
        ledger_session,
        item_id="item-2",
        user_id=1,
        cursor="cursor-2",
        last_synced_at=OLD,
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="posted-new",
        amount_cents=400,
        transaction_date=date(2026, 9, 10),
    )
    add_txn(
        ledger_session,
        item_id="item-2",
        transaction_id="posted-old",
        amount_cents=250,
        transaction_date=date(2026, 9, 2),
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot == SpendingSnapshot(PERIOD, 650, 0, OLD)
    assert snapshot.refreshed_at == OLD


def test_pending_and_refunds_sum_signed_cents(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="posted",
        amount_cents=1000,
        transaction_date=date(2026, 9, 3),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="refund",
        amount_cents=-200,
        transaction_date=date(2026, 9, 4),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="pending",
        amount_cents=300,
        transaction_date=date(2026, 9, 5),
        pending=True,
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="pending-refund",
        amount_cents=-50,
        transaction_date=date(2026, 9, 6),
        pending=True,
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot.posted_cents == 800
    assert snapshot.pending_cents == 250


def test_empty_completed_ledger_returns_zero(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot == SpendingSnapshot(PERIOD, 0, 0, NEW)


@pytest.mark.parametrize(
    "cursor, last_synced_at",
    [
        (None, NEW),
        ("cursor-1", None),
        ("", NEW),
        ("   ", NEW),
        (None, None),
    ],
)
def test_uninitialized_item_is_unavailable(
    ledger_session: Session, cursor: str | None, last_synced_at: datetime | None
) -> None:
    add_user(ledger_session, 1)
    add_item(
        ledger_session,
        item_id="item-1",
        user_id=1,
        cursor=cursor,
        last_synced_at=last_synced_at,
    )
    with pytest.raises(SpendingUnavailable, match="Spending is unavailable"):
        load_spending(ledger_session, 1, PERIOD)


def test_missing_item_is_unavailable(ledger_session: Session) -> None:
    add_user(ledger_session, 1)
    with pytest.raises(SpendingUnavailable):
        load_spending(ledger_session, 1, PERIOD)


def test_one_uninitialized_item_blocks_completed_sibling(
    ledger_session: Session,
) -> None:
    complete_owner(ledger_session)
    add_item(
        ledger_session,
        item_id="item-2",
        user_id=1,
        cursor=None,
        last_synced_at=None,
    )
    with pytest.raises(SpendingUnavailable):
        load_spending(ledger_session, 1, PERIOD)


def test_wrong_user_month_and_category_are_excluded(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_user(ledger_session, 2)
    add_item(
        ledger_session,
        item_id="item-other",
        user_id=2,
        cursor="cursor-other",
        last_synced_at=OLD,
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="owned-grocery",
        amount_cents=500,
        transaction_date=date(2026, 9, 15),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="owned-non-grocery",
        amount_cents=900,
        transaction_date=date(2026, 9, 15),
        is_grocery=False,
    )
    add_txn(
        ledger_session,
        item_id="item-other",
        transaction_id="other-user",
        amount_cents=7000,
        transaction_date=date(2026, 9, 15),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="other-month",
        amount_cents=400,
        transaction_date=date(2026, 8, 31),
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot.posted_cents == 500
    assert snapshot.pending_cents == 0
    assert snapshot.refreshed_at == NEW


def test_month_boundaries_are_inclusive(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="before",
        amount_cents=11,
        transaction_date=date(2026, 8, 31),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="first",
        amount_cents=20,
        transaction_date=date(2026, 9, 1),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="last",
        amount_cents=30,
        transaction_date=date(2026, 9, 30),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="after",
        amount_cents=40,
        transaction_date=date(2026, 10, 1),
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot.posted_cents == 50


def test_february_leap_day_is_included(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="leap",
        amount_cents=29,
        transaction_date=date(2024, 2, 29),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="march",
        amount_cents=1,
        transaction_date=date(2024, 3, 1),
    )
    snapshot = load_spending(ledger_session, 1, date(2024, 2, 1))
    assert snapshot.posted_cents == 29


def test_december_includes_the_last_day(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="nye",
        amount_cents=7,
        transaction_date=date(2026, 12, 31),
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="jan",
        amount_cents=9,
        transaction_date=date(2027, 1, 1),
    )
    snapshot = load_spending(ledger_session, 1, date(2026, 12, 1))
    assert snapshot.posted_cents == 7


def test_stored_utc_converts_new_york_offset() -> None:
    ny = datetime(2026, 9, 2, 8, 0, tzinfo=NEW_YORK)
    assert _stored_utc(ny) == datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def test_fixture_sync_time_persists_as_utc(ledger_session: Session) -> None:
    add_user(ledger_session, 1)
    add_item(
        ledger_session,
        item_id="item-ny",
        user_id=1,
        cursor="cursor-ny",
        last_synced_at=datetime(2026, 9, 2, 8, 0, tzinfo=NEW_YORK),
    )
    stored = ledger_session.get(PlaidItem, "item-ny")
    assert stored is not None
    assert as_utc(stored.last_synced_at) == datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def test_aware_new_york_sync_time_normalizes_to_utc(ledger_session: Session) -> None:
    add_user(ledger_session, 1)
    add_item(
        ledger_session,
        item_id="item-ny",
        user_id=1,
        cursor="cursor-ny",
        last_synced_at=datetime(2026, 9, 2, 8, 0, tzinfo=NEW_YORK),
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot.refreshed_at == datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def test_naive_sync_time_is_stored_utc(ledger_session: Session) -> None:
    add_user(ledger_session, 1)
    add_item(
        ledger_session,
        item_id="item-naive",
        user_id=1,
        cursor="cursor-naive",
        last_synced_at=datetime(2026, 9, 1, 9, 0),  # noqa: DTZ001
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot.refreshed_at == datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    assert snapshot.refreshed_at.tzinfo is UTC


def test_sqlite_reload_treats_naive_sync_time_as_utc(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    ledger_session.flush()
    ledger_session.expire_all()
    stored = ledger_session.get(PlaidItem, "item-1")
    assert stored is not None
    snapshot = load_spending(ledger_session, 1, PERIOD)
    assert snapshot.refreshed_at.tzinfo is not None
    assert snapshot.refreshed_at.utcoffset() is not None
    assert snapshot.refreshed_at == as_utc(stored.last_synced_at)


@pytest.mark.parametrize(
    "user_id, period",
    [
        (0, PERIOD),
        (-1, PERIOD),
        (True, PERIOD),
        (1.5, PERIOD),
        (1, date(2026, 9, 2)),
        (1, datetime(2026, 9, 1, tzinfo=UTC)),
        (1, "2026-09-01"),
    ],
)
def test_invalid_inputs_are_rejected(user_id: object, period: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        load_spending(None, user_id, period)  # type: ignore[arg-type]


def test_result_has_no_raw_ledger_records(ledger_session: Session) -> None:
    complete_owner(ledger_session)
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="posted",
        amount_cents=125,
        transaction_date=date(2026, 9, 8),
    )
    snapshot = load_spending(ledger_session, 1, PERIOD)
    payload = asdict(snapshot)
    assert set(payload) == {
        "period",
        "posted_cents",
        "pending_cents",
        "refreshed_at",
    }
    assert "transactions" not in payload
    assert type(payload["posted_cents"]) is int
    assert type(payload["pending_cents"]) is int
    now = datetime(2026, 9, 2, 16, 0, tzinfo=UTC)
    result = calculate_budget(10_000, snapshot, now=now)
    assert result.available_cents == 9_875
    assert result.pending_cents == 0
    assert result.stale is False


def test_integral_cents_accepts_exact_decimal_totals() -> None:
    assert _integral_cents(None) == 0
    assert _integral_cents(12) == 12
    assert _integral_cents(Decimal("12")) == 12
    assert _integral_cents(Decimal("12.0")) == 12
    with pytest.raises(ValueError):
        _integral_cents(Decimal("12.5"))
    with pytest.raises(TypeError):
        _integral_cents(12.0)


def test_month_end_keeps_december_9999() -> None:
    assert _month_end(date(9999, 12, 1)) == date(9999, 12, 31)


def test_uninitialized_item_blocks_without_month_rows(
    ledger_session: Session,
) -> None:
    add_user(ledger_session, 1)
    add_item(
        ledger_session,
        item_id="item-1",
        user_id=1,
        cursor=None,
        last_synced_at=None,
    )
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="other-month",
        amount_cents=400,
        transaction_date=date(2026, 8, 31),
    )
    with pytest.raises(SpendingUnavailable, match="Spending is unavailable"):
        load_spending(ledger_session, 1, PERIOD)


def test_load_spending_uses_one_select(
    ledger_engine: Engine, ledger_session: Session
) -> None:
    complete_owner(ledger_session)
    add_txn(
        ledger_session,
        item_id="item-1",
        transaction_id="posted",
        amount_cents=125,
        transaction_date=date(2026, 9, 8),
    )
    statements: list[str] = []

    def capture(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(ledger_engine, "before_cursor_execute", capture)
    try:
        snapshot = load_spending(ledger_session, 1, PERIOD)
    finally:
        event.remove(ledger_engine, "before_cursor_execute", capture)
    assert snapshot == SpendingSnapshot(PERIOD, 125, 0, NEW)
    selects = [
        statement
        for statement in statements
        if statement.lstrip()[:6].upper() == "SELECT"
    ]
    assert len(selects) == 1
