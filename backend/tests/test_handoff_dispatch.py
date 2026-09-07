"""Test Instacart development shopping-list handoff dispatch."""

import os
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.db import Base
from app.handoff_models import ShoppingHandoff
from app.providers.instacart import InstacartRejected, InstacartUncertain
from app.services.handoff_contract import PAYLOAD_MISMATCH
from app.services.handoff_dispatch import _finish, dispatch_handoff
from app.services.handoff_intents import HandoffNotFound, HandoffView, prepare_handoff
from tests.test_handoff_intents import (
    NOW,
    SUCCESS_URL,
    UNSAFE_URL,
    VIEW_FIELDS,
    assert_utc,
    load_row,
    shopping_payload,
)

RETRY_URL = "https://www.instacart.com/store/lists/retry"


class FakeProvider:
    def __init__(self, outcome: str | BaseException, *, nest: bool = False) -> None:
        self.outcome = outcome
        self.nest = nest
        self.payloads: list[dict[str, object]] = []
        self.during: ShoppingHandoff | None = None
        self.nested: HandoffView | None = None
        self.factory: sessionmaker[Session] | None = None
        self.handoff_id: str | None = None
        self._lock = Lock()

    def bind(self, factory: sessionmaker[Session], handoff_id: str) -> None:
        self.factory = factory
        self.handoff_id = handoff_id

    def create_link(self, payload: dict[str, object]) -> str:
        with self._lock:
            self.payloads.append(payload)
            count = len(self.payloads)
        if self.factory is not None and self.handoff_id is not None:
            self.during = load_row(self.factory, self.handoff_id)
            if self.nest and count == 1:
                self.nested = dispatch_handoff(
                    self.factory, self, 1, self.handoff_id, now=lambda: NOW
                )
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FailCommitFactory:
    def __init__(self, inner: sessionmaker[Session], fail_on: int) -> None:
        self._inner = inner
        self._fail_on = fail_on
        self.commits = 0

    def begin(self) -> "_FailBegin":
        return _FailBegin(self)


class _FailBegin:
    def __init__(self, owner: FailCommitFactory) -> None:
        self._owner = owner
        self._cm = owner._inner.begin()

    def __enter__(self) -> Session:
        session = self._cm.__enter__()
        owner = self._owner

        def _fail(target: Session) -> None:
            del target
            owner.commits += 1
            if owner.commits == owner._fail_on:
                raise RuntimeError("forced commit failure")

        event.listen(session, "before_commit", _fail, once=True)
        return session

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        self._cm.__exit__(exc_type, exc, tb)


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
    url = os.environ.get("FEWIA_JOB_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set FEWIA_JOB_TEST_DATABASE_URL to an isolated migrated PostgreSQL."
        )
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


def test_commit_before_post_caches_success(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL)
    provider.bind(factory, view.id)
    shown = dispatch_handoff(factory, provider, 1, view.id, now=lambda: NOW)
    assert shown.state == "succeeded"
    assert shown.url == SUCCESS_URL
    assert shown.attempts == 1
    assert shown.retry_allowed is False
    assert shown.error_code is None
    assert provider.during is not None
    assert provider.during.state == "dispatching"
    assert provider.during.attempts == 1
    assert provider.during.retry_authorized_at is None
    assert provider.during.attempt_token is not None
    stored = load_row(factory, view.id)
    assert stored.state == "succeeded"
    assert stored.retry_authorized_at is None
    assert_utc(stored.started_at, NOW)
    cached = dispatch_handoff(factory, provider, 1, view.id, now=lambda: NOW)
    assert cached.url == SUCCESS_URL
    assert cached.state == "succeeded"
    assert len(provider.payloads) == 1
    assert provider.payloads[0] == shopping_payload()


def test_rejected_is_failed_and_timeout_is_uncertain(
    factory: sessionmaker[Session], owners: None
) -> None:
    rejected_view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    rejected = FakeProvider(InstacartRejected())
    failed = dispatch_handoff(factory, rejected, 1, rejected_view.id, now=lambda: NOW)
    assert failed.state == "failed"
    assert failed.error_code == "instacart_rejected"
    assert failed.retry_allowed is True
    assert failed.url is None
    replay = dispatch_handoff(factory, rejected, 1, rejected_view.id, now=lambda: NOW)
    assert replay.state == "failed"
    assert len(rejected.payloads) == 1
    timeout_view = prepare_handoff(factory, 1, shopping_payload(241), now=NOW)
    timeout = FakeProvider(InstacartUncertain())
    uncertain = dispatch_handoff(factory, timeout, 1, timeout_view.id, now=lambda: NOW)
    assert uncertain.state == "uncertain"
    assert uncertain.error_code == "instacart_uncertain"
    assert uncertain.retry_allowed is True
    assert uncertain.url is None
    again = dispatch_handoff(factory, timeout, 1, timeout_view.id, now=lambda: NOW)
    assert again.state == "uncertain"
    assert len(timeout.payloads) == 1


