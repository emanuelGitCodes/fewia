import sqlite3
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException, Request
from sqlalchemy import Connection, create_engine, event, func, select, text
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import AlbTokenVerifier, AuthSettings
from app.deps import get_current_user, get_kroger_client
from app.models import User
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import KrogerClient
from app.security_models import KrogerOwner


@pytest.fixture(autouse=True)
def _clear_kroger_cache() -> Iterator[None]:
    get_kroger_client.cache_clear()
    yield
    get_kroger_client.cache_clear()


def test_get_kroger_client_none_without_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.deps.load_provider_settings", lambda: GroceryProviderSettings()
    )
    assert get_kroger_client() is None


def test_get_kroger_client_none_when_files_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            kroger_client_id_file=tmp_path / "no-id",
            kroger_secret_file=tmp_path / "no-secret",
        ),
    )
    assert get_kroger_client() is None


def test_concurrent_first_calls_build_one_kroger_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = threading.Barrier(8, timeout=5)
    built: list[object] = []

    def slow_build(settings: object) -> object:
        del settings
        time.sleep(0.05)
        client = object()
        built.append(client)
        return client

    monkeypatch.setattr(
        "app.deps.load_provider_settings", lambda: GroceryProviderSettings()
    )
    monkeypatch.setattr("app.deps.build_kroger", slow_build)
    results: list[object] = []

    def work() -> None:
        barrier.wait()
        results.append(get_kroger_client())

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(built) == 1
    assert results == built * 8


def test_get_kroger_client_built_from_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    id_file = tmp_path / "id"
    secret_file = tmp_path / "secret"
    id_file.write_text("invented-id\n")
    secret_file.write_text("invented-secret\n")
    id_file.chmod(0o600)
    secret_file.chmod(0o600)
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            kroger_client_id_file=id_file, kroger_secret_file=secret_file
        ),
    )
    client = get_kroger_client()
    assert isinstance(client, KrogerClient)
    assert get_kroger_client() is client


@pytest.fixture
def identity_session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'identity.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure(connection: sqlite3.Connection, record: object) -> None:
        connection.create_function("gen_random_uuid", 0, lambda: uuid4().hex)

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "display_name TEXT NOT NULL, auth_issuer TEXT, auth_subject TEXT, "
                "workspace_id CHAR(32) NOT NULL DEFAULT (gen_random_uuid()), "
                "status TEXT NOT NULL DEFAULT 'active', "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "UNIQUE (auth_issuer, auth_subject))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE kroger_owners (user_id BIGINT PRIMARY KEY, "
                "pairing_generation CHAR(32) NOT NULL DEFAULT (gen_random_uuid()), "
                "connection_generation CHAR(32) NOT NULL DEFAULT (gen_random_uuid()), "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def identity_settings() -> AuthSettings:
    return AuthSettings(
        auth_mode="alb",
        database_mode="local",
        transport_mode="local",
        public_origin="https://fewia.example.test",
        alb_signer_arn=(
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
            "loadbalancer/app/fewia/0123456789abcdef"
        ),
        auth_issuer="https://identity.example.test/pool",
        auth_client_id="fewia-client",
        auth_logout_url="https://identity.example.test/logout?client_id=fewia-client",
    )


@pytest.fixture
def identity_request(
    monkeypatch: pytest.MonkeyPatch, identity_settings: AuthSettings
) -> Request:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    verifier = AlbTokenVerifier(
        identity_settings, key_fetch=lambda region, kid: pem, clock=lambda: 1800000000.0
    )
    monkeypatch.setattr("app.deps.get_alb_verifier", lambda settings: verifier)
    token = jwt.encode(
        {"sub": "subject-1", "email": "untrusted@example.test"},
        key,
        algorithm="ES256",
        headers={
            "kid": "11111111-1111-4111-8111-111111111111",
            "signer": identity_settings.alb_signer_arn,
            "client": identity_settings.auth_client_id,
            "iss": identity_settings.auth_issuer,
            "exp": 1800003600,
        },
    )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/grocery/session",
            "headers": [(b"x-amzn-oidc-data", token.encode("ascii"))],
        }
    )


@pytest.mark.parametrize("status", [None, "active", "disabled", "deleting"])
def test_local_identity_uses_only_active_user_one(
    identity_session: Session, status: str | None
) -> None:
    settings = AuthSettings(
        auth_mode="local_demo", database_mode="local", transport_mode="local"
    )
    identity_session.add(User(id=2, display_name="Other owner"))
    if status is not None:
        identity_session.add(User(id=1, display_name="Demo owner", status=status))
    identity_session.commit()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/grocery/session",
            "headers": [(b"x-user-id", b"2"), (b"x-amzn-oidc-identity", b"2")],
            "query_string": b"user_id=2",
        }
    )
    if status == "active":
        assert get_current_user(request, identity_session, settings).id == 1
    else:
        with pytest.raises(HTTPException) as caught:
            get_current_user(request, identity_session, settings)
        assert caught.value.status_code == 503


