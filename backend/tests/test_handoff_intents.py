"""Test shopping-list handoff intent cache and ownership rules."""

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.db import Base
from app.handoff_models import ShoppingHandoff
from app.services.handoff_contract import INVALID_CACHED_URL, STORE_FAILED
from app.services.handoff_intents import (
    HandoffNotFound,
    HandoffView,
    prepare_handoff,
    read_handoff,
    validated_cached_payload,
)
from app.services.shopping_payload import shopping_payload_hash

NOW = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)
SUCCESS_URL = "https://www.instacart.com/store/lists/demo"
UNSAFE_URL = "https://example.com/store/lists/demo"
SENTINEL = "SECRET_DB_TOKEN"
VIEW_FIELDS = {
    "id",
    "state",
    "attempts",
    "url",
    "error_code",
    "expires_at",
    "retry_allowed",
}


def shopping_payload(quantity: int = 240) -> dict[str, object]:
    return {
        "title": "FEWIA grocery plan",
        "link_type": "shopping_list",
        "expires_in": 7,
        "line_items": [
            {
                "name": "black beans",
                "line_item_measurements": [{"quantity": quantity, "unit": "g"}],
            }
        ],
    }


def assert_utc(stored: datetime | None, expected: datetime) -> None:
    assert stored is not None
    if stored.tzinfo is None:
        assert stored == expected.replace(tzinfo=None)
    else:
        assert stored.astimezone(UTC) == expected


@pytest.fixture()
def handoff_engine(tmp_path: Path) -> Iterator[Engine]:
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'handoff.db'}",
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

    tables = [models.User.__table__, ShoppingHandoff.__table__]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def factory(handoff_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=handoff_engine, expire_on_commit=False)


@pytest.fixture()
def owners(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))


@pytest.fixture()
def postgres_factory() -> Iterator[sessionmaker[Session]]:
    url = require_test_database_url()
    schema = f"handoff_{uuid4().hex}"
    admin = create_engine(url)
    if admin.dialect.name != "postgresql":
        admin.dispose()
        pytest.fail("The handoff concurrency test requires PostgreSQL.")
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin.dispose()
    engine = create_engine(
        url,
        pool_size=4,
        max_overflow=2,
        connect_args={
            "options": (
                f"-csearch_path={schema} -c statement_timeout=15000"
                " -c lock_timeout=10000"
            )
        },
    )
    tables = [models.User.__table__, ShoppingHandoff.__table__]
    Base.metadata.create_all(engine, tables=tables)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def load_row(factory: sessionmaker[Session], handoff_id: str) -> ShoppingHandoff:
    with factory() as session:
        stored = session.get(ShoppingHandoff, handoff_id)
        assert stored is not None
        session.expunge(stored)
        return stored


def test_view_exposes_safe_fields_only() -> None:
    assert set(HandoffView.__dataclass_fields__) == VIEW_FIELDS
    assert HandoffView.__dataclass_params__.frozen is True
    assert str(HandoffNotFound()) == "shopping handoff is missing"


def test_prepare_inserts_cached_copy_and_rejects_mutation(
    factory: sessionmaker[Session], owners: None
) -> None:
    payload = shopping_payload()
    view = prepare_handoff(factory, 1, payload, now=NOW)
    payload["title"] = "mutated"
    nested = payload["line_items"]
    assert isinstance(nested, list)
    nested.clear()
    stored = load_row(factory, view.id)
    assert stored.user_id == 1
    assert stored.request_hash == shopping_payload_hash(shopping_payload())
    assert stored.request_payload == shopping_payload()
    assert stored.state == "prepared"
    assert stored.attempts == 0
    assert view.state == "prepared"
    assert view.attempts == 0
    assert view.url is None
    assert view.error_code is None
    assert view.expires_at is None
    assert view.retry_allowed is False
    again = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    assert again.id == view.id
    assert again.state == "prepared"


def test_prepare_is_unique_per_owner(
    factory: sessionmaker[Session], owners: None
) -> None:
    first = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    second = prepare_handoff(factory, 2, shopping_payload(), now=NOW)
    assert first.id != second.id
    other = prepare_handoff(factory, 1, shopping_payload(241), now=NOW)
    assert other.id != first.id


