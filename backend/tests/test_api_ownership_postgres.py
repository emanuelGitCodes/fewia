import hashlib
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.api import chat, evidence, grocery, plan_templates, proposals, sync
from app.auth import AlbTokenVerifier, AuthSettings
from app.deps import (
    get_kroger_cipher,
    get_kroger_client,
    get_kroger_pairing_cipher,
    get_provider_settings,
    get_session,
)
from app.evidence_models import GroceryEvidence
from app.job_models import Job, JobOutbox
from app.kroger_customer import store_tokens
from app.kroger_models import KrogerCustomerToken
from app.main import create_app
from app.models import User
from app.plaid_models import PlaidItem, PlaidTransaction
from app.plan_models import PlanProposal, PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import (
    CART_ADD_PATH,
    PRODUCTS_PATH,
    TOKEN_PATH,
    CustomerTokens,
    KrogerClient,
)
from app.providers.kroger_fixture import (
    ACCESS_TOKEN,
    FIXTURE_CLIENT_ID,
    FIXTURE_CLIENT_SECRET,
    FIXTURE_CODE,
    FIXTURE_PREFIX,
    REFRESH_TOKEN,
    fixture_handler,
)
from app.runtime_database_access import provision_runtime_access
from app.security_models import KrogerOwner, QuotaCounter, SecurityIntent
from app.services import kroger_security, security_admission
from tests.conftest import require_test_database_url
from tests.test_runtime_database_access import PgConnection
from tests.test_runtime_database_access import (
    orm_admin as orm_admin,
)
from tests.test_runtime_database_access import (
    orm_connection as orm_connection,
)

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
PLAN: dict[str, object] = {
    "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
    "pantry_ingredient_ids": [],
    "plan_cap_cents": 5000,
}
OPERATIONS: list[dict[str, object]] = [
    {"op": "set_servings", "recipe_id": "bean_tacos", "servings": 3}
]
NOTICE = (
    "Estimated from the demo price catalog. Store prices, availability, taxes, "
    "delivery fees, and tips are not verified."
)
KROGER = "/grocery/kroger"


def _private(response: httpx.Response, status: int) -> None:
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "private, no-store"


def _error(response: httpx.Response, status: int, message: str) -> None:
    _private(response, status)
    codes = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        422: "unprocessable_entity",
    }
    assert response.json() == {"error": {"code": codes[status], "message": message}}


@dataclass
class Matrix:
    api: TestClient
    factory: sessionmaker[Session]
    owners: tuple[int, int]
    headers: dict[int, dict[str, str]]
    revisions: dict[int, UUID]
    proposal_ids: dict[int, UUID]
    evidence_ids: dict[int, str]
    parents: dict[int, str]
    calls: list[tuple[str, str]]
    request_roles: list[str]

    def state(self) -> dict[str, list[tuple[object, ...]]]:
        with self.factory() as session:
            assert session.scalar(text("SELECT current_role")) == "fewia_app"
            statements = {
                "jobs": select(Job.__table__).where(Job.user_id.in_(self.owners)),
                "outbox": select(JobOutbox.__table__)
                .join(Job, Job.id == JobOutbox.job_id)
                .where(Job.user_id.in_(self.owners)),
                "plans": select(PlanRevision.__table__).where(
                    PlanRevision.user_id.in_(self.owners)
                ),
                "proposals": select(PlanProposal.__table__).where(
                    PlanProposal.user_id.in_(self.owners)
                ),
                "evidence": select(GroceryEvidence.__table__).where(
                    GroceryEvidence.user_id.in_(self.owners)
                ),
                "tokens": select(KrogerCustomerToken.__table__).where(
                    KrogerCustomerToken.user_id.in_(self.owners)
                ),
                "intents": select(SecurityIntent.__table__).where(
                    SecurityIntent.user_id.in_(self.owners)
                ),
                "owners": select(KrogerOwner.__table__).where(
                    KrogerOwner.user_id.in_(self.owners)
                ),
                "quotas": select(QuotaCounter.__table__).where(
                    QuotaCounter.scope_key.in_((0, *self.owners))
                ),
                "items": select(PlaidItem.__table__).where(
                    PlaidItem.user_id.in_(self.owners)
                ),
            }
            return {
                name: sorted(
                    (tuple(row) for row in session.execute(statement)), key=repr
                )
                for name, statement in statements.items()
            }