def test_alb_identity_reuses_existing_owner(
    identity_session: Session,
    identity_settings: AuthSettings,
    identity_request: Request,
) -> None:
    user = User(
        id=12,
        display_name="Existing owner",
        auth_issuer=identity_settings.auth_issuer,
        auth_subject="subject-1",
    )
    identity_session.add(user)
    identity_session.add(KrogerOwner(user_id=12))
    identity_session.commit()
    workspace_id = user.workspace_id
    for _ in range(2):
        resolved = get_current_user(
            identity_request, identity_session, identity_settings
        )
        assert resolved.id == 12
        assert resolved.workspace_id == workspace_id
        assert resolved.display_name == "Existing owner"
    assert identity_session.scalar(select(func.count()).select_from(User)) == 1
    assert identity_session.scalar(select(func.count()).select_from(KrogerOwner)) == 1


def test_first_login_inserts_only_authorized_columns(
    identity_session: Session,
    identity_settings: AuthSettings,
    identity_request: Request,
) -> None:
    statements: list[str] = []

    def record(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.upper().startswith("INSERT"):
            statements.append(statement)

    bind = identity_session.get_bind()
    event.listen(bind, "before_cursor_execute", record)
    try:
        user = get_current_user(identity_request, identity_session, identity_settings)
    finally:
        event.remove(bind, "before_cursor_execute", record)
    assert len(statements) == 2
    assert statements[0] == (
        "INSERT INTO users (display_name, auth_issuer, auth_subject) "
        "VALUES (?, ?, ?) ON CONFLICT (auth_issuer, auth_subject) DO NOTHING"
    )
    assert statements[1] == (
        "INSERT INTO kroger_owners (user_id) VALUES (?) "
        "ON CONFLICT (user_id) DO NOTHING"
    )
    assert user.display_name == "FEWIA user"
    assert user.status == "active"
    assert user.workspace_id is not None
    owner = identity_session.get(KrogerOwner, user.id)
    assert owner is not None
    assert isinstance(owner.connection_generation, UUID)
    assert owner.connection_generation.version == 4
    assert owner.connection_generation != owner.pairing_generation


@pytest.mark.parametrize("status", ["disabled", "deleting"])
def test_alb_identity_rejects_inactive_owner(
    identity_session: Session,
    identity_settings: AuthSettings,
    identity_request: Request,
    status: str,
) -> None:
    identity_session.add(
        User(
            id=12,
            display_name="Inactive owner",
            auth_issuer=identity_settings.auth_issuer,
            auth_subject="subject-1",
            status=status,
        )
    )
    identity_session.commit()
    with pytest.raises(HTTPException) as caught:
        get_current_user(identity_request, identity_session, identity_settings)
    assert caught.value.status_code == 403
    assert identity_session.scalar(select(func.count()).select_from(User)) == 1
    assert identity_session.get(KrogerOwner, 12) is None


def test_concurrent_first_login_creates_one_owner(
    identity_session: Session,
    identity_settings: AuthSettings,
    identity_request: Request,
) -> None:
    barrier = threading.Barrier(2, timeout=5)
    bind = identity_session.get_bind()

    def login() -> tuple[int, str]:
        with Session(bind, expire_on_commit=False) as session:
            barrier.wait()
            user = get_current_user(identity_request, session, identity_settings)
            return user.id, str(user.workspace_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(login) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert results[0] == results[1]
    assert identity_session.scalar(select(func.count()).select_from(User)) == 1
    assert identity_session.scalar(select(func.count()).select_from(KrogerOwner)) == 1


@pytest.mark.parametrize("kind", ["missing", "malformed", "duplicate"])
def test_alb_dependency_rejects_bad_header_without_provisioning(
    identity_session: Session,
    identity_settings: AuthSettings,
    identity_request: Request,
    kind: str,
) -> None:
    values: list[tuple[bytes, bytes]] = identity_request.scope["headers"]
    invalid = {
        "missing": [],
        "malformed": [(b"x-amzn-oidc-data", b"bad.token.value")],
        "duplicate": values + values,
    }
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/grocery/session",
            "headers": invalid[kind],
        }
    )
    with pytest.raises(HTTPException) as caught:
        get_current_user(request, identity_session, identity_settings)
    assert caught.value.status_code == 401
    assert caught.value.detail == "Authentication is invalid."
    assert identity_session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("table", ["users", "kroger_owners"])
def test_provisioning_failure_rolls_back_and_returns_static_error(
    identity_session: Session,
    identity_settings: AuthSettings,
    identity_request: Request,
    table: str,
) -> None:
    def deny_insert(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if statement.startswith(f"INSERT INTO {table} "):
            raise OperationalError(statement, None, RuntimeError("Insert denied."))

    bind = identity_session.get_bind()
    event.listen(bind, "before_cursor_execute", deny_insert)
    try:
        with pytest.raises(HTTPException) as caught:
            get_current_user(identity_request, identity_session, identity_settings)
    finally:
        event.remove(bind, "before_cursor_execute", deny_insert)
    assert caught.value.status_code == 503
    assert caught.value.detail == "Authentication service is unavailable."
    assert identity_session.scalar(select(func.count()).select_from(User)) == 0
    assert identity_session.scalar(select(func.count()).select_from(KrogerOwner)) == 0
