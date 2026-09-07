import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from test_plaid_sync import ScriptedProvider, load_item, load_txn, page, txn

from app import models
from app.db import Base
from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidNotReady, PlaidSyncMutation, PlaidUnavailable
from app.services.job_delivery import LeaseLost, RetryableJobError
from app.services.sync_job import SyncJobInput, make_sync_handler

ITEM_ID = "item-1"
RETRY = "Plaid sync is retryable."
UNAVAILABLE = "The Plaid provider is unavailable."
SECRET = "Authorization: Bearer secret-token"


@pytest.fixture()
def sync_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "sync-job.db"
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
def factory(sync_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=sync_engine, expire_on_commit=False)


@pytest.fixture()
def owned_item(factory: sessionmaker[Session]) -> str:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(
            PlaidItem(
                id=ITEM_ID,
                user_id=1,
                provider_item_id="provider-1",
                credential_ref="plaid-item-ref",
            )
        )
    return ITEM_ID


def dummy_factory() -> sessionmaker[Session]:
    return cast(sessionmaker[Session], object())


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"operation": "plaid_sync", "item_id": ITEM_ID}
    body.update(overrides)
    return body


def test_input_forbids_cursor_token_and_owner() -> None:
    SyncJobInput.model_validate(payload())
    extras = (
        payload(cursor="c1"),
        payload(token=SECRET),
        payload(owner="1"),
        payload(user_id=1),
        payload(item_id=""),
        payload(item_id="   "),
        payload(item_id="x" * 257),
        {"operation": "plaid_sync"},
        {"item_id": ITEM_ID, "operation": "chat"},
    )
    for body in extras:
        with pytest.raises(ValidationError):
            SyncJobInput.model_validate(body)


def test_missing_provider_fails_after_validation() -> None:
    handler = make_sync_handler(dummy_factory(), None)
    with pytest.raises(ValidationError):
        handler(payload(cursor="c1"), lambda: None)
    with pytest.raises(ValueError, match="unavailable") as caught:
        handler(payload(), lambda: None)
    assert str(caught.value) == UNAVAILABLE
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert SECRET not in str(caught.value)


def test_success_returns_source_and_count_only(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [page(added=(txn("txn-1"),), next_cursor="c1", has_more=False)]
    )
    handler = make_sync_handler(factory, provider)
    result = handler(payload(), lambda: None)
    assert result == {"source": "plaid_sandbox", "changed_count": 1}
    assert "cursor" not in result
    assert "token" not in result
    stored = load_txn(factory, owned_item, "txn-1")
    assert stored is not None
    assert load_item(factory, owned_item).cursor == "c1"


def test_retryable_errors_are_static_and_roll_back(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [
            page(added=(txn("txn-1"),), next_cursor="c1", has_more=True),
            PlaidUnavailable(),
        ]
    )
    handler = make_sync_handler(factory, provider)
    with pytest.raises(RetryableJobError) as caught:
        handler(payload(), lambda: None)
    assert str(caught.value) == RETRY
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert SECRET not in str(caught.value)
    assert load_item(factory, owned_item).cursor is None
    assert load_txn(factory, owned_item, "txn-1") is None
    for error in (PlaidNotReady(), PlaidUnavailable()):
        retry_handler = make_sync_handler(factory, ScriptedProvider([error]))
        with pytest.raises(RetryableJobError) as raised:
            retry_handler(payload(), lambda: None)
        assert str(raised.value) == RETRY
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
    exhausted = make_sync_handler(
        factory,
        ScriptedProvider(
            [PlaidSyncMutation(), PlaidSyncMutation(), PlaidSyncMutation()]
        ),
    )
    with pytest.raises(RetryableJobError) as raised:
        exhausted(payload(), lambda: None)
    assert str(raised.value) == RETRY
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_lease_lost_is_preserved(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [page(added=(txn("txn-1"),), next_cursor="c1", has_more=False)]
    )
    handler = make_sync_handler(factory, provider)

    def heartbeat() -> None:
        raise LeaseLost

    with pytest.raises(LeaseLost) as caught:
        handler(payload(), heartbeat)
    assert caught.value.__cause__ is None
    assert load_txn(factory, ITEM_ID, "txn-1") is None


def test_invalid_payload_does_not_call_provider(
    factory: sessionmaker[Session],
) -> None:
    provider = ScriptedProvider([])
    handler = make_sync_handler(factory, provider)
    with pytest.raises(ValidationError):
        handler(payload(token=SECRET), lambda: None)
    assert provider.calls == []