@pytest.fixture
def matrix(
    orm_admin: PgConnection,
    orm_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Matrix]:
    require_test_database_url()
    auth = AuthSettings(
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
        auth_logout_url="https://identity.example.test/logout",
    )
    settings = GroceryProviderSettings(
        bedrock_model_id="synthetic-unused-model",
        spending_source="plaid_sandbox",
        kroger_mode="live",
        kroger_redirect_uri="http://localhost/grocery/kroger/callback",
        kroger_return_url="http://localhost/prototype",
    )
    monkeypatch.setattr("app.deps.load_auth_settings", lambda: auth)
    monkeypatch.setattr("app.deps.load_provider_settings", lambda: settings)
    monkeypatch.setattr(proposals, "get_provider_settings", lambda: settings)
    monkeypatch.setattr(sync, "_plaid_is_configured", lambda: True)
    for module in (grocery, chat, plan_templates):
        monkeypatch.setattr(module, "_ny_now", lambda: NOW)
    monkeypatch.setattr(security_admission, "database_utc_now", lambda session: NOW)
    monkeypatch.setattr(
        "app.services.job_submission.database_utc_now", lambda session: NOW
    )
    monkeypatch.setattr(kroger_security.time, "time", lambda: NOW.timestamp())

    def forbid_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests MUST NOT use the network.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbid_network)
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    verifier = AlbTokenVerifier(
        auth, key_fetch=lambda region, kid: pem, clock=lambda: NOW.timestamp()
    )
    monkeypatch.setattr("app.deps.get_alb_verifier", lambda settings: verifier)
    factory = sessionmaker(
        bind=orm_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    cipher = Fernet(Fernet.generate_key())
    pairing_cipher = Fernet(Fernet.generate_key())
    revisions: dict[int, UUID] = {}
    proposal_ids: dict[int, UUID] = {}
    evidence_ids: dict[int, str] = {}
    parents: dict[int, str] = {}
    headers: dict[int, dict[str, str]] = {}
    assert (
        orm_connection.exec_driver_sql("SELECT current_role").scalar_one()
        != "fewia_app"
    )
    with factory() as session:
        users = [
            User(
                display_name=f"Synthetic owner {index}",
                auth_issuer=auth.auth_issuer,
                auth_subject=f"matrix-{uuid4()}",
            )
            for index in range(2)
        ]
        session.add_all(users)
        session.flush()
        owners = (users[0].id, users[1].id)
        for index, user in enumerate(users):
            owner = user.id
            session.add(KrogerOwner(user_id=owner))
            session.add(
                PlaidItem(
                    id=f"matrix-{owner}",
                    user_id=owner,
                    provider_item_id=f"matrix-provider-{owner}",
                    credential_ref="synthetic-unused-reference",
                    cursor="synthetic-ready-cursor",
                    last_synced_at=NOW,
                )
            )
            revisions[owner] = uuid4()
            proposal_ids[owner] = uuid4()
            evidence_ids[owner] = hashlib.sha256(str(uuid4()).encode()).hexdigest()
            parents[owner] = str(uuid4())
            session.add(
                PlanRevision(
                    id=revisions[owner], user_id=owner, snapshot=deepcopy(PLAN)
                )
            )
            session.flush()
            session.add(
                PlanProposal(
                    id=proposal_ids[owner],
                    user_id=owner,
                    base_plan_revision_id=revisions[owner],
                    operations=deepcopy(OPERATIONS),
                    apply_constraints={
                        "monthly_limit_cents": 10000,
                        "plan_cap_cents": 5000,
                        "diet": "omnivore",
                        "ingredient_exclusions": [],
                    },
                )
            )
            session.add(
                GroceryEvidence(
                    id=evidence_ids[owner], user_id=owner, snapshot={"owner": owner}
                )
            )
            session.add(
                Job(
                    id=parents[owner],
                    user_id=owner,
                    kind="agent",
                    request_key="chat:seeded-history",
                    status="succeeded",
                    payload={"operation": "chat", "message": "plan bean tacos"},
                    result={
                        "answer": f"Owner {owner} plan",
                        "request": {
                            "meals": PLAN["meals"],
                            "budget_period": "2026-11-01",
                        },
                    },
                )
            )
            for label, day, amount, pending, grocery_purchase in (
                ("posted", date(2026, 11, 1), 1000 + index * 2000, False, True),
                ("pending", date(2026, 11, 30), 100 + index * 200, True, True),
                ("before", date(2026, 10, 31), 90000, False, True),
                ("after", date(2026, 12, 1), 90000, False, True),
                ("other", date(2026, 11, 12), 90000, False, False),
            ):
                session.add(
                    PlaidTransaction(
                        item_id=f"matrix-{owner}",
                        transaction_id=label,
                        account_id="synthetic-account",
                        amount_cents=amount,
                        currency="USD",
                        transaction_date=day,
                        pending=pending,
                        is_grocery=grocery_purchase,
                        classification_version="synthetic-v1",
                    )
                )
            session.flush()
            ticket = kroger_security.issue_pairing_ticket(session, owner)
            proof = kroger_security.redeem_pairing_ticket(session, owner, ticket)
            headers[owner] = {
                "x-amzn-oidc-data": jwt.encode(
                    {"sub": user.auth_subject},
                    key,
                    algorithm="ES256",
                    headers={
                        "kid": "11111111-1111-4111-8111-111111111111",
                        "signer": auth.alb_signer_arn,
                        "client": auth.auth_client_id,
                        "iss": auth.auth_issuer,
                        "exp": int(NOW.timestamp()) + 3600,
                    },
                ),
                "x-fewia-kroger-owner": proof,
            }
        store_tokens(
            session,
            owners[0],
            cipher,
            CustomerTokens(ACCESS_TOKEN, REFRESH_TOKEN, 1800),
        )
        session.commit()
    provision_runtime_access(orm_admin, "A1" * 16)
    orm_connection.exec_driver_sql("SET LOCAL ROLE fewia_app")
    calls: list[tuple[str, str]] = []
    request_roles: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return fixture_handler(request)

    def request_session() -> Iterator[Session]:
        with factory() as session:
            role = session.scalar(text("SELECT current_role"))
            assert role == "fewia_app"
            request_roles.append(str(role))
            yield session

    application = create_app()
    with httpx.Client(transport=httpx.MockTransport(handle), trust_env=False) as http:
        provider = KrogerClient(
            FIXTURE_CLIENT_ID,
            FIXTURE_CLIENT_SECRET,
            base_url=f"http://localhost{FIXTURE_PREFIX}",
            client=http,
            fixture=True,
        )
        application.dependency_overrides.update(
            {
                get_session: request_session,
                evidence.get_session_factory: lambda: factory,
                get_provider_settings: lambda: settings,
                get_kroger_client: lambda: provider,
                get_kroger_cipher: lambda: cipher,
                get_kroger_pairing_cipher: lambda: pairing_cipher,
            }
        )
        try:
            with TestClient(application, base_url="http://localhost") as api:
                yield Matrix(
                    api,
                    factory,
                    owners,
                    headers,
                    revisions,
                    proposal_ids,
                    evidence_ids,
                    parents,
                    calls,
                    request_roles,
                )
        finally:
            application.dependency_overrides.clear()
            assert (
                orm_connection.exec_driver_sql("SELECT current_role").scalar_one()
                == "fewia_app"
            )
            orm_connection.exec_driver_sql("RESET ROLE")


def test_persisted_owner_spending_budget_and_plan_creation(matrix: Matrix) -> None:
    for index, owner in enumerate(matrix.owners):
        auth = matrix.headers[owner]
        posted, pending = 1000 + index * 2000, 100 + index * 200
        config = matrix.api.get("/grocery/config", headers=auth)
        _private(config, 200)
        assert config.json()["source"] == "plaid_sandbox"
        assert config.json()["posted_cents"] == posted
        assert config.json()["pending_cents"] == pending
        assert config.json()["notice"] == NOTICE
        templates = matrix.api.post(
            "/grocery/templates",
            headers=auth,
            json={"budget_period": "2026-11-01", "monthly_limit_cents": 10000},
        )
        _private(templates, 200)
        assert templates.json()["budget"]["available_cents"] == 10000 - posted
        assert templates.json()["budget"]["pending_cents"] == pending
        assert templates.json()["notice"] == NOTICE
        before = matrix.state()
        saved = matrix.api.post("/grocery/plans", headers=auth, json=PLAN)
        _private(saved, 201)
        assert set(saved.json()) == {"plan_revision_id"}
        with matrix.factory() as session:
            row = session.get(PlanRevision, UUID(saved.json()["plan_revision_id"]))
            assert row is not None and row.user_id == owner and row.snapshot == PLAN
        after = matrix.state()
        assert len(after["plans"]) == len(before["plans"]) + 1
        for table in before.keys() - {"plans", "quotas"}:
            assert after[table] == before[table]
    assert matrix.request_roles and set(matrix.request_roles) == {"fewia_app"}
    assert matrix.calls == []


@pytest.mark.parametrize("kind", ["plan", "chat", "sync"])
def test_owner_job_creation_replay_reads_and_outbox(matrix: Matrix, kind: str) -> None:
    path = {
        "plan": "/grocery/jobs",
        "chat": "/grocery/chat/jobs",
        "sync": "/grocery/sync/jobs",
    }[kind]
    accepted: dict[int, str] = {}
    for index, owner in enumerate(matrix.owners):
        body: dict[str, object]
        if kind == "sync":
            body = {"item_id": f"matrix-{owner}"}
        elif kind == "chat":
            body = {
                "message": "use my plan",
                "monthly_limit_cents": 10000,
                "plan_revision_id": str(matrix.revisions[owner]),
                "previous_job_id": matrix.parents[owner],
            }
        else:
            body = {
                "request": {"meals": PLAN["meals"], "budget_period": "2026-11-01"},
                "monthly_limit_cents": 10000,
            }
        auth = matrix.headers[owner]
        headers = {**auth, "Idempotency-Key": "shared-owner-key"}
        first = matrix.api.post(path, headers=headers, json=body)
        _private(first, 202)
        job_id = first.json()["job_id"]
        accepted[owner] = job_id
        assert first.json() == {"job_id": job_id, "status": "queued"}
        before_replay = matrix.state()
        replay = matrix.api.post(path, headers=headers, json=body)
        _private(replay, 202)
        assert replay.json() == first.json()
        assert matrix.state() == before_replay
        own = matrix.api.get(f"{path}/{job_id}", headers=auth)
        _private(own, 200)
        expected = {
            "id": job_id,
            "status": "queued",
            "result": None,
            "error_code": None,
        }
        if kind == "plan":
            expected["error_detail"] = None
        assert own.json() == expected
        with matrix.factory() as session:
            job = session.get(Job, job_id)
            assert job is not None and job.user_id == owner
            assert job.request_namespace == kind
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(JobOutbox)
                    .where(JobOutbox.job_id == job_id)
                )
                == 1
            )
            if kind == "sync":
                assert job.payload["item_id"] == f"matrix-{owner}"
            else:
                assert job.payload["spending"]["posted_cents"] == 1000 + index * 2000
                assert job.payload["spending"]["pending_cents"] == 100 + index * 200
            if kind == "chat":
                assert job.payload["plan_revision"] == {
                    "id": str(matrix.revisions[owner]),
                    "snapshot": PLAN,
                }
                assert job.payload["history"] == [
                    {"role": "user", "text": "plan bean tacos"},
                    {"role": "assistant", "text": f"Owner {owner} plan"},
                ]
            assert (
                session.scalar(
                    select(func.sum(QuotaCounter.count)).where(
                        QuotaCounter.action == "mutation",
                        QuotaCounter.scope_key == owner,
                    )
                )
                == 1
            )
    assert len(set(accepted.values())) == 2
    before_denials = matrix.state()
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        for requested in (accepted[other], str(uuid4())):
            _error(
                matrix.api.get(f"{path}/{requested}", headers=matrix.headers[owner]),
                404,
                "Job not found",
            )
    assert matrix.state() == before_denials
    with matrix.factory() as session:
        assert set(
            session.execute(
                select(Job.id, Job.user_id)
                .join(JobOutbox, JobOutbox.job_id == Job.id)
                .where(Job.user_id.in_(matrix.owners))
            ).all()
        ) == {(job_id, owner) for owner, job_id in accepted.items()}
    assert matrix.calls == []