def test_read_is_owner_scoped(factory: sessionmaker[Session], owners: None) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    assert read_handoff(factory, 1, view.id, now=NOW) == view
    assert read_handoff(factory, 2, view.id, now=NOW) is None
    assert read_handoff(factory, 1, str(uuid4()), now=NOW) is None
    assert read_handoff(factory, 1, "", now=NOW) is None


@pytest.mark.parametrize("user_id", [True, False, 0, -1, 1.0, "1"])
def test_owner_must_be_a_positive_int(
    factory: sessionmaker[Session], owners: None, user_id: object
) -> None:
    with pytest.raises(ValueError, match="user_id MUST be a positive integer"):
        prepare_handoff(factory, user_id, shopping_payload(), now=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="user_id MUST be a positive integer"):
        read_handoff(factory, user_id, "x", now=NOW)  # type: ignore[arg-type]


def test_naive_clock_is_rejected(factory: sessionmaker[Session], owners: None) -> None:
    naive = datetime(2026, 9, 6, 15, 0)  # noqa: DTZ001
    with pytest.raises(ValueError, match="now MUST be a timezone-aware datetime"):
        prepare_handoff(factory, 1, shopping_payload(), now=naive)
    with pytest.raises(ValueError, match="now MUST be a timezone-aware datetime"):
        read_handoff(factory, 1, "x", now=naive)


def test_payload_mismatch_does_not_overwrite(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        tampered = shopping_payload(241)
        row.request_payload = tampered
    with pytest.raises(
        ValueError, match="shopping handoff payload does not match the cached plan"
    ):
        prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    stored = load_row(factory, view.id)
    assert stored.request_payload == shopping_payload(241)
    assert stored.request_hash == shopping_payload_hash(shopping_payload())


def test_stale_dispatch_read_becomes_uncertain(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        row.state = "dispatching"
        row.attempt_token = "attempt-1"
        row.attempts = 1
        row.started_at = NOW
        row.url = SUCCESS_URL
    fresh = read_handoff(factory, 1, view.id, now=NOW + timedelta(seconds=120))
    assert fresh is not None
    assert fresh.state == "dispatching"
    assert fresh.retry_allowed is False
    assert fresh.url is None
    stale = read_handoff(factory, 1, view.id, now=NOW + timedelta(seconds=121))
    assert stale is not None
    assert stale.state == "uncertain"
    assert stale.error_code == "stale_dispatch"
    assert stale.retry_allowed is True
    assert stale.url is None
    stored = load_row(factory, view.id)
    assert stored.attempt_token == "attempt-1"
    assert stored.attempts == 1
    assert stored.request_hash == shopping_payload_hash(shopping_payload())
    assert stored.user_id == 1


def test_expired_success_hides_url(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    started = NOW - timedelta(days=8)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        row.state = "succeeded"
        row.attempts = 1
        row.started_at = started
        row.expires_at = started + timedelta(days=7)
        row.url = SUCCESS_URL
    live = read_handoff(factory, 1, view.id, now=started + timedelta(days=6))
    assert live is not None
    assert live.url == SUCCESS_URL
    assert live.retry_allowed is False
    expired = read_handoff(factory, 1, view.id, now=NOW)
    assert expired is not None
    assert expired.state == "succeeded"
    assert expired.url is None
    assert expired.retry_allowed is True
    assert expired.expires_at is None


def test_sqlite_naive_started_at_is_utc(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        row.state = "dispatching"
        row.attempt_token = "attempt-naive"
        row.attempts = 1
        row.started_at = NOW.replace(tzinfo=None)
    stale = prepare_handoff(
        factory, 1, shopping_payload(), now=NOW + timedelta(seconds=121)
    )
    assert stale.id == view.id
    assert stale.state == "uncertain"
    assert stale.error_code == "stale_dispatch"


def test_unknown_user_does_not_insert(
    factory: sessionmaker[Session], owners: None
) -> None:
    with pytest.raises(ValueError, match=STORE_FAILED) as raised:
        prepare_handoff(factory, 9, shopping_payload(), now=NOW)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    rendered = str(raised.value) + repr(raised.value)
    assert "FOREIGN" not in rendered
    assert SENTINEL not in rendered


def test_sqlite_prepare_is_sequential_and_unique(
    factory: sessionmaker[Session], owners: None
) -> None:
    first = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    second = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    assert first.id == second.id
    with factory() as session:
        rows = session.query(ShoppingHandoff).filter_by(user_id=1).all()
        assert len(rows) == 1


def test_postgres_concurrent_prepare_dedups(
    postgres_factory: sessionmaker[Session],
) -> None:
    with postgres_factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))
    owned = prepare_handoff(postgres_factory, 1, shopping_payload(), now=NOW)
    start = Barrier(2)
    bind = postgres_factory.kw["bind"]
    assert bind is not None
    first = sessionmaker(bind=bind, expire_on_commit=False)
    second = sessionmaker(bind=bind, expire_on_commit=False)

    def submit(owned_factory: sessionmaker[Session]) -> str:
        start.wait(timeout=10)
        return prepare_handoff(owned_factory, 1, shopping_payload(), now=NOW).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, first), executor.submit(submit, second)]
        ids = [future.result(timeout=20) for future in futures]
    assert ids[0] == ids[1] == owned.id
    other = prepare_handoff(postgres_factory, 2, shopping_payload(), now=NOW)
    assert other.id not in ids
    with postgres_factory() as session:
        rows = session.query(ShoppingHandoff).filter_by(user_id=1).all()
        assert len(rows) == 1


