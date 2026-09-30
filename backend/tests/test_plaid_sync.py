"""Test bounded Plaid Item sync application and rollback."""

import sqlite3
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from sqlalchemy import Connection, Engine, create_engine, delete, event, text
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.db import Base
from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidSyncMutation, PlaidUnavailable
from app.providers.plaid_contract import SyncPage, TransactionData
from app.services.plaid_sync import sync_item

ITEM_ERROR = "Plaid Item is missing or not owned"
PAGE_ERROR = "Plaid sync exceeded the page bound"
NOW = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)


class ScriptedProvider:
    def __init__(self, responses: list[SyncPage | BaseException]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str | None]] = []

    def sync_page(self, credential_ref: str, cursor: str | None) -> SyncPage:
        self.calls.append((credential_ref, cursor))
        if not self.responses:
            raise AssertionError("unexpected sync_page call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def txn(
    transaction_id: str,
    *,
    amount_cents: int = 100,
    pending: bool = False,
    pending_transaction_id: str | None = None,
    is_grocery: bool = True,
) -> TransactionData:
    return TransactionData(
        transaction_id=transaction_id,
        account_id="acct-1",
        amount_cents=amount_cents,
        currency="USD",
        transaction_date=date(2026, 9, 6),
        pending=pending,
        pending_transaction_id=pending_transaction_id,
        is_grocery=is_grocery,
        classification_version="plaid-pfc-v1",
    )


def page(
    *,
    added: tuple[TransactionData, ...] = (),
    modified: tuple[TransactionData, ...] = (),
    removed_ids: tuple[str, ...] = (),
    next_cursor: str = "c1",
    has_more: bool = False,
) -> SyncPage:
    return SyncPage(added, modified, removed_ids, next_cursor, has_more)


@pytest.fixture()
def sync_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "plaid-sync.db"
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
        session.add(models.User(id=2, display_name="Other"))
        session.add(
            PlaidItem(
                id="item-1",
                user_id=1,
                provider_item_id="provider-1",
                credential_ref="plaid-item-ref",
            )
        )
        session.add(
            PlaidItem(
                id="item-2",
                user_id=1,
                provider_item_id="provider-2",
                credential_ref="plaid-item-ref-2",
            )
        )
        session.add(
            PlaidItem(
                id="item-other",
                user_id=2,
                provider_item_id="provider-other",
                credential_ref="plaid-other-ref",
            )
        )
    return "item-1"


def clock() -> datetime:
    return NOW


def load_item(factory: sessionmaker[Session], item_id: str) -> PlaidItem:
    with factory() as session:
        stored = session.get(PlaidItem, item_id)
        assert stored is not None
        session.expunge(stored)
        return stored


def load_txn(
    factory: sessionmaker[Session], item_id: str, transaction_id: str
) -> PlaidTransaction | None:
    with factory() as session:
        stored = session.get(PlaidTransaction, (item_id, transaction_id))
        if stored is None:
            return None
        session.expunge(stored)
        return stored


def assert_utc(stored: datetime | None, expected: datetime) -> None:
    assert stored is not None
    if stored.tzinfo is None:
        assert stored == expected.replace(tzinfo=None)
    else:
        assert stored.astimezone(UTC) == expected


def test_two_page_success_applies_rows_and_final_cursor(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [
            page(added=(txn("txn-1"),), next_cursor="c1", has_more=True),
            page(added=(txn("txn-2"),), next_cursor="c2", has_more=False),
        ]
    )
    beats = 0

    def heartbeat() -> None:
        nonlocal beats
        beats += 1

    count = sync_item(factory, owned_item, provider, now=clock, heartbeat=heartbeat)
    assert count == 2
    assert beats == 4
    assert provider.calls == [
        ("plaid-item-ref", None),
        ("plaid-item-ref", "c1"),
    ]
    item = load_item(factory, owned_item)
    assert item.cursor == "c2"
    assert_utc(item.last_synced_at, NOW)
    first = load_txn(factory, owned_item, "txn-1")
    second = load_txn(factory, owned_item, "txn-2")
    assert first is not None
    assert second is not None
    assert first.account_id == "acct-1"
    assert first.amount_cents == 100
    assert first.currency == "USD"
    assert first.transaction_date == date(2026, 9, 6)
    assert first.pending is False
    assert first.pending_transaction_id is None
    assert first.is_grocery is True
    assert first.classification_version == "plaid-pfc-v1"