@pytest.mark.parametrize(
    "reference", ["previous_job_id", "plan_revision_id", "item_id"]
)
def test_foreign_and_missing_job_inputs_preserve_both_owners(
    matrix: Matrix, reference: str
) -> None:
    before = matrix.state()
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        if reference == "item_id":
            path = "/grocery/sync/jobs"
            foreign = f"matrix-{other}"
            base: dict[str, object] = {}
            message = "Plaid Item is missing or not owned"
        else:
            path = "/grocery/chat/jobs"
            foreign = (
                matrix.parents[other]
                if reference == "previous_job_id"
                else str(matrix.revisions[other])
            )
            base = {"message": "use my plan", "monthly_limit_cents": 10000}
            message = (
                "Job not found"
                if reference == "previous_job_id"
                else "The plan is not available. Refresh the page and try again."
            )
        for value in (foreign, str(uuid4())):
            response = matrix.api.post(
                path,
                headers={
                    **matrix.headers[owner],
                    "Idempotency-Key": "denied-reference",
                },
                json={**base, reference: value},
            )
            _error(response, 404, message)
            assert matrix.state() == before
    assert matrix.calls == []


@pytest.mark.parametrize("action", ["apply", "discard"])
def test_proposals_mutate_only_the_verified_owner(matrix: Matrix, action: str) -> None:
    body = {"plan_cap_cents": 4000} if action == "apply" else {"confirm": True}
    preview = {**PLAN, "meals": [{"recipe_id": "bean_tacos", "servings": 3}]}
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        before = matrix.state()
        for requested in (matrix.proposal_ids[other], uuid4()):
            path = f"/grocery/proposals/{requested}"
            _error(
                matrix.api.get(path, headers=matrix.headers[owner]),
                404,
                "The plan proposal was not found.",
            )
            _error(
                matrix.api.post(
                    f"{path}/{action}", headers=matrix.headers[owner], json=body
                ),
                404,
                "The plan proposal was not found.",
            )
            assert matrix.state() == before
        path = f"/grocery/proposals/{matrix.proposal_ids[owner]}"
        own = matrix.api.get(path, headers=matrix.headers[owner])
        _private(own, 200)
        assert own.json() == {
            "id": str(matrix.proposal_ids[owner]),
            "status": "pending",
            "base_plan_revision_id": str(matrix.revisions[owner]),
            "operations": OPERATIONS,
            "preview": preview,
            "applied_plan_revision_id": None,
        }
        response = matrix.api.post(
            f"{path}/{action}", headers=matrix.headers[owner], json=body
        )
        _private(response, 200)
        with matrix.factory() as session:
            row = session.get(PlanProposal, matrix.proposal_ids[owner])
            assert row is not None and row.user_id == owner
            assert row.status == ("applied" if action == "apply" else "discarded")
            if action == "apply":
                revision = session.get(PlanRevision, row.applied_plan_revision_id)
                assert revision is not None and revision.user_id == owner
                assert revision.snapshot == {**preview, "plan_cap_cents": 4000}
                assert response.json() == {
                    "plan_revision_id": str(revision.id),
                    "snapshot": revision.snapshot,
                }
            else:
                assert row.applied_plan_revision_id is None
                assert response.json() == {"status": "discarded"}
            other_row = session.get(PlanProposal, matrix.proposal_ids[other])
            assert other_row is not None
            other_before = next(
                row for row in before["proposals"] if row[0] == other_row.id
            )
            assert (
                tuple(
                    session.execute(
                        select(PlanProposal.__table__).where(
                            PlanProposal.id == other_row.id
                        )
                    ).one()
                )
                == other_before
            )
        after = matrix.state()
        for table in before.keys() - {"plans", "proposals", "quotas"}:
            assert after[table] == before[table]
        replay = matrix.api.post(
            f"{path}/{action}", headers=matrix.headers[owner], json=body
        )
        _private(replay, 200)
        assert replay.json() == response.json()
        assert matrix.state() == after
    assert matrix.calls == []


