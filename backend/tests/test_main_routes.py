"""Tests for the FastAPI route table after health-era retirement."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api import chat, evidence, grocery, plan_templates, proposals, sync
from app.auth import AlbTokenVerifier, AuthSettings
from app.deps import get_kroger_client
from app.domain.budget import SpendingSnapshot
from app.domain.plan_proposal import ApplyConstraints, create_proposal
from app.evidence_models import GroceryEvidence
from app.job_models import Job, JobOutbox
from app.main import app
from app.models import User
from app.plaid_models import PlaidItem
from app.plan_models import PlanProposal, PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.security_models import KrogerOwner
from app.services import job_submission, security_admission

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
PLAN = {
    "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
    "pantry_ingredient_ids": [],
    "plan_cap_cents": 5000,
}


@pytest.fixture(autouse=True)
def mutation_admission(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[Session, int, security_admission.Action]]:
    calls: list[tuple[Session, int, security_admission.Action]] = []
    real_reserve = security_admission.reserve_action

    def reserve(
        db: Session,
        user_id: int,
        action: security_admission.Action,
        *,
        now: datetime | None = None,
    ) -> None:
        if db.get_bind().dialect.name == "sqlite":
            status = db.scalar(select(User.status).where(User.id == user_id))
            if status != "active":
                raise security_admission.OwnerUnavailableError()
        else:
            real_reserve(db, user_id, action, now=now)
        calls.append((db, user_id, action))

    monkeypatch.setattr(security_admission, "reserve_action", reserve)
    monkeypatch.setattr(job_submission, "reserve_action", reserve)
    return calls


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


@pytest.fixture
def two_owner_headers(
    alb_headers: tuple[AuthSettings, dict[str, str]],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[int, dict[str, str]]:
    settings, _ = alb_headers
    session.add(
        User(
            id=13,
            display_name="Second owner",
            auth_issuer=settings.auth_issuer,
            auth_subject="subject-2",
        )
    )
    session.flush()
    session.add(KrogerOwner(user_id=13))
    session.flush()
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    verifier = AlbTokenVerifier(
        settings, key_fetch=lambda region, kid: pem, clock=lambda: 1800000000.0
    )
    monkeypatch.setattr("app.deps.get_alb_verifier", lambda settings: verifier)
    return {
        owner: {
            "x-amzn-oidc-data": jwt.encode(
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
        }
        for owner, subject in ((12, "subject-1"), (13, "subject-2"))
    }


@pytest.fixture
def owner_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = GroceryProviderSettings(
        bedrock_model_id="test-model", spending_source="plaid_sandbox"
    )
    monkeypatch.setattr("app.deps.load_provider_settings", lambda: settings)
    monkeypatch.setattr(proposals, "get_provider_settings", lambda: settings)
    monkeypatch.setattr(sync, "_plaid_is_configured", lambda: True)
    monkeypatch.setitem(app.dependency_overrides, get_kroger_client, lambda: None)
    for module in (grocery, chat, plan_templates):
        monkeypatch.setattr(module, "_ny_now", lambda: NOW)

    def spending(db: Session, user_id: int, period: object) -> SpendingSnapshot:
        assert user_id in (12, 13)
        assert period == NOW.date().replace(day=1)
        return SpendingSnapshot(
            NOW.date().replace(day=1), user_id * 100, user_id * 10, NOW
        )

    monkeypatch.setattr("app.services.grocery_context.load_spending", spending)


def test_two_owners_get_their_spending_and_templates(
    client: TestClient,
    two_owner_headers: dict[int, dict[str, str]],
    owner_runtime: None,
) -> None:
    for owner, headers in two_owner_headers.items():
        config = client.get("/grocery/config", headers=headers)
        assert config.status_code == 200
        assert config.json()["posted_cents"] == owner * 100
        assert config.json()["pending_cents"] == owner * 10
        templates = client.post(
            "/grocery/templates",
            headers=headers,
            json={"budget_period": "2026-11-01", "monthly_limit_cents": 10000},
        )
        assert templates.status_code == 200
        assert templates.json()["budget"]["available_cents"] == 10000 - owner * 100
        assert templates.json()["budget"]["pending_cents"] == owner * 10
        assert client.get("/grocery/providers", headers=headers).status_code == 200
        for response in (config, templates):
            assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("kind", ["plan", "chat", "sync"])
def test_two_owners_create_and_read_only_their_jobs(
    client: TestClient,
    session: Session,
    two_owner_headers: dict[int, dict[str, str]],
    owner_runtime: None,
    kind: str,
) -> None:
    path = {
        "plan": "/grocery/jobs",
        "chat": "/grocery/chat/jobs",
        "sync": "/grocery/sync/jobs",
    }[kind]
    accepted: dict[int, str] = {}
    for owner, auth in two_owner_headers.items():
        if kind == "sync":
            session.add(
                PlaidItem(
                    id=f"item-{owner}",
                    user_id=owner,
                    provider_item_id=f"provider-{owner}",
                    credential_ref="synthetic-reference",
                )
            )
            session.flush()
            body: dict[str, object] = {"item_id": f"item-{owner}"}
        elif kind == "chat":
            body = {"message": "plan bean tacos", "monthly_limit_cents": 10000}
        else:
            body = {
                "request": {"meals": PLAN["meals"], "budget_period": "2026-11-01"},
                "monthly_limit_cents": 10000,
            }
        headers = {**auth, "Idempotency-Key": "same-key"}
        first = client.post(path, headers=headers, json=body)
        assert first.status_code == 202
        assert client.post(path, headers=headers, json=body).json() == first.json()
        job_id = first.json()["job_id"]
        accepted[owner] = job_id
        stored = session.get(Job, job_id)
        assert stored is not None and stored.user_id == owner
        if kind != "sync":
            assert stored.payload["spending"]["posted_cents"] == owner * 100
        own = client.get(f"{path}/{job_id}", headers=auth)
        assert own.status_code == 200
        assert own.headers["cache-control"] == "private, no-store"
    assert accepted[12] != accepted[13]
    for owner, auth in two_owner_headers.items():
        foreign_id = accepted[13 if owner == 12 else 12]
        foreign = client.get(f"{path}/{foreign_id}", headers=auth)
        missing = client.get(f"{path}/{uuid4()}", headers=auth)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert foreign.headers["cache-control"] == "private, no-store"


def test_chat_uses_owned_plan_and_history_and_hides_foreign_references(
    client: TestClient,
    session: Session,
    two_owner_headers: dict[int, dict[str, str]],
    owner_runtime: None,
) -> None:
    revisions: dict[int, str] = {}
    parents: dict[int, str] = {}
    for owner, auth in two_owner_headers.items():
        saved = client.post("/grocery/plans", headers=auth, json=PLAN)
        assert saved.status_code == 201
        revision_id = saved.json()["plan_revision_id"]
        revisions[owner] = revision_id
        revision = session.get(PlanRevision, UUID(revision_id))
        assert revision is not None and revision.user_id == owner
        first = client.post(
            "/grocery/chat/jobs",
            headers={**auth, "Idempotency-Key": "history-parent"},
            json={
                "message": "plan bean tacos",
                "monthly_limit_cents": 10000,
                "plan_revision_id": revision_id,
            },
        )
        assert first.status_code == 202
        parents[owner] = first.json()["job_id"]
        parent = session.get(Job, parents[owner])
        assert parent is not None
        assert parent.payload["plan_revision"]["snapshot"] == PLAN
        parent.status = "succeeded"
        parent.result = {
            "answer": f"Owner {owner} plan",
            "request": {"meals": PLAN["meals"], "budget_period": "2026-11-01"},
        }
        session.flush()
        followup = client.post(
            "/grocery/chat/jobs",
            headers={**auth, "Idempotency-Key": "history-followup"},
            json={
                "message": "use my plan",
                "monthly_limit_cents": 10000,
                "previous_job_id": parents[owner],
            },
        )
        assert followup.status_code == 202
        child = session.get(Job, followup.json()["job_id"])
        assert child is not None
        assert child.payload["history"][-1]["text"] == f"Owner {owner} plan"
    for owner, auth in two_owner_headers.items():
        other = 13 if owner == 12 else 12
        for field, foreign_id in (
            ("previous_job_id", parents[other]),
            ("plan_revision_id", revisions[other]),
        ):
            responses = [
                client.post(
                    "/grocery/chat/jobs",
                    headers={**auth, "Idempotency-Key": f"foreign-{field}"},
                    json={
                        "message": "use my plan",
                        "monthly_limit_cents": 10000,
                        field: value,
                    },
                )
                for value in (foreign_id, str(uuid4()))
            ]
            assert all(response.status_code == 404 for response in responses)
            assert responses[0].json() == responses[1].json()


def test_sync_hides_foreign_and_missing_plaid_items(
    client: TestClient,
    session: Session,
    two_owner_headers: dict[int, dict[str, str]],
    owner_runtime: None,
) -> None:
    for owner in two_owner_headers:
        session.add(
            PlaidItem(
                id=f"item-{owner}",
                user_id=owner,
                provider_item_id=f"provider-{owner}",
                credential_ref="synthetic-reference",
            )
        )
    session.flush()
    for owner, auth in two_owner_headers.items():
        other = 13 if owner == 12 else 12
        responses = [
            client.post(
                "/grocery/sync/jobs",
                headers={**auth, "Idempotency-Key": "foreign-item"},
                json={"item_id": item_id},
            )
            for item_id in (f"item-{other}", "missing-item")
        ]
        assert all(response.status_code == 404 for response in responses)
        assert responses[0].json() == responses[1].json()
    assert session.scalars(select(Job)).all() == []


def test_two_owners_read_only_their_evidence(
    client: TestClient,
    session: Session,
    two_owner_headers: dict[int, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = sessionmaker(bind=session.connection())
    monkeypatch.setitem(
        app.dependency_overrides, evidence.get_session_factory, lambda: factory
    )
    ids = {12: "a" * 64, 13: "b" * 64}
    for owner, revision_id in ids.items():
        session.add(
            GroceryEvidence(id=revision_id, user_id=owner, snapshot={"owner": owner})
        )
    session.flush()
    for owner, auth in two_owner_headers.items():
        own = client.get(f"/grocery/evidence/{ids[owner]}", headers=auth)
        assert own.status_code == 200
        assert own.json()["snapshot"] == {"owner": owner}
        assert own.headers["cache-control"] == "private, no-store"
        other = 13 if owner == 12 else 12
        foreign = client.get(f"/grocery/evidence/{ids[other]}", headers=auth)
        missing = client.get(f"/grocery/evidence/{'c' * 64}", headers=auth)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()


@pytest.mark.parametrize("action", ["apply", "discard"])
def test_two_owners_mutate_only_their_proposals(
    client: TestClient,
    session: Session,
    two_owner_headers: dict[int, dict[str, str]],
    owner_runtime: None,
    action: str,
) -> None:
    ids: dict[int, UUID] = {}
    for owner, auth in two_owner_headers.items():
        saved = client.post("/grocery/plans", headers=auth, json=PLAN)
        assert saved.status_code == 201
        ids[owner] = create_proposal(
            session,
            owner,
            UUID(saved.json()["plan_revision_id"]),
            [{"op": "set_servings", "recipe_id": "bean_tacos", "servings": 3}],
            constraints=ApplyConstraints(
                monthly_limit_cents=10000,
                plan_cap_cents=5000,
                diet="omnivore",
                ingredient_exclusions=[],
            ),
        )
    session.flush()
    body = {"plan_cap_cents": 4000} if action == "apply" else {"confirm": True}
    for owner, auth in two_owner_headers.items():
        other = 13 if owner == 12 else 12
        for requested in (ids[other], uuid4()):
            path = f"/grocery/proposals/{requested}"
            assert client.get(path, headers=auth).status_code == 404
            denied = client.post(f"{path}/{action}", headers=auth, json=body)
            assert denied.status_code == 404
        path = f"/grocery/proposals/{ids[owner]}"
        own = client.get(path, headers=auth)
        assert own.status_code == 200
        applied = client.post(f"{path}/{action}", headers=auth, json=body)
        assert applied.status_code == 200
        repeated = client.post(f"{path}/{action}", headers=auth, json=body)
        assert repeated.json() == applied.json()
        row = session.get(PlanProposal, ids[owner])
        assert row is not None and row.user_id == owner
        if action == "apply":
            committed = session.get(PlanRevision, row.applied_plan_revision_id)
            assert committed is not None and committed.user_id == owner
            assert committed.snapshot["plan_cap_cents"] == 4000
            assert applied.json()["snapshot"] == committed.snapshot
        else:
            assert row.status == "discarded"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "browser_headers",
    [
        [("origin", "https://attacker.example.test")],
        [("origin", "null")],
        [("origin", "https://FEWIA.example.test")],
        [("origin", "https://fewia.example.test:443")],
        [("origin", "https://fewia.example.test/")],
        [("origin", "https://fewia.example.test https://attacker.example.test")],
        [("origin", "https://fewia.example.test")] * 2,
        [("origin", "https://fewia.example.test"), ("sec-fetch-site", "cross-site")],
        [("sec-fetch-site", "cross-site"), ("sec-fetch-mode", "navigate")],
        [("sec-fetch-site", "same-site")],
        [("sec-fetch-site", "same-origin")],
        [("sec-fetch-mode", "cors")],
        [("sec-fetch-dest", "empty")],
        [("sec-fetch-user", "?1")],
        [("sec-fetch-unknown", "synthetic")],
        [("sec-fetch-site", "same-origin"), ("sec-fetch-mode", "no-cors")],
        [("origin", "https://fewia.example.test"), ("sec-fetch-dest", "document")],
        [("sec-fetch-site", "same-origin")] * 2,
        [
            ("origin", "https://fewia.example.test"),
            ("sec-fetch-site", "same-origin"),
            ("Sec-Fetch-Site", "same-origin"),
        ],
        [
            ("origin", "https://fewia.example.test"),
            ("sec-fetch-mode", "cors"),
            ("sec-fetch-mode", "cors"),
        ],
        [
            ("origin", "https://fewia.example.test"),
            ("sec-fetch-dest", "empty"),
            ("sec-fetch-dest", "empty"),
        ],
        [("origin", "https://fewia.example.test"), ("sec-fetch-user", "?1")],
        [
            ("origin", "https://fewia.example.test"),
            ("sec-fetch-unknown", "synthetic"),
        ],
    ],
)
def test_unsafe_browser_requests_fail_before_mutation(
    client: TestClient,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    method: str,
    browser_headers: list[tuple[str, str]],
) -> None:
    _, auth = alb_headers
    response = client.request(
        method,
        "/grocery/signout",
        headers=[*auth.items(), *browser_headers],
        json={},
    )
    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "forbidden",
            "message": "The browser request is not allowed.",
        }
    }
    assert not response.headers.get_list("set-cookie")
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "browser_headers",
    [
        {},
        {"origin": "https://fewia.example.test"},
        {
            "origin": "https://fewia.example.test",
            "sec-fetch-site": "same-origin",
        },
        {
            "origin": "https://fewia.example.test",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        },
        {
            "origin": "https://fewia.example.test",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
        },
    ],
)
def test_cli_and_configured_browser_origin_ignore_forwarded_host(
    client: TestClient,
    session: Session,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    browser_headers: dict[str, str],
) -> None:
    _, auth = alb_headers
    workspace_headers: dict[str, str] = {}
    if browser_headers:
        user = session.get(User, 12)
        assert user is not None
        workspace_headers["X-FEWIA-Workspace"] = str(user.workspace_id)
    response = client.post(
        "/grocery/signout",
        headers={
            **auth,
            **browser_headers,
            **workspace_headers,
            "x-forwarded-host": "attacker.example.test",
            "x-forwarded-proto": "http",
            "forwarded": "host=attacker.example.test;proto=http",
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "content_type",
    [
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=synthetic",
        "text/plain",
    ],
)
def test_cross_site_forms_cannot_sign_out(
    client: TestClient,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    content_type: str,
) -> None:
    _, auth = alb_headers
    response = client.post(
        "/grocery/signout",
        headers={
            **auth,
            "Origin": "https://attacker.example.test",
            "X-Forwarded-Host": "attacker.example.test",
            "Content-Type": content_type,
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
        },
        content="confirm=true",
    )
    assert response.status_code == 403
    assert not response.headers.get_list("set-cookie")
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("status", [400, 401, 404, 405, 422, 503])
def test_grocery_errors_are_private(
    client: TestClient,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    _, auth = alb_headers
    if status == 400:
        response = client.get("/grocery/session", headers={**auth, "Host": "evil.test"})
    elif status == 401:
        response = client.get("/grocery/session")
    elif status == 404:
        response = client.get(f"/grocery/jobs/{uuid4()}", headers=auth)
    elif status == 405:
        response = client.delete("/grocery/session", headers=auth)
    elif status == 422:
        response = client.post("/grocery/plans", headers=auth, json={})
    else:

        def unavailable(*args: object, **kwargs: object) -> object:
            raise grocery.SpendingUnavailable()

        monkeypatch.setattr(grocery, "spending_input", unavailable)
        response = client.get("/grocery/config", headers=auth)
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert "error" in response.json()
    health = client.get("/healthz")
    assert health.status_code == 200
    assert "cache-control" not in health.headers


def test_unhandled_grocery_errors_are_private(
    client: TestClient,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, auth = alb_headers

    def unavailable(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(grocery, "require_spending", unavailable)
    with TestClient(
        app, base_url="http://localhost", raise_server_exceptions=False
    ) as errors:
        response = errors.get("/grocery/config", headers=auth)
    assert response.status_code == 500
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "The server could not complete the request.",
        }
    }


def test_chat_active_limit_counts_only_the_authenticated_owner(
    client: TestClient,
    session: Session,
    two_owner_headers: dict[int, dict[str, str]],
    owner_runtime: None,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
) -> None:
    for owner, auth in two_owner_headers.items():
        for index in range(3):
            first = client.post(
                "/grocery/chat/jobs",
                headers={**auth, "Idempotency-Key": f"rate-{index}"},
                json={"message": f"Owner {owner} plan", "monthly_limit_cents": 10000},
            )
            assert first.status_code == 202
        limited = client.post(
            "/grocery/chat/jobs",
            headers={**auth, "Idempotency-Key": "rate-second"},
            json={"message": "another plan", "monthly_limit_cents": 10000},
        )
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "60"
        assert limited.headers["cache-control"] == "private, no-store"
    assert mutation_admission == [
        (session, owner, "mutation") for owner in two_owner_headers for _ in range(3)
    ]


MUTATIONS = ("plan_job", "chat_job", "sync_job", "save", "apply", "discard")


def _mutation_request(
    session: Session, user_id: int, operation: str
) -> tuple[str, dict[str, object]]:
    if operation == "save":
        return "/grocery/plans", dict(PLAN)
    if operation == "plan_job":
        return "/grocery/jobs", {
            "request": {"meals": PLAN["meals"], "budget_period": "2026-11-01"},
            "monthly_limit_cents": 10000,
        }
    if operation == "chat_job":
        return "/grocery/chat/jobs", {
            "message": "plan bean tacos",
            "monthly_limit_cents": 10000,
        }
    if operation == "sync_job":
        session.add(
            PlaidItem(
                id="admission-item",
                user_id=user_id,
                provider_item_id="synthetic-provider-item",
                credential_ref="synthetic-reference",
            )
        )
        session.flush()
        return "/grocery/sync/jobs", {"item_id": "admission-item"}
    assert operation in ("apply", "discard")
    base_id = uuid4()
    session.add(PlanRevision(id=base_id, user_id=user_id, snapshot=dict(PLAN)))
    session.flush()
    proposal_id = create_proposal(
        session,
        user_id,
        base_id,
        [{"op": "set_servings", "recipe_id": "bean_tacos", "servings": 3}],
        constraints=ApplyConstraints(
            monthly_limit_cents=10000,
            plan_cap_cents=5000,
            diet="omnivore",
            ingredient_exclusions=[],
        ),
    )
    session.flush()
    return f"/grocery/proposals/{proposal_id}/{operation}", (
        {"plan_cap_cents": 5000} if operation == "apply" else {"confirm": True}
    )


def _mutation_state(session: Session) -> dict[str, object]:
    return {
        "jobs": [row.id for row in session.scalars(select(Job))],
        "outboxes": [row.id for row in session.scalars(select(JobOutbox))],
        "revisions": [row.id for row in session.scalars(select(PlanRevision))],
        "proposals": [
            (row.id, row.status, row.applied_plan_revision_id, row.updated_at)
            for row in session.scalars(select(PlanProposal))
        ],
    }


@pytest.mark.parametrize("operation", MUTATIONS)
def test_new_mutations_reserve_once_and_replays_reserve_nothing(
    client: TestClient,
    session: Session,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    owner_runtime: None,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    _, auth = alb_headers
    path, body = _mutation_request(session, 12, operation)
    headers = {**auth, "Idempotency-Key": "admitted"}
    before = _mutation_state(session)
    admission = job_submission if operation.endswith("_job") else security_admission
    reserve = admission.reserve_action
    commit = session.commit
    transactions: list[object] = []
    commits: list[str] = []

    def observe_reserve(
        db: Session,
        user_id: int,
        action: security_admission.Action,
        *,
        now: datetime | None = None,
    ) -> None:
        current = _mutation_state(db)
        if operation.endswith("_job"):
            for field in ("jobs", "outboxes"):
                previous_ids = before[field]
                current_ids = current[field]
                assert isinstance(previous_ids, list)
                assert isinstance(current_ids, list)
                assert len(current_ids) == len(previous_ids) + 1
                assert set(previous_ids) < set(current_ids)
                current[field] = previous_ids
        assert current == before
        reserve(db, user_id, action, now=now)
        transactions.append(db.get_transaction())

    def observe_commit() -> None:
        assert mutation_admission == [(session, 12, "mutation")]
        assert len(transactions) == 1
        assert session.get_transaction() is transactions[0]
        commits.append("commit")
        commit()

    monkeypatch.setattr(admission, "reserve_action", observe_reserve)
    monkeypatch.setattr(session, "commit", observe_commit)
    first = client.post(path, headers=headers, json=body)
    expected_status = 202 if operation.endswith("_job") else 200
    if operation == "save":
        expected_status = 201
    assert first.status_code == expected_status
    assert mutation_admission == [(session, 12, "mutation")]
    assert commits == ["commit"]
    monkeypatch.setattr(session, "commit", commit)
    if operation == "save":
        assert len(session.scalars(select(PlanRevision)).all()) == 1
        return

    def reject(
        db: Session,
        user_id: int,
        action: security_admission.Action,
        *,
        now: datetime | None = None,
    ) -> None:
        raise AssertionError("A replay MUST NOT reserve admission.")

    monkeypatch.setattr(admission, "reserve_action", reject)
    before = _mutation_state(session)
    second = client.post(path, headers=headers, json=body)
    assert second.status_code == first.status_code
    assert second.json() == first.json()
    assert mutation_admission == [(session, 12, "mutation")]
    assert _mutation_state(session) == before


@pytest.mark.parametrize("operation", MUTATIONS)
def test_mutation_limit_is_safe_and_preserves_database_state(
    client: TestClient,
    session: Session,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    owner_runtime: None,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    _, auth = alb_headers
    path, body = _mutation_request(session, 12, operation)
    before = _mutation_state(session)

    def reject(
        db: Session,
        user_id: int,
        action: security_admission.Action,
        *,
        now: datetime | None = None,
    ) -> None:
        assert db is session and user_id == 12 and action == "mutation"
        raise security_admission.AdmissionLimitError(37)

    admission = job_submission if operation.endswith("_job") else security_admission
    monkeypatch.setattr(admission, "reserve_action", reject)
    response = client.post(
        path, headers={**auth, "Idempotency-Key": "limited"}, json=body
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "37"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "error": {
            "code": "too_many_requests",
            "message": "Action limit reached. Try again later.",
        }
    }
    assert _mutation_state(session) == before


@pytest.mark.parametrize("operation", MUTATIONS)
@pytest.mark.parametrize("status", ["disabled", "deleting"])
def test_owner_changed_after_authentication_cannot_mutate(
    client: TestClient,
    session: Session,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    owner_runtime: None,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    status: str,
) -> None:
    _, auth = alb_headers
    path, body = _mutation_request(session, 12, operation)
    before = _mutation_state(session)
    admission = job_submission if operation.endswith("_job") else security_admission
    reserve = admission.reserve_action
    attempts: list[int] = []

    def change_owner(
        db: Session,
        user_id: int,
        action: security_admission.Action,
        *,
        now: datetime | None = None,
    ) -> None:
        assert db is session and user_id == 12 and action == "mutation"
        attempts.append(user_id)
        db.execute(update(User).where(User.id == user_id).values(status=status))
        reserve(db, user_id, action, now=now)

    monkeypatch.setattr(admission, "reserve_action", change_owner)
    response = client.post(
        path, headers={**auth, "Idempotency-Key": "owner-changed"}, json=body
    )
    assert attempts == [12]
    assert mutation_admission == []
    assert response.status_code == 403
    assert "retry-after" not in response.headers
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "error": {"code": "forbidden", "message": "Action owner is unavailable."}
    }
    assert _mutation_state(session) == before


def test_reads_and_template_suggestions_do_not_reserve_admission(
    client: TestClient,
    session: Session,
    alb_headers: tuple[AuthSettings, dict[str, str]],
    owner_runtime: None,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
) -> None:
    _, auth = alb_headers
    path, _ = _mutation_request(session, 12, "apply")
    for read_path in (
        "/grocery/session",
        "/grocery/config",
        "/grocery/providers",
        path,
    ):
        if read_path == path:
            read_path = read_path.removesuffix("/apply")
        assert client.get(read_path, headers=auth).status_code == 200
    templates = client.post(
        "/grocery/templates",
        headers=auth,
        json={"budget_period": "2026-11-01", "monthly_limit_cents": 10000},
    )
    assert templates.status_code == 200
    assert mutation_admission == []