def test_in_flight_dispatch_is_not_replayed(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL, nest=True)
    provider.bind(factory, view.id)
    shown = dispatch_handoff(factory, provider, 1, view.id, now=lambda: NOW)
    assert shown.state == "succeeded"
    assert len(provider.payloads) == 1
    assert provider.nested is not None
    assert provider.nested.state == "dispatching"
    assert provider.nested.retry_allowed is False
    assert provider.nested.url is None


@pytest.mark.parametrize("expected", [True, False, 0, 1.0, "0", None])
def test_retry_requires_strict_int_expected_attempt(
    factory: sessionmaker[Session], owners: None, expected: object
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL)
    shown = dispatch_handoff(
        factory,
        provider,
        1,
        view.id,
        retry=True,
        expected_attempt=expected,  # type: ignore[arg-type]
        now=lambda: NOW,
    )
    assert shown.state == "prepared"
    assert provider.payloads == []


def test_explicit_retry_posts_once_and_sets_retry_clock(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    failed = dispatch_handoff(
        factory,
        FakeProvider(InstacartRejected()),
        1,
        view.id,
        now=lambda: NOW,
    )
    assert failed.state == "failed"
    assert failed.attempts == 1
    retry_at = NOW + timedelta(minutes=1)
    provider = FakeProvider(RETRY_URL)
    shown = dispatch_handoff(
        factory,
        provider,
        1,
        view.id,
        retry=True,
        expected_attempt=1,
        now=lambda: retry_at,
    )
    assert shown.state == "succeeded"
    assert shown.url == RETRY_URL
    assert shown.attempts == 2
    stored = load_row(factory, view.id)
    assert_utc(stored.retry_authorized_at, retry_at)
    duplicate = dispatch_handoff(
        factory,
        provider,
        1,
        view.id,
        retry=True,
        expected_attempt=1,
        now=lambda: retry_at,
    )
    matching = dispatch_handoff(
        factory,
        provider,
        1,
        view.id,
        retry=True,
        expected_attempt=2,
        now=lambda: retry_at,
    )
    assert duplicate.state == "succeeded"
    assert matching.state == "succeeded"
    assert matching.retry_allowed is False
    assert len(provider.payloads) == 1


def test_stale_dispatch_retries_only_when_explicit(
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
    later = NOW + timedelta(seconds=121)
    provider = FakeProvider(SUCCESS_URL)
    blocked = dispatch_handoff(factory, provider, 1, view.id, now=lambda: later)
    assert blocked.state == "uncertain"
    assert blocked.error_code == "stale_dispatch"
    assert blocked.retry_allowed is True
    assert provider.payloads == []
    retried = dispatch_handoff(
        factory,
        provider,
        1,
        view.id,
        retry=True,
        expected_attempt=1,
        now=lambda: later,
    )
    assert retried.state == "succeeded"
    assert retried.url == SUCCESS_URL
    assert len(provider.payloads) == 1


def test_expired_success_retries_only_when_explicit(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    first = FakeProvider(SUCCESS_URL)
    dispatch_handoff(factory, first, 1, view.id, now=lambda: NOW)
    started = NOW - timedelta(days=8)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        row.started_at = started
        row.expires_at = started + timedelta(days=7)
    expired = dispatch_handoff(factory, first, 1, view.id, now=lambda: NOW)
    assert expired.state == "succeeded"
    assert expired.url is None
    assert expired.retry_allowed is True
    assert len(first.payloads) == 1
    retry_provider = FakeProvider(RETRY_URL)
    retried = dispatch_handoff(
        factory,
        retry_provider,
        1,
        view.id,
        retry=True,
        expected_attempt=1,
        now=lambda: NOW,
    )
    assert retried.state == "succeeded"
    assert retried.url == RETRY_URL
    assert len(retry_provider.payloads) == 1
    assert_utc(load_row(factory, view.id).retry_authorized_at, NOW)


def test_unsafe_url_and_tampered_payload_are_blocked(
    factory: sessionmaker[Session], owners: None
) -> None:
    unsafe_view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    unsafe = FakeProvider(UNSAFE_URL)
    blocked = dispatch_handoff(factory, unsafe, 1, unsafe_view.id, now=lambda: NOW)
    assert blocked.state == "uncertain"
    assert blocked.url is None
    assert blocked.error_code == "instacart_uncertain"
    assert blocked.retry_allowed is True
    assert len(unsafe.payloads) == 1
    stored_unsafe = load_row(factory, unsafe_view.id)
    assert stored_unsafe.url is None
    tampered_view = prepare_handoff(factory, 1, shopping_payload(241), now=NOW)
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, tampered_view.id)
        assert row is not None
        row.request_payload = shopping_payload(242)
    tampered = FakeProvider(SUCCESS_URL)
    with pytest.raises(ValueError, match=PAYLOAD_MISMATCH):
        dispatch_handoff(factory, tampered, 1, tampered_view.id, now=lambda: NOW)
    assert tampered.payloads == []
    stored = load_row(factory, tampered_view.id)
    assert stored.state == "prepared"
    assert stored.attempts == 0
    assert stored.request_payload == shopping_payload(242)


def test_owner_isolation_and_public_view_fields(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL)
    with pytest.raises(HandoffNotFound):
        dispatch_handoff(factory, provider, 2, view.id, now=lambda: NOW)
    with pytest.raises(HandoffNotFound):
        dispatch_handoff(factory, provider, 1, str(uuid4()), now=lambda: NOW)
    with pytest.raises(ValueError, match="retry MUST be a boolean"):
        dispatch_handoff(
            factory,
            provider,
            1,
            view.id,
            retry=1,  # type: ignore[arg-type]
            now=lambda: NOW,
        )
    assert provider.payloads == []
    assert load_row(factory, view.id).state == "prepared"
    shown = dispatch_handoff(factory, provider, 1, view.id, now=lambda: NOW)
    assert set(HandoffView.__dataclass_fields__) == VIEW_FIELDS
    assert HandoffView.__dataclass_params__.frozen is True
    rendered = f"{shown!s}{shown!r}"
    stored = load_row(factory, view.id)
    assert stored.attempt_token is not None
    assert stored.attempt_token not in rendered
    assert "request_payload" not in HandoffView.__dataclass_fields__
    assert "attempt_token" not in HandoffView.__dataclass_fields__
    assert "black beans" not in rendered
    assert shown.error_code is None


def test_claim_commit_failure_does_not_post(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL)
    failing = FailCommitFactory(factory, 1)
    with pytest.raises(RuntimeError, match="forced commit failure"):
        dispatch_handoff(
            failing,  # type: ignore[arg-type]
            provider,
            1,
            view.id,
            now=lambda: NOW,
        )
    assert provider.payloads == []
    stored = load_row(factory, view.id)
    assert stored.state == "prepared"
    assert stored.attempts == 0
    assert stored.retry_authorized_at is None


def test_finish_commit_failure_leaves_dispatching_without_replay(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL)
    failing = FailCommitFactory(factory, 2)
    with pytest.raises(RuntimeError, match="forced commit failure"):
        dispatch_handoff(
            failing,  # type: ignore[arg-type]
            provider,
            1,
            view.id,
            now=lambda: NOW,
        )
    assert len(provider.payloads) == 1
    stored = load_row(factory, view.id)
    assert stored.state == "dispatching"
    assert stored.attempts == 1
    assert stored.url is None
    replay = dispatch_handoff(factory, provider, 1, view.id, now=lambda: NOW)
    assert replay.state == "dispatching"
    assert replay.retry_allowed is False
    assert len(provider.payloads) == 1


def test_stale_completion_does_not_overwrite_fresh_attempt(
    factory: sessionmaker[Session], owners: None
) -> None:
    view = prepare_handoff(factory, 1, shopping_payload(), now=NOW)
    provider = FakeProvider(SUCCESS_URL)
    failing = FailCommitFactory(factory, 2)
    with pytest.raises(RuntimeError, match="forced commit failure"):
        dispatch_handoff(
            failing,  # type: ignore[arg-type]
            provider,
            1,
            view.id,
            now=lambda: NOW,
        )
    first = load_row(factory, view.id)
    old_token = first.attempt_token
    assert old_token is not None
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, view.id)
        assert row is not None
        row.attempts = 2
        row.attempt_token = "fresh-token"
        row.started_at = NOW + timedelta(seconds=1)
        row.url = None
        row.error_code = None
    with factory.begin() as session:
        _finish(session, 1, view.id, old_token, SUCCESS_URL, False, NOW)
    stored = load_row(factory, view.id)
    assert stored.state == "dispatching"
    assert stored.attempt_token == "fresh-token"
    assert stored.attempts == 2
    assert stored.url is None


def test_postgres_concurrent_retry_posts_once(
    postgres_factory: sessionmaker[Session],
) -> None:
    with postgres_factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))
    prepared = prepare_handoff(postgres_factory, 1, shopping_payload(), now=NOW)
    failed = dispatch_handoff(
        postgres_factory,
        FakeProvider(InstacartRejected()),
        1,
        prepared.id,
        now=lambda: NOW,
    )
    assert failed.state == "failed"
    assert failed.attempts == 1
    start = Barrier(2)
    provider = FakeProvider(SUCCESS_URL)
    bind = postgres_factory.kw["bind"]
    assert bind is not None
    first = sessionmaker(bind=bind, expire_on_commit=False)
    second = sessionmaker(bind=bind, expire_on_commit=False)

    def submit(owned: sessionmaker[Session]) -> str:
        start.wait(timeout=10)
        return dispatch_handoff(
            owned,
            provider,
            1,
            prepared.id,
            retry=True,
            expected_attempt=1,
            now=lambda: NOW,
        ).state

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, first), executor.submit(submit, second)]
        states = [future.result(timeout=20) for future in futures]
    assert len(provider.payloads) == 1
    assert "succeeded" in states
    with postgres_factory() as session:
        rows = session.query(ShoppingHandoff).filter_by(user_id=1).all()
        assert len(rows) == 1
        assert rows[0].state == "succeeded"
        assert rows[0].attempts == 2
        assert rows[0].url == SUCCESS_URL