def test_evidence_is_private_and_immutable_trigger_stays_enabled(
    matrix: Matrix,
) -> None:
    before = matrix.state()
    with matrix.factory() as session:
        trigger = session.execute(
            text(
                "SELECT pg_get_triggerdef(oid), tgenabled FROM pg_trigger "
                "WHERE tgrelid = 'public.grocery_evidence'::regclass "
                "AND tgname = 'fewia_grocery_evidence_immutable'"
            )
        ).one()
        assert trigger[1] == "O"
        for table in ("plaid_items", "plaid_transactions", "daily_finance"):
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert (
                    session.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "current_role, :table, :privilege)"
                        ),
                        {"table": table, "privilege": privilege},
                    )
                    is False
                )
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        own_id = matrix.evidence_ids[owner]
        own = matrix.api.get(
            f"/grocery/evidence/{own_id}", headers=matrix.headers[owner]
        )
        _private(own, 200)
        assert own.json() == {"revision_id": own_id, "snapshot": {"owner": owner}}
        for requested in (matrix.evidence_ids[other], "f" * 64, "invalid"):
            _error(
                matrix.api.get(
                    f"/grocery/evidence/{requested}", headers=matrix.headers[owner]
                ),
                404,
                "Evidence not found",
            )
    assert matrix.state() == before
    with matrix.factory() as session:
        assert tuple(
            session.execute(
                text(
                    "SELECT pg_get_triggerdef(oid), tgenabled FROM pg_trigger "
                    "WHERE tgrelid = 'public.grocery_evidence'::regclass "
                    "AND tgname = 'fewia_grocery_evidence_immutable'"
                )
            ).one()
        ) == tuple(trigger)


