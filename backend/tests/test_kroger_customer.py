"""Tests for the Kroger OAuth state and token storage, using invented data."""

import logging
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import ORMExecuteState, Session

from app import kroger_customer
from app.kroger_customer import (
    STATE_TTL_SECONDS,
    customer_access_token,
    delete_tokens,
    is_connected,
    make_state,
    new_nonce,
    redact_access_log,
    state_matches,
    store_tokens,
)
from app.kroger_models import KrogerCustomerToken
from app.providers import kroger
from app.providers.kroger import CustomerTokens, KrogerClient, KrogerUnavailable

ACCESS = "SENTINEL-ACCESS-TOKEN"
REFRESH = "SENTINEL-REFRESH-TOKEN"
NEW_ACCESS = "SENTINEL-NEW-ACCESS-TOKEN"
NEW_REFRESH = "SENTINEL-NEW-REFRESH-TOKEN"
USER_ID = 1


def _cipher() -> Fernet:
    return Fernet(Fernet.generate_key())


def _freeze_clock(monkeypatch: pytest.MonkeyPatch, offset: float) -> None:
    now = time.time() + offset
    monkeypatch.setattr(kroger_customer, "_now", lambda: now)


@pytest.fixture(autouse=True)
def _commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "commit", session.flush)


def _row_count(session: Session) -> int:
    count = session.scalar(select(func.count()).select_from(KrogerCustomerToken))
    assert count is not None
    return count


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_state_round_trip() -> None:
    cipher = _cipher()
    nonce = new_nonce()
    state = make_state(cipher, nonce)
    assert nonce not in state
    assert state_matches(cipher, state, nonce) is True


def test_nonces_are_unique_and_url_safe() -> None:
    first, second = new_nonce(), new_nonce()
    assert first != second
    assert len(first) >= 32
    assert all(ch.isalnum() or ch in "-_" for ch in first)


def test_state_rejects_a_different_cookie() -> None:
    cipher = _cipher()
    state = make_state(cipher, new_nonce())
    assert state_matches(cipher, state, new_nonce()) is False


def test_state_rejects_a_missing_cookie() -> None:
    cipher = _cipher()
    state = make_state(cipher, new_nonce())
    assert state_matches(cipher, state, None) is False


@pytest.mark.parametrize("state", ["", "not-a-token", "é", "gAAAAA" + "A" * 40])
def test_state_rejects_garbage(state: str) -> None:
    assert state_matches(_cipher(), state, "nonce") is False


def test_state_rejects_another_key() -> None:
    nonce = new_nonce()
    state = make_state(_cipher(), nonce)
    assert state_matches(_cipher(), state, nonce) is False


def test_state_expires_after_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    cipher = _cipher()
    nonce = new_nonce()
    state = make_state(cipher, nonce)
    _freeze_clock(monkeypatch, STATE_TTL_SECONDS - 5)
    assert state_matches(cipher, state, nonce) is True
    _freeze_clock(monkeypatch, STATE_TTL_SECONDS + 5)
    assert state_matches(cipher, state, nonce) is False


