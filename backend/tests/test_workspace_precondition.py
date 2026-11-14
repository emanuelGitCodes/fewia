"""Check workspace preconditions across authenticated request sessions."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import jwt
import pytest
from conftest import require_test_database_url
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import Table, select
from sqlalchemy.orm import Session, sessionmaker

from app.api import grocery
from app.auth import AlbTokenVerifier, AuthSettings
from app.db import Base
from app.deps import (
    get_current_user,
    get_kroger_cipher,
    get_kroger_client,
    get_kroger_pairing_cipher,
    get_provider_settings,
    get_session,
)
from app.evaluation_database import fixture_database
from app.job_models import Job, JobOutbox
from app.kroger_models import KrogerCustomerToken
from app.main import create_app
from app.models import User
from app.plan_models import PlanProposal, PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import AUTHORIZE_PATH, HOSTS, KrogerClient
from app.security_models import KrogerOwner, QuotaCounter, SecurityIntent
from app.workspace import WorkspaceChangedError, check_workspace

WORKSPACE = "abcdefab-1234-5678-9abc-123456789abc"
HEADER = "X-FEWIA-Workspace"
ORIGIN = "https://fewia.example.test"
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
JOB_BODY = {
    "request": {
        "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
        "budget_period": "2026-11-01",
    },
    "monthly_limit_cents": 10000,
}
PLAN_BODY = {
    "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
    "pantry_ingredient_ids": [],
    "plan_cap_cents": 5000,
}
TABLES = tuple(
    cast(Table, model.__table__)
    for model in (
        User,
        KrogerOwner,
        Job,
        JobOutbox,
        QuotaCounter,
        SecurityIntent,
        PlanRevision,
        PlanProposal,
        KrogerCustomerToken,
    )
)


@dataclass
class WorkspaceRig:
    api: TestClient
    factory: sessionmaker[Session]
    tokens: dict[str, str]
    workspaces: dict[str, str]
    request_sessions: list[Session]

    def auth(self, subject: str) -> dict[str, str]:
        return {"x-amzn-oidc-data": self.tokens[subject]}

    def state(self) -> dict[str, list[tuple[object, ...]]]:
        with self.factory() as session:
            return {
                table.name: [
                    tuple(row)
                    for row in session.execute(
                        table.select().order_by(*table.primary_key.columns)
                    )
                ]
                for table in TABLES
            }


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Iterator[WorkspaceRig]:
    settings = AuthSettings(
        auth_mode="alb",
        database_mode="aws",
        transport_mode="aws",
        public_origin=ORIGIN,
        alb_signer_arn=(
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
            "loadbalancer/app/fewia/0123456789abcdef"
        ),
        auth_issuer="https://identity.example.test/pool",
        auth_client_id="fewia-client",
        auth_logout_url="https://identity.example.test/logout?client_id=fewia-client",
    )
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    verifier = AlbTokenVerifier(
        settings, key_fetch=lambda region, kid: pem, clock=lambda: 1800000000.0
    )
    monkeypatch.setattr("app.deps.load_auth_settings", lambda: settings)
    monkeypatch.setattr("app.deps.get_alb_verifier", lambda settings: verifier)
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(spending_source="fixture"),
    )
    monkeypatch.setattr(grocery, "_ny_now", lambda: NOW)

    def forbid_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests MUST NOT use the network.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbid_network)
    tokens = {
        subject: jwt.encode(
            {"sub": subject},
            key,
            algorithm="ES256",
            headers={
                "kid": "11111111-1111-4111-8111-111111111111",
                "signer": settings.alb_signer_arn,
                "client": settings.auth_client_id,
                "iss": settings.auth_issuer,
                "exp": 1800003600,
            },
        )
        for subject in ("a", "b", "disabled", "deleting", "new")
    }
    with fixture_database(require_test_database_url()) as database:
        with database.factory() as session:
            Base.metadata.create_all(session.get_bind(), tables=list(TABLES))
            users: list[User] = []
            for subject in ("a", "b", "disabled", "deleting"):
                status = subject if subject in {"disabled", "deleting"} else "active"
                user = User(
                    display_name="Synthetic owner",
                    auth_issuer=settings.auth_issuer,
                    auth_subject=subject,
                    status=status,
                )
                users.append(user)
            session.add_all(users)
            session.commit()
            assert [user.id for user in users] == [1, 2, 3, 4]
            workspaces = {
                user.auth_subject or "": str(user.workspace_id) for user in users
            }
        request_sessions: list[Session] = []

        def request_session() -> Iterator[Session]:
            with database.factory() as session:
                request_sessions.append(session)
                yield session

        application = create_app()
        application.dependency_overrides[get_session] = request_session
        application.dependency_overrides[get_kroger_client] = lambda: None
        application.dependency_overrides[get_kroger_cipher] = lambda: None
        application.dependency_overrides[get_kroger_pairing_cipher] = lambda: None
        with TestClient(application, base_url="http://localhost") as api:
            yield WorkspaceRig(
                api, database.factory, tokens, workspaces, request_sessions
            )


def assert_workspace_changed(response: httpx.Response) -> None:
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "workspace_changed",
            "message": "Your workspace changed. Reload before continuing.",
        }
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert not response.headers.get_list("set-cookie")


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/grocery/jobs", JOB_BODY),
        ("/grocery/plans", PLAN_BODY),
        ("/grocery/signout", {}),
        ("/grocery/kroger/pairing/redeem", {"ticket": "x" * 43}),
    ],
)
@pytest.mark.parametrize("header_kind", ["missing", "stale"])
def test_tab_workspace_change_has_no_persisted_effects(
    rig: WorkspaceRig, path: str, body: dict[str, object], header_kind: str
) -> None:
    bootstrap = rig.api.get("/grocery/session", headers=rig.auth("a"))
    assert bootstrap.status_code == 200
    before = rig.state()
    headers = {
        **rig.auth("b"),
        "Origin": ORIGIN,
        "Idempotency-Key": "switched-tab",
    }
    if header_kind == "stale":
        headers[HEADER] = bootstrap.json()["workspace_id"]
    response = rig.api.post(
        path,
        headers=headers,
        json=body,
    )
    assert_workspace_changed(response)
    assert rig.state() == before
    assert len(rig.request_sessions) == 2
    assert rig.request_sessions[0] is not rig.request_sessions[1]


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "comma", "malformed", "stale"]
)
def test_browser_job_rejects_invalid_preconditions_without_writes(
    rig: WorkspaceRig, kind: str
) -> None:
    current = rig.workspaces["b"]
    values = {
        "missing": [],
        "duplicate": [(HEADER, current), (HEADER.lower(), current)],
        "comma": [(HEADER, f"{current},{current}")],
        "malformed": [(HEADER, "invalid")],
        "stale": [(HEADER, rig.workspaces["a"])],
    }
    before = rig.state()
    response = rig.api.post(
        "/grocery/jobs",
        headers=[
            *rig.auth("b").items(),
            ("Origin", ORIGIN),
            ("Idempotency-Key", "invalid-precondition"),
            *values[kind],
        ],
        json=JOB_BODY,
    )
    assert_workspace_changed(response)
    assert rig.state() == before


@pytest.mark.parametrize("browser", [False, True])
def test_accepted_job_uses_only_authenticated_owner(
    rig: WorkspaceRig, browser: bool
) -> None:
    headers = {**rig.auth("b"), "Idempotency-Key": "accepted"}
    if browser:
        headers.update(
            {"Origin": ORIGIN, HEADER: rig.workspaces["b"], "X-User-ID": "1"}
        )
    response = rig.api.post("/grocery/jobs", headers=headers, json=JOB_BODY)
    assert response.status_code == 202
    assert response.headers["cache-control"] == "private, no-store"
    with rig.factory() as session:
        jobs = session.scalars(select(Job)).all()
        assert len(jobs) == 1
        assert jobs[0].id == response.json()["job_id"]
        assert jobs[0].user_id == 2
        assert [row.job_id for row in session.scalars(select(JobOutbox))] == [
            jobs[0].id
        ]
        counters = session.scalars(select(QuotaCounter)).all()
        assert len(counters) == 1
        assert (counters[0].action, counters[0].scope_key, counters[0].count) == (
            "mutation",
            2,
            1,
        )
        assert session.scalars(select(KrogerOwner.user_id)).all() == [2]


def test_personalized_reads_check_supplied_workspace(rig: WorkspaceRig) -> None:
    path = "/grocery/jobs/11111111-1111-4111-8111-111111111111"
    for extra in ({}, {HEADER: rig.workspaces["b"]}):
        response = rig.api.get(path, headers={**rig.auth("b"), **extra})
        assert response.status_code == 404
        assert response.headers["cache-control"] == "private, no-store"
    before = rig.state()
    assert_workspace_changed(
        rig.api.get(path, headers={**rig.auth("b"), HEADER: rig.workspaces["a"]})
    )
    assert rig.state() == before


def test_session_ignores_stale_or_invalid_workspace(rig: WorkspaceRig) -> None:
    for values in (
        [(HEADER, rig.workspaces["a"])],
        [(HEADER, "invalid"), (HEADER.lower(), "invalid")],
    ):
        response = rig.api.get(
            "/grocery/session", headers=[*rig.auth("b").items(), *values]
        )
        assert response.status_code == 200
        assert response.json() == {
            "auth_mode": "alb",
            "workspace_id": rig.workspaces["b"],
        }
        assert response.headers["cache-control"] == "private, no-store"
    assert rig.api.get("/healthz", headers={HEADER: "invalid"}).status_code == 200


@pytest.mark.parametrize("subject", ["disabled", "deleting", "invalid"])
def test_authentication_errors_precede_workspace_checks(
    rig: WorkspaceRig, subject: str
) -> None:
    headers = (
        {"x-amzn-oidc-data": "bad.token.value"}
        if subject == "invalid"
        else rig.auth(subject)
    )
    before = rig.state()
    response = rig.api.post(
        "/grocery/signout", headers={**headers, "Origin": ORIGIN, HEADER: "invalid"}
    )
    assert response.status_code == (401 if subject == "invalid" else 403)
    assert response.json()["error"]["code"] != "workspace_changed"
    assert rig.state() == before


def test_invalid_origin_precedes_workspace_check(rig: WorkspaceRig) -> None:
    before = rig.state()
    response = rig.api.post(
        "/grocery/signout",
        headers={**rig.auth("b"), "Origin": "https://attacker.example.test"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "The browser request is not allowed."
    assert rig.state() == before


@pytest.mark.parametrize("kind", ["missing", "stale", "malformed"])
def test_failed_first_login_does_not_provision(rig: WorkspaceRig, kind: str) -> None:
    extra = (
        {}
        if kind == "missing"
        else {HEADER: rig.workspaces["a"] if kind == "stale" else "bad"}
    )
    before = rig.state()
    response = rig.api.post(
        "/grocery/signout", headers={**rig.auth("new"), "Origin": ORIGIN, **extra}
    )
    assert_workspace_changed(response)
    assert rig.state() == before


def test_first_login_with_supplied_workspace_does_not_provision(
    rig: WorkspaceRig,
) -> None:
    before = rig.state()
    assert_workspace_changed(
        rig.api.get(
            "/grocery/jobs/11111111-1111-4111-8111-111111111111",
            headers={**rig.auth("new"), HEADER: rig.workspaces["a"]},
        )
    )
    assert rig.state() == before


def test_first_login_session_recovers_with_stale_workspace(rig: WorkspaceRig) -> None:
    response = rig.api.get(
        "/grocery/session",
        headers={**rig.auth("new"), HEADER: rig.workspaces["a"]},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    with rig.factory() as session:
        user = session.scalar(select(User).where(User.auth_subject == "new"))
        assert user is not None
        assert response.json() == {
            "auth_mode": "alb",
            "workspace_id": str(user.workspace_id),
        }
        assert str(user.workspace_id) != rig.workspaces["a"]
        assert session.get(KrogerOwner, user.id) is not None


@pytest.mark.parametrize("bootstrap", [False, True])
def test_headerless_first_login_remains_compatible(
    rig: WorkspaceRig, bootstrap: bool
) -> None:
    response = (
        rig.api.get("/grocery/session", headers=rig.auth("new"))
        if bootstrap
        else rig.api.post("/grocery/signout", headers=rig.auth("new"))
    )
    assert response.status_code == 200
    with rig.factory() as session:
        user = session.scalar(select(User).where(User.auth_subject == "new"))
        assert user is not None
        assert session.get(KrogerOwner, user.id) is not None


@pytest.mark.parametrize(
    "values",
    [
        [(b"X-FEWIA-Workspace", WORKSPACE.encode())] * 2,
        [
            (b"X-FEWIA-Workspace", WORKSPACE.encode()),
            (b"x-fewia-workspace", WORKSPACE.encode()),
        ],
        *[
            [(b"x-fewia-workspace", value)]
            for value in (
                b"",
                b"invalid",
                WORKSPACE.upper().encode(),
                WORKSPACE.replace("-", "").encode(),
                ("{" + WORKSPACE + "}").encode(),
                ("urn:uuid:" + WORKSPACE).encode(),
                (" " + WORKSPACE).encode(),
                (WORKSPACE + " ").encode(),
                (WORKSPACE + "," + WORKSPACE).encode(),
                b"\t" + WORKSPACE.encode()[1:],
                b"\r" + WORKSPACE.encode()[1:],
                b"\n" + WORKSPACE.encode()[1:],
                b"\x00" + WORKSPACE.encode()[1:],
                b"\x7f" + WORKSPACE.encode()[1:],
                b"\xff" + WORKSPACE.encode()[1:],
                b"a" * 4096,
            )
        ],
    ],
)
def test_raw_header_rejects_noncanonical_values(
    values: list[tuple[bytes, bytes]],
) -> None:
    request = Request(
        {"type": "http", "method": "GET", "path": "/grocery/jobs", "headers": values}
    )
    user = User(id=1, workspace_id=UUID(WORKSPACE))
    with pytest.raises(WorkspaceChangedError):
        check_workspace(request, user)


def test_raw_header_name_is_case_insensitive() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/grocery/jobs",
            "headers": [(b"X-FeWiA-WoRkSpAcE", WORKSPACE.encode())],
        }
    )
    check_workspace(request, User(id=1, workspace_id=UUID(WORKSPACE)))


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("marker", [b"Origin", b"SeC-FeTcH-Site", b"sec-fetch-unknown"])
def test_each_browser_marker_requires_workspace(method: str, marker: bytes) -> None:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": "/grocery/signout",
            "headers": [(marker, b"")],
        }
    )
    with pytest.raises(WorkspaceChangedError):
        check_workspace(request, User(id=1, workspace_id=UUID(WORKSPACE)))


@pytest.mark.parametrize("status", [None, "active", "disabled", "deleting"])
def test_local_fixture_preserves_user_checks(
    session: Session, status: str | None
) -> None:
    if status is not None:
        session.add(User(id=1, display_name="Synthetic local owner", status=status))
        session.flush()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/grocery/signout",
            "headers": [(b"x-fewia-workspace", b"invalid")],
        }
    )
    if status == "active":
        with pytest.raises(WorkspaceChangedError):
            get_current_user(request, session, AuthSettings())
    else:
        with pytest.raises(HTTPException) as caught:
            get_current_user(request, session, AuthSettings())
        assert caught.value.status_code == 503


def test_oauth_navigation_keeps_ticket_and_state_checks(
    rig: WorkspaceRig,
) -> None:
    cipher = Fernet(Fernet.generate_key())
    settings = GroceryProviderSettings(
        kroger_mode="fixture",
        kroger_redirect_uri="http://localhost/grocery/kroger/callback",
        kroger_return_url="http://127.0.0.1:5173/prototype",
    )
    calls: list[str] = []

    def exchange(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "expires_in": 1800,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(exchange)) as transport:
        provider = KrogerClient(
            "invented-id",
            "invented-secret",
            base_url=HOSTS["certification"],
            client=transport,
        )
        overrides = cast(FastAPI, rig.api.app).dependency_overrides
        overrides[get_provider_settings] = lambda: settings
        overrides[get_kroger_client] = lambda: provider
        overrides[get_kroger_cipher] = lambda: cipher
        overrides[get_kroger_pairing_cipher] = lambda: cipher
        connected = rig.api.post("/grocery/kroger/connect", headers=rig.auth("b"))
        assert connected.status_code == 200
        start = connected.json()["authorization_url"].removeprefix("/api")
        before = rig.state()
        stale = {**rig.auth("b"), HEADER: rig.workspaces["a"]}
        assert_workspace_changed(rig.api.get(start, headers=stale))
        assert rig.state() == before
        started = rig.api.get(start, headers=rig.auth("b"), follow_redirects=False)
        assert started.status_code == 302
        assert rig.api.get(start, headers=rig.auth("b")).status_code == 422
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        fixture = "/grocery/kroger/fixture" + AUTHORIZE_PATH
        before = rig.state()
        assert_workspace_changed(
            rig.api.get(fixture, params={"state": state}, headers=stale)
        )
        assert_workspace_changed(
            rig.api.get(
                "/grocery/kroger/callback",
                params={"state": state, "code": "synthetic-code"},
                headers=stale,
            )
        )
        assert rig.state() == before
        assert calls == []
        authorized = rig.api.get(
            fixture,
            params={"state": state},
            headers=rig.auth("b"),
            follow_redirects=False,
        )
        assert authorized.status_code == 302
        callback = authorized.headers["location"]
        finished = rig.api.get(callback, headers=rig.auth("b"), follow_redirects=False)
        assert finished.status_code == 302
        assert finished.headers["location"].endswith("kroger=connected")
        replay = rig.api.get(callback, headers=rig.auth("b"), follow_redirects=False)
        assert replay.headers["location"].endswith("kroger=error")
        assert len(calls) == 1