def test_static_authentication_browser_and_validation_failures(matrix: Matrix) -> None:
    before = matrix.state()
    owner = matrix.owners[0]
    for headers in ({}, {"x-user-id": str(owner)}, {"x-amzn-oidc-data": "invalid"}):
        _error(
            matrix.api.get("/grocery/config", headers=headers),
            401,
            "Authentication is invalid.",
        )
    blocked = matrix.api.post(
        "/grocery/plans",
        headers={**matrix.headers[owner], "Origin": "https://attacker.example.test"},
        json=PLAN,
    )
    _error(blocked, 403, "The browser request is not allowed.")
    invalid = matrix.api.post(
        f"{KROGER}/cart/preview",
        headers=matrix.headers[owner],
        json={
            "plan_revision_id": "synthetic-private-invalid",
            "location_id": "invalid",
        },
    )
    _private(invalid, 422)
    assert invalid.json() == {
        "error": {
            "code": "validation_error",
            "message": "The request has invalid parameters.",
            "detail": [],
        }
    }
    assert matrix.state() == before
    assert matrix.calls == []


def test_kroger_owners_bind_connection_oauth_preview_and_cart(matrix: Matrix) -> None:
    first_owner, second_owner = matrix.owners
    for owner, connected in ((first_owner, True), (second_owner, False)):
        connection = matrix.api.get(
            f"{KROGER}/connection", headers=matrix.headers[owner]
        )
        _private(connection, 200)
        assert connection.json() == {"connected": connected}
    assert matrix.calls == []
    targets: dict[int, str] = {}
    for owner in matrix.owners:
        response = matrix.api.post(f"{KROGER}/connect", headers=matrix.headers[owner])
        _private(response, 200)
        assert set(response.json()) == {"authorization_url"}
        target = response.json()["authorization_url"]
        assert target.startswith("/api/grocery/kroger/connect/start?ticket=")
        targets[owner] = target.removeprefix("/api")
    assert targets[first_owner] != targets[second_owner]
    states: dict[int, str] = {}
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        before = matrix.state()
        for target in (targets[other], f"{KROGER}/connect/start?ticket={'x' * 43}"):
            rejected = matrix.api.get(
                target, headers=matrix.headers[owner], follow_redirects=False
            )
            _error(rejected, 422, "Kroger action is invalid or expired.")
            assert matrix.state() == before
        started = matrix.api.get(
            targets[owner], headers=matrix.headers[owner], follow_redirects=False
        )
        _private(started, 302)
        assert "set-cookie" not in started.headers
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        assert len(state) == 43
        states[owner] = state
        after = matrix.state()
        _error(
            matrix.api.get(
                targets[owner], headers=matrix.headers[owner], follow_redirects=False
            ),
            422,
            "Kroger action is invalid or expired.",
        )
        assert matrix.state() == after
    assert states[first_owner] != states[second_owner]
    assert matrix.calls == []
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        before = matrix.state()
        for state in (states[other], "x" * 43):
            rejected = matrix.api.get(
                f"{KROGER}/callback",
                headers=matrix.headers[owner],
                params={"code": FIXTURE_CODE, "state": state},
                follow_redirects=False,
            )
            _private(rejected, 302)
            assert rejected.content == b""
            assert (
                rejected.headers["location"]
                == "http://localhost/prototype?kroger=error"
            )
            assert matrix.state() == before
        calls_before = len(matrix.calls)
        callback = matrix.api.get(
            f"{KROGER}/callback",
            headers=matrix.headers[owner],
            params={"code": FIXTURE_CODE, "state": states[owner]},
            follow_redirects=False,
        )
        _private(callback, 302)
        assert (
            callback.headers["location"]
            == "http://localhost/prototype?kroger=connected"
        )
        assert matrix.calls[calls_before:] == [
            ("POST", f"{FIXTURE_PREFIX}{TOKEN_PATH}")
        ]
        after = matrix.state()
        replay = matrix.api.get(
            f"{KROGER}/callback",
            headers=matrix.headers[owner],
            params={"code": FIXTURE_CODE, "state": states[owner]},
            follow_redirects=False,
        )
        _private(replay, 302)
        assert replay.headers["location"] == "http://localhost/prototype?kroger=error"
        assert matrix.state() == after
        assert len(matrix.calls) == calls_before + 1
        for table in before.keys() - {"tokens", "intents", "quotas"}:
            assert after[table] == before[table]
        assert [row for row in after["tokens"] if row[0] == other] == [
            row for row in before["tokens"] if row[0] == other
        ]
    for owner in matrix.owners:
        connection = matrix.api.get(
            f"{KROGER}/connection", headers=matrix.headers[owner]
        )
        _private(connection, 200)
        assert connection.json() == {"connected": True}
    assert len(matrix.calls) == 2
    confirmations: dict[int, str] = {}
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        before = matrix.state()
        calls_before = len(matrix.calls)
        for revision in (matrix.revisions[other], uuid4()):
            rejected = matrix.api.post(
                f"{KROGER}/cart/preview",
                headers=matrix.headers[owner],
                json={"plan_revision_id": str(revision), "location_id": "FX000001"},
            )
            _error(rejected, 404, "The plan revision was not found.")
            assert matrix.state() == before
            assert len(matrix.calls) == calls_before
        preview = matrix.api.post(
            f"{KROGER}/cart/preview",
            headers=matrix.headers[owner],
            json={
                "plan_revision_id": str(matrix.revisions[owner]),
                "location_id": "FX000001",
            },
        )
        _private(preview, 200)
        body = preview.json()
        assert set(body) == {
            "items",
            "unmatched",
            "source",
            "confirmation_token",
            "expires_in_seconds",
        }
        assert body["source"] == "fixture"
        assert body["expires_in_seconds"] == 300
        assert body["items"]
        confirmations[owner] = body["confirmation_token"]
        assert isinstance(confirmations[owner], str) and confirmations[owner]
        with matrix.factory() as session:
            intent = session.scalars(
                select(SecurityIntent).where(
                    SecurityIntent.digest
                    == hashlib.sha256(confirmations[owner].encode()).hexdigest()
                )
            ).one()
            assert intent.user_id == owner and intent.state == "pending"
            assert set(intent.details) == {
                "action_id",
                "input_sha256",
                "pairing_generation",
                "connection_version",
            }
    for owner, other in (matrix.owners, matrix.owners[::-1]):
        before = matrix.state()
        calls_before = len(matrix.calls)
        for token in (confirmations[other], "synthetic-missing-confirmation"):
            rejected = matrix.api.post(
                f"{KROGER}/cart/add",
                headers=matrix.headers[owner],
                json={"confirmation_token": token},
            )
            _error(rejected, 422, "Kroger action is invalid or expired.")
            assert matrix.state() == before
            assert len(matrix.calls) == calls_before
        added = matrix.api.post(
            f"{KROGER}/cart/add",
            headers=matrix.headers[owner],
            json={"confirmation_token": confirmations[owner]},
        )
        _private(added, 204)
        assert added.content == b""
        assert matrix.calls[calls_before:] == [
            ("PUT", f"{FIXTURE_PREFIX}{CART_ADD_PATH}")
        ]
        after = matrix.state()
        replay = matrix.api.post(
            f"{KROGER}/cart/add",
            headers=matrix.headers[owner],
            json={"confirmation_token": confirmations[owner]},
        )
        _private(replay, 204)
        assert replay.content == b""
        assert matrix.state() == after
        assert len(matrix.calls) == calls_before + 1
        for table in before.keys() - {"intents", "quotas"}:
            assert after[table] == before[table]
        assert [row for row in after["intents"] if row[1] == other] == [
            row for row in before["intents"] if row[1] == other
        ]
        with matrix.factory() as session:
            intent = session.scalars(
                select(SecurityIntent).where(
                    SecurityIntent.digest
                    == hashlib.sha256(confirmations[owner].encode()).hexdigest()
                )
            ).one()
            assert intent.user_id == owner and intent.state == "succeeded"
            assert intent.details["outcome"] == "added"
            assert (
                session.scalar(
                    select(func.sum(QuotaCounter.count)).where(
                        QuotaCounter.action == "retailer",
                        QuotaCounter.scope_key == owner,
                    )
                )
                == 3
            )
    assert sum(path.endswith(CART_ADD_PATH) for _, path in matrix.calls) == 2
    assert sum(path.endswith(TOKEN_PATH) for _, path in matrix.calls) == 3
    assert all(
        path
        in {
            f"{FIXTURE_PREFIX}{suffix}"
            for suffix in (TOKEN_PATH, PRODUCTS_PATH, CART_ADD_PATH)
        }
        for _, path in matrix.calls
    )
