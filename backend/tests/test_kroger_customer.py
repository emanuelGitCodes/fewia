"""Tests for Kroger token storage and query redaction, using invented data."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import ORMExecuteState, Session

from app import kroger_customer
from app.kroger_customer import (
    KrogerConnectionChanged,
    customer_access_token,
    delete_rejected_access_token,
    delete_tokens,
    is_connected,
    redact_access_log,
    store_tokens,
)
from app.kroger_models import KrogerCustomerToken
from app.providers import kroger
from app.providers.kroger import CustomerTokens, KrogerClient, KrogerUnavailable
from app.security_models import KrogerOwner
from app.services.security_admission import OwnerUnavailableError

ACCESS = "SENTINEL-ACCESS-TOKEN"
REFRESH = "SENTINEL-REFRESH-TOKEN"
NEW_ACCESS = "SENTINEL-NEW-ACCESS-TOKEN"
NEW_REFRESH = "SENTINEL-NEW-REFRESH-TOKEN"
USER_ID = 1


def _cipher() -> Fernet:
    return Fernet(Fernet.generate_key())


def _row_count(session: Session) -> int:
    count = session.scalar(select(func.count()).select_from(KrogerCustomerToken))
    assert count is not None
    return count


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
        self.raw: bytes | None = None
        self.body: dict[str, object] = {
            "access_token": NEW_ACCESS,
            "refresh_token": NEW_REFRESH,
            "expires_in": 1800,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raw is not None:
            return httpx.Response(self.status, content=self.raw)
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


@pytest.mark.parametrize(
    ("status", "body"),
    [(400, {"error": "invalid_grant"}), (401, {"error": "invalid_grant"})],
)
def test_rejected_refresh_deletes_the_row_and_is_not_connected(
    session: Session, seed_user: UserSeeder, status: int, body: dict[str, object]
) -> None:
    cipher, server = _cipher(), _TokenServer()
    server.status = status
    server.body = body
    _connected(session, seed_user, cipher, -5)
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) is None
    assert len(server.requests) == 1
    assert _row_count(session) == 0
    assert is_connected(session, USER_ID) is False


@pytest.mark.parametrize(
    ("status", "body", "raw"),
    [
        (400, {"error": "invalid_request"}, None),
        (400, {}, b"not json"),
        (400, {}, b'["invalid_grant"]'),
        (401, {"error": "invalid_client"}, None),
        (401, {}, b"not json"),
        (401, {}, b'["invalid_grant"]'),
    ],
)
def test_other_refresh_400_and_401_keep_the_row_and_are_unavailable(
    session: Session,
    seed_user: UserSeeder,
    status: int,
    body: dict[str, object],
    raw: bytes | None,
) -> None:
    cipher, server = _cipher(), _TokenServer()
    server.status = status
    server.body = body
    server.raw = raw
    row = _connected(session, seed_user, cipher, -5)
    with pytest.raises(KrogerUnavailable):
        customer_access_token(session, USER_ID, _kroger(server), cipher)
    assert _row_count(session) == 1
    assert _stored(row, cipher) == (ACCESS, REFRESH)


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


def test_fresh_access_token_lookup_does_not_lock_the_row(
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
    assert "FOR UPDATE" not in selects[0]


def test_connection_version_changes_on_reconnect_only(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher, server = _cipher(), _TokenServer()
    row = _connected(session, seed_user, cipher, -5)
    original = row.connection_version
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) == (
        NEW_ACCESS
    )
    assert row.connection_version == original
    store_tokens(session, USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    assert row.connection_version != original


class _RacingTokenServer(_TokenServer):
    def __init__(self, during_refresh: Callable[[], None]) -> None:
        super().__init__()
        self.during_refresh = during_refresh

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.during_refresh()
        return super().__call__(request)


@pytest.mark.parametrize("expires_in", [120, -5])
@pytest.mark.parametrize("change", ["connection", "generation"])
def test_bound_token_lookup_rejects_changed_identity_before_provider_io(
    session: Session, seed_user: UserSeeder, expires_in: int, change: str
) -> None:
    cipher, server = _cipher(), _TokenServer()
    row = _connected(session, seed_user, cipher, expires_in)
    version, generation = row.connection_version, uuid4()
    owner = KrogerOwner(user_id=USER_ID, pairing_generation=generation)
    session.add(owner)
    if change == "connection":
        store_tokens(session, USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    else:
        owner.pairing_generation = uuid4()
    session.flush()
    with pytest.raises(
        KrogerConnectionChanged, match="^Kroger account is not connected$"
    ):
        customer_access_token(
            session,
            USER_ID,
            _kroger(server),
            cipher,
            expected_connection_version=version,
            expected_pairing_generation=generation,
        )
    assert server.requests == []
    assert _stored(row, cipher) == (ACCESS, REFRESH)


@pytest.mark.parametrize("expires_in", [120, -5])
def test_bound_token_lookup_rechecks_the_active_owner(
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    expires_in: int,
) -> None:
    cipher, server = _cipher(), _TokenServer()
    row = _connected(session, seed_user, cipher, expires_in)
    generation = uuid4()
    session.add(KrogerOwner(user_id=USER_ID, pairing_generation=generation))
    session.flush()
    owners: list[int] = []

    def unavailable(db: Session, user_id: int) -> None:
        assert db is session
        owners.append(user_id)
        raise OwnerUnavailableError()

    monkeypatch.setattr(kroger_customer, "lock_active_owner", unavailable)
    with pytest.raises(
        KrogerConnectionChanged, match="^Kroger account is not connected$"
    ):
        customer_access_token(
            session,
            USER_ID,
            _kroger(server),
            cipher,
            expected_connection_version=row.connection_version,
            expected_pairing_generation=generation,
        )
    assert owners == [USER_ID]
    assert server.requests == []
    assert _stored(row, cipher) == (ACCESS, REFRESH)


@pytest.mark.parametrize("rejected", [False, True])
def test_bound_refresh_uses_the_same_connection_winner(
    session: Session, seed_user: UserSeeder, rejected: bool
) -> None:
    cipher = _cipher()
    row = _connected(session, seed_user, cipher, -5)
    version, generation = row.connection_version, uuid4()
    session.add(KrogerOwner(user_id=USER_ID, pairing_generation=generation))
    session.flush()
    winner_pair: list[tuple[bytes, bytes]] = []

    def replace() -> None:
        assert not session.in_transaction()
        current = session.get(KrogerCustomerToken, USER_ID)
        assert current is not None
        current.access_token = cipher.encrypt(b"WINNER")
        current.refresh_token = cipher.encrypt(b"WINNER-R")
        current.access_expires_at = datetime.now(UTC) + timedelta(seconds=1800)
        winner_pair.append((current.access_token, current.refresh_token))
        session.commit()

    server = _RacingTokenServer(replace)
    if rejected:
        server.status = 401
        server.body = {"error": "invalid_grant"}
    assert (
        customer_access_token(
            session,
            USER_ID,
            _kroger(server),
            cipher,
            expected_connection_version=version,
            expected_pairing_generation=generation,
        )
        == "WINNER"
    )
    assert len(server.requests) == 1
    assert row.connection_version == version
    assert (row.access_token, row.refresh_token) == winner_pair[0]


@pytest.mark.parametrize("reconnect", [False, True])
@pytest.mark.parametrize("rejected", [False, True])
def test_refresh_winner_preserves_replacement(
    session: Session,
    seed_user: UserSeeder,
    reconnect: bool,
    rejected: bool,
) -> None:
    cipher = _cipher()
    row = _connected(session, seed_user, cipher, -5)
    original_version = row.connection_version
    winner_version = original_version
    locks: list[str] = []

    def capture(state: ORMExecuteState) -> None:
        if state.is_select:
            statement = str(state.statement.compile(dialect=postgresql.dialect()))
            if "FOR UPDATE" in statement:
                locks.append(statement)

    def replace() -> None:
        nonlocal winner_version
        assert locks == []
        with Session(bind=session.connection()) as winner:
            if reconnect:
                store_tokens(
                    winner, USER_ID, cipher, CustomerTokens("WINNER", "WINNER-R", 1800)
                )
            else:
                current = winner.get(KrogerCustomerToken, USER_ID)
                assert current is not None
                current.access_token = cipher.encrypt(b"WINNER")
                current.refresh_token = cipher.encrypt(b"WINNER-R")
                current.access_expires_at = datetime.now(UTC) + timedelta(seconds=1800)
                winner.flush()
            current = winner.get(KrogerCustomerToken, USER_ID)
            assert current is not None
            winner_version = current.connection_version

    event.listen(session, "do_orm_execute", capture)
    server = _RacingTokenServer(replace)
    if rejected:
        server.status = 401
        server.body = {"error": "invalid_grant"}
    assert customer_access_token(session, USER_ID, _kroger(server), cipher) == "WINNER"
    assert len(server.requests) == 1
    assert len(locks) == 1
    assert _stored(row, cipher) == ("WINNER", "WINNER-R")
    assert row.connection_version == winner_version
    assert (winner_version != original_version) == reconnect


@pytest.mark.parametrize("reconnect", [False, True])
def test_stale_cart_rejection_preserves_replacement(
    session: Session, seed_user: UserSeeder, reconnect: bool
) -> None:
    cipher = _cipher()
    row = _connected(session, seed_user, cipher, -5)
    original_version = row.connection_version
    if reconnect:
        store_tokens(
            session, USER_ID, cipher, CustomerTokens(NEW_ACCESS, NEW_REFRESH, 1800)
        )
    else:
        customer_access_token(session, USER_ID, _kroger(_TokenServer()), cipher)
    assert (
        delete_rejected_access_token(
            session,
            USER_ID,
            cipher,
            ACCESS,
            expected_connection_version=original_version,
        )
        is False
    )
    assert _stored(row, cipher) == (NEW_ACCESS, NEW_REFRESH)
    assert (
        delete_rejected_access_token(
            session,
            USER_ID,
            cipher,
            NEW_ACCESS,
            expected_connection_version=row.connection_version,
        )
        is True
    )
    assert session.get(KrogerCustomerToken, USER_ID) is None
    assert delete_rejected_access_token(session, USER_ID, cipher, NEW_ACCESS) is False


def test_rejected_token_with_a_stale_version_preserves_identical_reconnect(
    session: Session, seed_user: UserSeeder
) -> None:
    cipher = _cipher()
    row = _connected(session, seed_user, cipher, 1800)
    original_version = row.connection_version
    store_tokens(session, USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    replacement_pair = (row.access_token, row.refresh_token)
    assert row.connection_version != original_version
    assert not delete_rejected_access_token(
        session,
        USER_ID,
        cipher,
        ACCESS,
        expected_connection_version=original_version,
    )
    assert session.get(KrogerCustomerToken, USER_ID) is row
    assert (row.access_token, row.refresh_token) == replacement_pair


def test_token_helpers_leave_commit_to_caller(
    session: Session, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_commit() -> None:
        pytest.fail("Token helpers MUST NOT commit.")

    monkeypatch.setattr(session, "commit", forbidden_commit)
    cipher = _cipher()
    _connected(session, seed_user, cipher, -5)
    customer_access_token(session, USER_ID, _kroger(_TokenServer()), cipher)
    delete_tokens(session, USER_ID)


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


@pytest.mark.parametrize("prefix", ["", "/api"])
@pytest.mark.parametrize(
    "path",
    [
        "/grocery/kroger/callback",
        "/grocery/kroger/connect/start",
        "/grocery/kroger/%63allback",
        "/grocery/kroger/fixture/v1/connect/oauth2/authorize",
    ],
)
def test_access_log_drops_sensitive_queries(
    caplog: pytest.LogCaptureFixture, prefix: str, path: str
) -> None:
    target = f"{prefix}{path}"
    record = _log_access(
        caplog, target + "?code=SENTINEL&state=SENTINEL&ticket=SENTINEL"
    )
    assert record.getMessage() == f'127.0.0.1:5000 - "GET {target} HTTP/1.1" 302'
    assert "SENTINEL" not in caplog.text
    assert "SENTINEL" not in str(record.args)


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
