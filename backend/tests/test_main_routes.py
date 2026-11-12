"""Tests for the FastAPI route table after health-era retirement."""

from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import AlbTokenVerifier, AuthSettings
from app.main import app
from app.models import User
from app.security_models import KrogerOwner


@pytest.fixture(autouse=True)
def _local_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AuthSettings(
        auth_mode="local_demo", database_mode="local", transport_mode="local"
    )
    monkeypatch.setattr("app.deps.load_auth_settings", lambda: settings)


@pytest.fixture
def alb_headers(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> tuple[AuthSettings, dict[str, str]]:
    settings = AuthSettings(
        auth_mode="alb",
        database_mode="aws",
        transport_mode="aws",
        public_origin="https://fewia.example.test",
        alb_signer_arn=(
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
            "loadbalancer/app/fewia/0123456789abcdef"
        ),
        auth_issuer="https://identity.example.test/pool",
        auth_client_id="fewia-client",
        auth_logout_url=(
            "https://identity.example.test/logout?client_id=fewia-client"
            "&logout_uri=https%3A%2F%2Ffewia.example.test"
        ),
    )
    session.add(
        User(
            id=12,
            display_name="Owner",
            auth_issuer=settings.auth_issuer,
            auth_subject="subject-1",
        )
    )
    session.flush()
    session.add(KrogerOwner(user_id=12))
    session.flush()
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    verifier = AlbTokenVerifier(
        settings, key_fetch=lambda region, kid: pem, clock=lambda: 1800000000.0
    )
    monkeypatch.setattr("app.deps.load_auth_settings", lambda: settings)
    monkeypatch.setattr("app.deps.get_alb_verifier", lambda settings: verifier)
    token = jwt.encode(
        {"sub": "subject-1", "email": "untrusted@example.test"},
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
    return settings, {"x-amzn-oidc-data": token}


def test_app_route_paths_exclude_context_and_predict() -> None:
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert all(not path.startswith("/context") for path in paths)
    assert all(not path.startswith("/predict") for path in paths)


def test_local_session_returns_only_mode_and_workspace(
    client: TestClient, session: Session
) -> None:
    user = User(id=1, display_name="Demo owner")
    session.add(user)
    session.flush()
    response = client.get(
        "/grocery/session?user_id=2",
        headers={"x-forwarded-host": "attacker.example.test", "x-user-id": "2"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "auth_mode": "local_demo",
        "workspace_id": str(user.workspace_id),
    }
    assert UUID(response.json()["workspace_id"]) == user.workspace_id


@pytest.mark.parametrize("status", [None, "disabled", "deleting"])
def test_local_session_fails_closed(
    client: TestClient, session: Session, status: str | None
) -> None:
    if status is not None:
        session.add(User(id=1, display_name="Unavailable owner", status=status))
        session.flush()
    response = client.get("/grocery/session")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Authentication service is unavailable.",
        }
    }


def test_alb_session_returns_only_mode_and_workspace(
    client: TestClient,
    session: Session,
    alb_headers: tuple[AuthSettings, dict[str, str]],
) -> None:
    _, headers = alb_headers
    response = client.get("/grocery/session", headers=headers)
    user = session.get(User, 12)
    assert user is not None
    assert response.status_code == 200
    assert response.json() == {
        "auth_mode": "alb",
        "workspace_id": str(user.workspace_id),
    }
    assert "x-amzn-oidc-data" not in response.headers
    assert headers["x-amzn-oidc-data"] not in response.text


def test_alb_signout_uses_fixed_url_and_bounded_cookie_names(
    client: TestClient,
    alb_headers: tuple[AuthSettings, dict[str, str]],
) -> None:
    settings, headers = alb_headers
    response = client.post(
        "/grocery/signout?logout_url=https://attacker.example.test",
        headers={
            **headers,
            "cookie": "unrelated=keep; AWSELBAuthSessionCookie-99=keep",
        },
        json={"logout_url": "https://attacker.example.test"},
    )
    assert response.status_code == 200
    assert response.json() == {"logout_url": settings.auth_logout_url}
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 5
    assert {cookie.split("=", 1)[0] for cookie in cookies} == {
        "AWSELBAuthSessionCookie",
        "AWSELBAuthSessionCookie-0",
        "AWSELBAuthSessionCookie-1",
        "AWSELBAuthSessionCookie-2",
        "AWSELBAuthSessionCookie-3",
    }
    for cookie in cookies:
        assert "Max-Age=0" in cookie
        assert "expires=" in cookie.lower()
        assert "Path=/;" in cookie
        assert "Secure" in cookie
        assert "HttpOnly" in cookie
        assert "Domain=" not in cookie
    assert "attacker.example.test" not in response.text
    assert headers["x-amzn-oidc-data"] not in response.text
    assert all(headers["x-amzn-oidc-data"] not in cookie for cookie in cookies)


def test_local_signout_returns_completion(client: TestClient, session: Session) -> None:
    session.add(User(id=1, display_name="Demo owner"))
    session.flush()
    response = client.post("/grocery/signout")
    assert response.status_code == 200
    assert response.json() == {"logout_url": None}
    assert not response.headers.get_list("set-cookie")


def test_alb_protects_routes_and_keeps_health_public(
    client: TestClient,
    alb_headers: tuple[AuthSettings, dict[str, str]],
) -> None:
    for response in (
        client.get("/grocery/session"),
        client.post(
            "/grocery/templates",
            json={"budget_period": "2026-11-01", "monthly_limit_cents": 30000},
        ),
        client.post("/grocery/kroger/stores", json={"zip_code": "45202"}),
    ):
        assert response.status_code == 401
        assert response.json() == {
            "error": {"code": "unauthorized", "message": "Authentication is invalid."}
        }
    assert client.post("/grocery/signout").status_code == 401
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
