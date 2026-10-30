"""Tests for the Kroger OAuth state and token storage, using invented data."""

import logging
import time
from datetime import UTC, datetime

import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import kroger_customer
from app.kroger_customer import (
    STATE_TTL_SECONDS,
    is_connected,
    make_state,
    new_nonce,
    redact_access_log,
    state_matches,
    store_tokens,
)
from app.kroger_models import KrogerCustomerToken
from app.providers.kroger import CustomerTokens

ACCESS = "SENTINEL-ACCESS-TOKEN"
REFRESH = "SENTINEL-REFRESH-TOKEN"
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