def test_store_tokens_inserts_ciphertext(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(USER_ID)
    cipher = _cipher()
    store_tokens(session, USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    row = session.get(KrogerCustomerToken, USER_ID)
    assert row is not None
    assert _row_count(session) == 1
    assert ACCESS.encode() not in row.access_token
    assert REFRESH.encode() not in row.refresh_token
    assert cipher.decrypt(row.access_token).decode() == ACCESS
    assert cipher.decrypt(row.refresh_token).decode() == REFRESH
    remaining = (_aware(row.access_expires_at) - datetime.now(UTC)).total_seconds()
    assert 1700 < remaining <= 1800


def test_store_tokens_replaces_the_existing_row(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(USER_ID)
    cipher = _cipher()
    store_tokens(session, USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    first = session.get(KrogerCustomerToken, USER_ID)
    assert first is not None
    old_access = first.access_token
    newer = CustomerTokens("NEW-ACCESS", "NEW-REFRESH", 900)
    store_tokens(session, USER_ID, cipher, newer)
    row = session.get(KrogerCustomerToken, USER_ID)
    assert row is not None
    assert _row_count(session) == 1
    assert row.access_token != old_access
    assert b"NEW-ACCESS" not in row.access_token
    assert b"NEW-REFRESH" not in row.refresh_token
    assert cipher.decrypt(row.access_token).decode() == "NEW-ACCESS"
    assert cipher.decrypt(row.refresh_token).decode() == "NEW-REFRESH"
    remaining = (_aware(row.access_expires_at) - datetime.now(UTC)).total_seconds()
    assert 800 < remaining <= 900


def test_is_connected(session: Session, seed_user: UserSeeder) -> None:
    seed_user(USER_ID)
    assert is_connected(session, USER_ID) is False
    store_tokens(session, USER_ID, _cipher(), CustomerTokens(ACCESS, REFRESH, 1800))
    assert is_connected(session, USER_ID) is True
    assert is_connected(session, USER_ID + 1) is False


class _TokenServer:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.body: dict[str, object] = {
            "access_token": NEW_ACCESS,
            "refresh_token": NEW_REFRESH,
            "expires_in": 1800,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)


def _kroger(server: _TokenServer) -> KrogerClient:
    http = httpx.Client(transport=httpx.MockTransport(server))
    return KrogerClient(
        "invented-id",
        "invented-secret",
        base_url=kroger.HOSTS["certification"],
        client=http,
    )


def _connected(
    session: Session, seed_user: UserSeeder, cipher: Fernet, expires_in: int
) -> KrogerCustomerToken:
    seed_user(USER_ID)
    store_tokens(session, USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    row = session.get(KrogerCustomerToken, USER_ID)
    assert row is not None
    row.access_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    session.flush()
    return row


def _stored(row: KrogerCustomerToken, cipher: Fernet) -> tuple[str, str]:
    return (
        cipher.decrypt(row.access_token).decode(),
        cipher.decrypt(row.refresh_token).decode(),
    )


def test_access_token_is_none_without_a_row(session: Session) -> None:
    server = _TokenServer()
    token = customer_access_token(session, USER_ID, _kroger(server), _cipher())
    assert token is None
    assert server.requests == []


def test_fresh_access_token_is_returned_without_a_refresh(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher, server = _cipher(), _TokenServer()
    row = _connected(session, seed_user, cipher, 120)
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) == ACCESS
    assert server.requests == []
    assert _stored(row, cipher) == (ACCESS, REFRESH)


@pytest.mark.parametrize("expires_in", [30, -5])
def test_expired_access_triggers_one_refresh_and_stores_the_rotation(
    session: Session, seed_user: UserSeeder, expires_in: int
) -> None:
    cipher, server = _cipher(), _TokenServer()
    row = _connected(session, seed_user, cipher, expires_in)
    client = _kroger(server)
    assert customer_access_token(session, USER_ID, client, cipher) == NEW_ACCESS
    assert len(server.requests) == 1
    assert parse_qs(server.requests[0].content.decode()) == {
        "grant_type": ["refresh_token"],
        "refresh_token": [REFRESH],
    }
    assert NEW_ACCESS.encode() not in row.access_token
    assert NEW_REFRESH.encode() not in row.refresh_token
    assert _stored(row, cipher) == (NEW_ACCESS, NEW_REFRESH)
    remaining = (_aware(row.access_expires_at) - datetime.now(UTC)).total_seconds()
    assert 1700 < remaining <= 1800
    assert customer_access_token(session, USER_ID, client, cipher) == NEW_ACCESS
    assert len(server.requests) == 1


def test_refresh_keeps_the_old_refresh_token_when_none_returns(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher, server = _cipher(), _TokenServer()
    server.body = {"access_token": NEW_ACCESS, "expires_in": 1800}
    row = _connected(session, seed_user, cipher, -5)
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) == (
        NEW_ACCESS
    )
    assert _stored(row, cipher) == (NEW_ACCESS, REFRESH)


def test_failed_refresh_propagates_and_keeps_the_row(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher, server = _cipher(), _TokenServer()
    server.status = 500
    row = _connected(session, seed_user, cipher, -5)
    with pytest.raises(KrogerUnavailable):
        customer_access_token(session, USER_ID, _kroger(server), cipher)
    assert _row_count(session) == 1
    assert _stored(row, cipher) == (ACCESS, REFRESH)


@pytest.mark.parametrize("status", [400, 401])
def test_rejected_refresh_deletes_the_row_and_is_not_connected(
    session: Session, seed_user: UserSeeder, status: int
) -> None:
    cipher, server = _cipher(), _TokenServer()
    server.status = status
    _connected(session, seed_user, cipher, -5)
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) is None
    assert len(server.requests) == 1
    assert _row_count(session) == 0
    assert is_connected(session, USER_ID) is False


def test_refresh_timeout_propagates_and_keeps_the_row(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher = _cipher()

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = KrogerClient(
        "invented-id",
        "invented-secret",
        base_url=kroger.HOSTS["certification"],
        client=httpx.Client(transport=httpx.MockTransport(timeout)),
    )
    row = _connected(session, seed_user, cipher, -5)
    with pytest.raises(KrogerUnavailable):
        customer_access_token(session, USER_ID, client, cipher)
    assert _row_count(session) == 1
    assert _stored(row, cipher) == (ACCESS, REFRESH)


@pytest.mark.parametrize("expires_in", [120, -5])
def test_a_token_that_no_longer_decrypts_is_not_connected_and_is_deleted(
    session: Session, seed_user: UserSeeder, expires_in: int
) -> None:
    server = _TokenServer()
    _connected(session, seed_user, _cipher(), expires_in)
    token = customer_access_token(session, USER_ID, _kroger(server), _cipher())
    assert token is None
    assert server.requests == []
    assert _row_count(session) == 0
    assert is_connected(session, USER_ID) is False


def test_access_token_lookup_locks_the_row(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher, server = _cipher(), _TokenServer()
    _connected(session, seed_user, cipher, 120)
    selects: list[str] = []

    def capture(state: ORMExecuteState) -> None:
        if state.is_select:
            statement = state.statement.compile(dialect=postgresql.dialect())
            selects.append(str(statement))

    event.listen(session, "do_orm_execute", capture)
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) == ACCESS
    assert len(selects) == 1
    assert "kroger_customer_tokens" in selects[0]
    assert selects[0].rstrip().endswith("FOR UPDATE")


def test_delete_tokens_removes_the_row_and_tolerates_none(
    session: Session, seed_user: UserSeeder
) -> None:
    delete_tokens(session, USER_ID)
    _connected(session, seed_user, _cipher(), 1800)
    delete_tokens(session, USER_ID)
    assert _row_count(session) == 0
    assert is_connected(session, USER_ID) is False
    delete_tokens(session, USER_ID)


def _log_access(caplog: pytest.LogCaptureFixture, path: str) -> logging.LogRecord:
    redact_access_log()
    caplog.set_level(logging.INFO, logger="uvicorn.access")
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", path, "1.1", 302
    )
    records = [r for r in caplog.records if r.name == "uvicorn.access"]
    assert len(records) == 1
    return records[0]


def test_access_log_drops_the_callback_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = f"{kroger_customer.CALLBACK_PATH}?code=SENTINEL-CODE&state=SENTINEL-STATE"
    record = _log_access(caplog, path)
    assert record.getMessage() == (
        '127.0.0.1:5000 - "GET /grocery/kroger/callback HTTP/1.1" 302'
    )
    assert "SENTINEL" not in caplog.text


@pytest.mark.parametrize(
    "path",
    [
        "/grocery/kroger/connect",
        "/grocery/kroger/connection?x=1",
        "/grocery/kroger/stores",
        "/health?code=keep",
    ],
)
def test_access_log_leaves_other_paths_alone(
    caplog: pytest.LogCaptureFixture, path: str
) -> None:
    record = _log_access(caplog, path)
    assert record.getMessage() == f'127.0.0.1:5000 - "GET {path} HTTP/1.1" 302'


def test_access_log_filter_is_installed_once() -> None:
    redact_access_log()
    redact_access_log()
    filters = logging.getLogger("uvicorn.access").filters
    assert sum(type(f).__name__ == "_RedactCallbackQuery" for f in filters) == 1