def test_intents_reexport_validates_cached_payload() -> None:
    payload = shopping_payload()
    digest = shopping_payload_hash(payload)
    assert validated_cached_payload(payload, digest) == payload


def test_cached_true_quantity_does_not_match(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        tampered = shopping_payload()
        items = tampered["line_items"]
        assert isinstance(items, list)
        line = items[0]
        assert isinstance(line, dict)
        measures = line["line_item_measurements"]
        assert isinstance(measures, list)
        measure = measures[0]
        assert isinstance(measure, dict)
        measure["quantity"] = True
        row.request_payload = tampered
    with pytest.raises(
        ValueError, match="shopping handoff payload does not match the cached plan"
    ):
        prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    stored = load_row(factory, view.id)
    stored_items = stored.request_payload["line_items"]
    assert isinstance(stored_items, list)
    stored_line = stored_items[0]
    assert isinstance(stored_line, dict)
    stored_measures = stored_line["line_item_measurements"]
    assert isinstance(stored_measures, list)
    stored_measure = stored_measures[0]
    assert isinstance(stored_measure, dict)
    assert stored_measure["quantity"] is True
    assert stored.request_hash == shopping_payload_hash(shopping_payload())


def test_unsafe_cached_success_url_is_not_returned(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        row.state = "succeeded"
        row.attempts = 1
        row.started_at = NOW
        row.expires_at = NOW + timedelta(days=7)
        row.url = UNSAFE_URL
    shown = read_handoff(factory, 1, view.id, now=NOW)
    assert shown is not None
    assert shown.url is None
    assert shown.state == "uncertain"
    assert shown.error_code == INVALID_CACHED_URL
    assert shown.retry_allowed is True
    stored = load_row(factory, view.id)
    assert stored.url is None
    assert stored.state == "uncertain"
    assert stored.request_payload == shopping_payload()
    assert stored.request_hash == shopping_payload_hash(shopping_payload())


def test_raw_integrity_error_sentinel_has_no_chain(
    factory: sessionmaker[Session], owners: None
) -> None:
    def explode(mapper: object, connection: object, target: ShoppingHandoff) -> None:
        del mapper, connection, target
        raise IntegrityError("INSERT", {"token": SENTINEL}, Exception(SENTINEL))

    event.listen(ShoppingHandoff, "before_insert", explode)
    try:
        with pytest.raises(ValueError, match=STORE_FAILED) as raised:
            prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    finally:
        event.remove(ShoppingHandoff, "before_insert", explode)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    rendered = str(raised.value) + repr(raised.value)
    assert SENTINEL not in rendered


def test_foreign_read_is_none_and_readonly(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    assert read_handoff(factory, 2, view.id, now=NOW) is None
    stored = load_row(factory, view.id)
    assert stored.user_id == 1
    assert stored.state == "prepared"
    assert stored.request_payload == shopping_payload()
    assert stored.url is None
