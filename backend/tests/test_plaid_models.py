"""Test the Plaid ledger metadata and SQLite constraints."""

import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Connection,
    Date,
    DateTime,
    Engine,
    ForeignKeyConstraint,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base


@pytest.fixture()
def plaid_engine() -> Iterator[Engine]:
    from app import plaid_models

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
        plaid_models.PlaidItem.__table__,
        plaid_models.PlaidTransaction.__table__,
    ]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def plaid_session(plaid_engine: Engine) -> Iterator[Session]:
    connection: Connection = plaid_engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection)
    try:
        yield test_session
    finally:
        test_session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def test_plaid_metadata_has_expected_columns_and_types() -> None:
    from app import plaid_models

    item = plaid_models.PlaidItem.__table__
    transaction = plaid_models.PlaidTransaction.__table__
    assert isinstance(item.c.id.type, String)
    assert item.c.id.type.length == 36
    assert isinstance(item.c.last_synced_at.type, DateTime)
    assert item.c.last_synced_at.type.timezone is True
    assert isinstance(transaction.c.amount_cents.type, BigInteger)
    assert isinstance(transaction.c.currency.type, Text)
    assert isinstance(transaction.c.transaction_date.type, Date)
    assert isinstance(transaction.c.pending.type, Boolean)
    assert isinstance(transaction.c.item_id.type, String)


def test_plaid_constraints_and_indexes_match_the_ledger_contract() -> None:
    from app import plaid_models

    item = plaid_models.PlaidItem.__table__
    transaction = plaid_models.PlaidTransaction.__table__
    assert {"plaid_items", "plaid_transactions"} <= set(Base.metadata.tables)
    assert [column.name for column in transaction.primary_key.columns] == [
        "item_id",
        "transaction_id",
    ]
    foreign_keys = {
        (foreign_key.parent.name, foreign_key.target_fullname)
        for constraint in transaction.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for foreign_key in constraint.elements
    }
    assert ("item_id", "plaid_items.id") in foreign_keys
    checks = [c for c in transaction.constraints if isinstance(c, CheckConstraint)]
    assert any("currency = 'USD'" in str(check.sqltext) for check in checks)
    index = next(
        index
        for index in transaction.indexes
        if index.name == "ix_plaid_transactions_item_date_pending"
    )
    assert [column.name for column in index.columns] == [
        "item_id",
        "transaction_date",
        "pending",
    ]
    assert "merchant_name" not in transaction.columns
    assert "raw_response" not in transaction.columns
    assert any(
        constraint.name == "uq_plaid_items_provider_item_id"
        for constraint in item.constraints
    )


def test_signed_usd_refund_round_trips_with_composite_identity(
    plaid_session: Session,
) -> None:
    from app.plaid_models import PlaidItem, PlaidTransaction

    item = PlaidItem(
        user_id=1,
        provider_item_id="sandbox-item",
        credential_ref="plaid-item-ref",
    )
    plaid_session.add(models.User(id=1, display_name="Test user"))
    plaid_session.add(item)
    plaid_session.flush()
    refund = PlaidTransaction(
        item_id=item.id,
        transaction_id="sandbox-refund",
        account_id="sandbox-account",
        amount_cents=-1299,
        currency="USD",
        transaction_date=date(2026, 9, 6),
        pending=False,
        is_grocery=True,
        classification_version="v1",
    )
    plaid_session.add(refund)
    plaid_session.flush()
    stored = plaid_session.get(PlaidTransaction, (item.id, "sandbox-refund"))
    assert stored is not None
    assert stored.amount_cents == -1299
    assert stored.currency == "USD"


def test_plaid_foreign_key_and_currency_constraints_reject_invalid_rows(
    plaid_session: Session,
) -> None:
    from app.plaid_models import PlaidItem, PlaidTransaction

    with pytest.raises(IntegrityError):
        with plaid_session.begin_nested():
            plaid_session.add(
                PlaidItem(
                    user_id=999,
                    provider_item_id="orphan-item",
                    credential_ref="plaid-item-ref",
                )
            )
            plaid_session.flush()
    plaid_session.add(models.User(id=1, display_name="Test user"))
    plaid_session.add(
        PlaidItem(
            id="item-1",
            user_id=1,
            provider_item_id="valid-item",
            credential_ref="plaid-item-ref",
        )
    )
    plaid_session.flush()
    with pytest.raises(IntegrityError):
        with plaid_session.begin_nested():
            plaid_session.add(
                PlaidTransaction(
                    item_id="item-1",
                    transaction_id="invalid-currency",
                    account_id="account-1",
                    amount_cents=100,
                    currency="CAD",
                    transaction_date=date(2026, 9, 6),
                    pending=False,
                    is_grocery=False,
                    classification_version="v1",
                )
            )
            plaid_session.flush()