def test_page_two_failure_rolls_back_ledger_and_cursor(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [
            page(added=(txn("txn-1"),), next_cursor="c1", has_more=True),
            PlaidUnavailable(),
        ]
    )
    with pytest.raises(PlaidUnavailable):
        sync_item(factory, owned_item, provider, now=clock)
    item = load_item(factory, owned_item)
    assert item.cursor is None
    assert item.last_synced_at is None
    assert load_txn(factory, owned_item, "txn-1") is None


def test_mutation_restart_discards_first_page_changes(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [
            page(added=(txn("txn-old"),), next_cursor="discard", has_more=True),
            PlaidSyncMutation(),
            page(added=(txn("txn-new"),), next_cursor="final", has_more=False),
        ]
    )
    count = sync_item(factory, owned_item, provider, now=clock)
    assert count == 1
    assert [cursor for _, cursor in provider.calls] == [None, "discard", None]
    assert load_txn(factory, owned_item, "txn-old") is None
    stored = load_txn(factory, owned_item, "txn-new")
    assert stored is not None
    assert load_item(factory, owned_item).cursor == "final"


def test_mutation_restart_reuses_non_null_original_cursor(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    with factory.begin() as session:
        item = session.get(PlaidItem, owned_item)
        assert item is not None
        item.cursor = "orig"
    provider = ScriptedProvider(
        [
            page(added=(txn("txn-old"),), next_cursor="discard", has_more=True),
            PlaidSyncMutation(),
            page(added=(txn("txn-new"),), next_cursor="final", has_more=False),
        ]
    )
    count = sync_item(factory, owned_item, provider, now=clock)
    assert count == 1
    assert [cursor for _, cursor in provider.calls] == ["orig", "discard", "orig"]
    assert load_txn(factory, owned_item, "txn-old") is None
    stored = load_txn(factory, owned_item, "txn-new")
    assert stored is not None
    assert load_item(factory, owned_item).cursor == "final"


def test_bounded_mutation_and_page_loops(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    mutations = ScriptedProvider(
        [PlaidSyncMutation(), PlaidSyncMutation(), PlaidSyncMutation()]
    )
    with pytest.raises(PlaidSyncMutation):
        sync_item(factory, owned_item, mutations, now=clock, max_restarts=2)
    item = load_item(factory, owned_item)
    assert item.cursor is None
    assert item.last_synced_at is None
    assert [cursor for _, cursor in mutations.calls] == [None, None, None]
    pages = ScriptedProvider(
        [
            page(added=(txn("txn-1"),), next_cursor="c1", has_more=True),
            page(added=(txn("txn-2"),), next_cursor="c2", has_more=True),
        ]
    )
    with pytest.raises(ValueError) as raised:
        sync_item(factory, owned_item, pages, now=clock, max_pages=2)
    assert str(raised.value) == PAGE_ERROR
    assert load_txn(factory, owned_item, "txn-1") is None
    empty = ScriptedProvider([])
    invalid_bounds: tuple[dict[str, object], ...] = (
        {"user_id": True},
        {"max_pages": True},
        {"max_restarts": True},
        {"user_id": 0},
        {"max_pages": 0},
        {"max_pages": 21},
        {"max_restarts": -1},
        {"max_restarts": 4},
    )
    for kwargs in invalid_bounds:
        with pytest.raises(ValueError) as raised:
            sync_item(factory, owned_item, empty, now=clock, **kwargs)
        assert "MUST" in str(raised.value)
    assert empty.calls == []


def test_repeated_replay_state_is_idempotent(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    row = txn("txn-1", amount_cents=250)
    complete = page(added=(row,), modified=(), next_cursor="c-final")
    first = sync_item(factory, owned_item, ScriptedProvider([complete]), now=clock)
    later = datetime(2026, 9, 6, 16, 0, tzinfo=UTC)

    def later_clock() -> datetime:
        return later

    second = sync_item(
        factory, owned_item, ScriptedProvider([complete]), now=later_clock
    )
    assert first == 1
    assert second == 1
    stored = load_txn(factory, owned_item, "txn-1")
    assert stored is not None
    assert stored.amount_cents == 250
    item = load_item(factory, owned_item)
    assert item.cursor == "c-final"
    assert_utc(item.last_synced_at, later)


def test_pending_removal_and_posted_addition(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    with factory.begin() as session:
        session.add(
            PlaidTransaction(
                item_id=owned_item,
                transaction_id="txn-pending",
                account_id="acct-1",
                amount_cents=400,
                currency="USD",
                transaction_date=date(2026, 9, 6),
                pending=True,
                pending_transaction_id=None,
                is_grocery=True,
                classification_version="plaid-pfc-v1",
            )
        )
    provider = ScriptedProvider(
        [
            page(
                added=(
                    txn(
                        "txn-posted",
                        amount_cents=400,
                        pending_transaction_id="txn-pending",
                    ),
                ),
                removed_ids=("txn-pending",),
                next_cursor="posted",
            )
        ]
    )
    count = sync_item(factory, owned_item, provider, now=clock)
    assert count == 2
    assert load_txn(factory, owned_item, "txn-pending") is None
    posted = load_txn(factory, owned_item, "txn-posted")
    assert posted is not None
    assert posted.pending is False
    assert posted.pending_transaction_id == "txn-pending"
    assert posted.amount_cents == 400


def test_refunds_preserve_signed_cents(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider(
        [page(added=(txn("txn-refund", amount_cents=-1299),), next_cursor="r1")]
    )
    count = sync_item(factory, owned_item, provider, now=clock)
    assert count == 1
    stored = load_txn(factory, owned_item, "txn-refund")
    assert stored is not None
    assert stored.amount_cents == -1299
    assert stored.currency == "USD"


def test_sync_does_not_overwrite_other_items(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    with factory.begin() as session:
        session.add(
            PlaidTransaction(
                item_id="item-2",
                transaction_id="txn-1",
                account_id="acct-2",
                amount_cents=50,
                currency="USD",
                transaction_date=date(2026, 9, 5),
                pending=False,
                is_grocery=False,
                classification_version="other-v1",
            )
        )
    provider = ScriptedProvider(
        [page(modified=(txn("txn-1", amount_cents=99),), next_cursor="own")]
    )
    count = sync_item(factory, owned_item, provider, now=clock)
    assert count == 1
    owned = load_txn(factory, owned_item, "txn-1")
    other = load_txn(factory, "item-2", "txn-1")
    assert owned is not None
    assert owned.amount_cents == 99
    assert other is not None
    assert other.amount_cents == 50
    assert other.account_id == "acct-2"
    assert other.classification_version == "other-v1"
    assert load_item(factory, "item-2").cursor is None


def test_ownership_check_uses_static_error(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider([])
    beats = 0

    def heartbeat() -> None:
        nonlocal beats
        beats += 1

    with pytest.raises(ValueError) as missing:
        sync_item(factory, "missing", provider, now=clock, heartbeat=heartbeat)
    with pytest.raises(ValueError) as foreign:
        sync_item(
            factory,
            "item-other",
            provider,
            user_id=1,
            now=clock,
            heartbeat=heartbeat,
        )
    assert str(missing.value) == ITEM_ERROR
    assert str(foreign.value) == ITEM_ERROR
    assert beats == 0
    assert provider.calls == []
    assert load_item(factory, "item-other").cursor is None


def test_invalid_now_rolls_back_ledger_and_cursor(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider([page(added=(txn("txn-1"),), next_cursor="c-now")])

    def bad_now() -> datetime:
        return datetime(2026, 9, 6, 15, 0)  # noqa: DTZ001

    with pytest.raises(ValueError) as raised:
        sync_item(factory, owned_item, provider, now=bad_now)
    assert str(raised.value) == "now MUST be a timezone-aware datetime"
    item = load_item(factory, owned_item)
    assert item.cursor is None
    assert item.last_synced_at is None
    assert load_txn(factory, owned_item, "txn-1") is None


def test_final_heartbeat_rolls_back_ledger_and_cursor(
    factory: sessionmaker[Session], owned_item: str
) -> None:
    provider = ScriptedProvider([page(added=(txn("txn-1"),), next_cursor="c-hb")])
    beats = 0

    def heartbeat() -> None:
        nonlocal beats
        beats += 1
        if beats == 3:
            raise RuntimeError("heartbeat failed")

    with pytest.raises(RuntimeError):
        sync_item(factory, owned_item, provider, now=clock, heartbeat=heartbeat)
    item = load_item(factory, owned_item)
    assert item.cursor is None
    assert item.last_synced_at is None
    assert load_txn(factory, owned_item, "txn-1") is None


@pytest.fixture()
def postgres_plaid() -> Iterator[tuple[Engine, int, str]]:
    url = require_test_database_url()
    engine = create_engine(
        url,
        connect_args={"options": "-c statement_timeout=15000 -c lock_timeout=10000"},
    )
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("The Item concurrency test requires PostgreSQL.")
    user_id = uuid4().int % 1_000_000_000 + 1_000_000_000
    item_id = str(uuid4())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(models.User(id=user_id, display_name="plaid-sync-concurrency"))
        session.add(
            PlaidItem(
                id=item_id,
                user_id=user_id,
                provider_item_id=f"provider-{item_id}",
                credential_ref="plaid-item-ref",
            )
        )
    try:
        yield engine, user_id, item_id
    finally:
        with factory.begin() as session:
            session.execute(
                delete(PlaidTransaction).where(PlaidTransaction.item_id == item_id)
            )
            session.execute(delete(PlaidItem).where(PlaidItem.id == item_id))
            session.execute(delete(models.User).where(models.User.id == user_id))
        engine.dispose()


def _wait_for_lock_waiter(engine: Engine, pid: int) -> None:
    deadline = time.monotonic() + 5
    query = text(
        "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE NOT granted AND pid = :pid)"
    )
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            waiting = connection.execute(query, {"pid": pid}).scalar()
            if waiting:
                return
        time.sleep(0.05)
    raise AssertionError("second sync did not wait on the Item lock")


def test_postgres_concurrent_item_syncs_serialize(
    postgres_plaid: tuple[Engine, int, str],
) -> None:
    engine, user_id, item_id = postgres_plaid
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    started = Event()
    release = Event()
    pid_ready = Event()
    second_pids: list[int] = []
    second_cursors: list[str | None] = []

    class FirstProvider:
        def sync_page(self, credential_ref: str, cursor: str | None) -> SyncPage:
            started.set()
            if not release.wait(timeout=10):
                raise AssertionError("first sync was not released")
            return page(added=(txn("txn-a"),), next_cursor="cursor-a")

    class SecondProvider:
        def sync_page(self, credential_ref: str, cursor: str | None) -> SyncPage:
            second_cursors.append(cursor)
            return page(added=(txn("txn-b"),), next_cursor="cursor-b")

    def run_first() -> int:
        return sync_item(factory, item_id, FirstProvider(), user_id=user_id, now=clock)

    def run_second() -> int:
        connection = engine.connect()
        try:
            pid = connection.execute(text("SELECT pg_backend_pid()")).scalar()
            if type(pid) is not int:
                raise AssertionError("PostgreSQL did not return a backend pid")
            connection.commit()
            second_pids.append(pid)
            pid_ready.set()
            bound = sessionmaker(bind=connection, expire_on_commit=False)
            return sync_item(
                bound, item_id, SecondProvider(), user_id=user_id, now=clock
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(run_first)
        try:
            assert started.wait(timeout=10)
            second_future = executor.submit(run_second)
            assert pid_ready.wait(timeout=10)
            _wait_for_lock_waiter(engine, second_pids[0])
            release.set()
            assert first_future.result(timeout=20) == 1
            assert second_future.result(timeout=20) == 1
        finally:
            release.set()
    assert second_cursors == ["cursor-a"]
    assert load_txn(factory, item_id, "txn-a") is not None
    assert load_txn(factory, item_id, "txn-b") is not None
    assert load_item(factory, item_id).cursor == "cursor-b"
