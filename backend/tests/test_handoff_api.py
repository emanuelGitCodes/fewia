"""Tests for Instacart development shopping-list handoff HTTP routes."""

import copy
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Connection, Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from test_evidence_contract import genuine_planning, inputs
from test_handoff_intents import SUCCESS_URL, UNSAFE_URL, VIEW_FIELDS, shopping_payload

from app import models
from app.api import handoff as handoff_api
from app.api.handoff_models import (
    DENIED,
    JOB_MISSING,
    NO_ITEMS,
    PLANNING_KEYS,
    REBUILD,
    HandoffRouteError,
    job_shopping_payload,
)
from app.api.handoff_types import CreateHandoffBody
from app.db import Base
from app.evidence_models import GroceryEvidence
from app.handoff_models import ShoppingHandoff
from app.job_models import Job
from app.main import app as main_app
from app.provider_settings import GroceryProviderSettings, ProviderConfigurationError
from app.providers.instacart import InstacartRejected, InstacartUncertain
from app.services.evidence_contract import canonical_json
from app.services.evidence_store import save_plan_evidence
from app.services.handoff_intents import HandoffNotFound, prepare_handoff

SECRET = "sk-test-not-for-models"
CHAT_EXTRA: dict[str, object] = {
    "status": "planned",
    "answer": "Here is an estimated plan.",
    "tool_trace": [{"marker": SECRET}],
    "model_turns": 2,
    "planner_revisions": 1,
    "usage": {"inputTokens": 9, "outputTokens": 4},
}
BEAN_PANTRY = [
    "black_beans",
    "cumin",
    "olive_oil",
    "onion",
    "salsa",
    "salt",
    "tortillas",
]


class FakeProvider:
    def __init__(self, outcome: str | BaseException) -> None:
        self.outcome = outcome
        self.payloads: list[dict[str, object]] = []
        self.closed = 0

    def create_link(self, payload: dict[str, object]) -> str:
        self.payloads.append(payload)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def close(self) -> None:
        self.closed += 1


@pytest.fixture()
def handoff_engine(tmp_path: Path) -> Iterator[Engine]:
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'handoff-api.db'}",
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

    tables = [
        models.User.__table__,
        Job.__table__,
        GroceryEvidence.__table__,
        ShoppingHandoff.__table__,
    ]
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
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.exception_handlers.update(main_app.exception_handlers)
    app.include_router(handoff_api.router)
    app.dependency_overrides[handoff_api.get_session_factory] = lambda: factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(handoff_api.get_session_factory, None)


def planning_result(
    planning: dict[str, object], revision: str, extra: dict[str, object] | None = None
) -> dict[str, object]:
    result = {key: planning[key] for key in PLANNING_KEYS}
    if "meal_nutrition" in planning:
        result["meal_nutrition"] = planning["meal_nutrition"]
    result["evidence_revision_id"] = revision
    if extra is not None:
        result.update(extra)
    return result


def add_job(
    factory: sessionmaker[Session],
    planning: dict[str, object],
    revision: str,
    *,
    extra: dict[str, object] | None = None,
    user_id: int = 1,
    status: str = "succeeded",
    kind: str = "agent",
) -> str:
    job = Job(
        user_id=user_id,
        kind=kind,
        request_key=str(uuid4()),
        status=status,
        payload={"marker": SECRET},
        result=planning_result(planning, revision, extra),
    )
    with factory.begin() as session:
        session.add(job)
        session.flush()
        return job.id


def accepted_job(
    factory: sessionmaker[Session],
    extra: dict[str, object] | None = None,
    **request_overrides: object,
) -> str:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed, **request_overrides)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    return add_job(factory, planning, revision, extra=extra)


def error_message(response: Response, secret: str = SECRET) -> str:
    data = response.json()
    rendered = json.dumps(data)
    assert secret not in rendered
    assert "attempt_token" not in rendered
    return str(data["error"]["message"])


def view_body(response: Response) -> dict[str, object]:
    data = response.json()
    rendered = json.dumps(data)
    assert SECRET not in rendered
    assert "attempt_token" not in rendered
    assert set(data) == VIEW_FIELDS
    return cast(dict[str, object], data)


def install_provider(
    monkeypatch: pytest.MonkeyPatch, outcome: str | BaseException
) -> list[FakeProvider]:
    made: list[FakeProvider] = []

    def build(settings: object) -> FakeProvider:
        del settings
        provider = FakeProvider(outcome)
        made.append(provider)
        return provider

    monkeypatch.setattr(handoff_api, "build_instacart", build)
    monkeypatch.setattr(handoff_api, "load_provider_settings", lambda: object())
    return made


def forbid_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def settings() -> object:
        raise AssertionError("load_provider_settings MUST NOT run")

    def build(value: object) -> FakeProvider:
        del value
        raise AssertionError("build_instacart MUST NOT run")

    monkeypatch.setattr(handoff_api, "load_provider_settings", settings)
    monkeypatch.setattr(handoff_api, "build_instacart", build)


def test_create_handoff_rejects_extra_fields(client: TestClient) -> None:
    response = client.post(
        "/grocery/handoffs", json={"job_id": str(uuid4()), "url": SUCCESS_URL}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_ownership_and_missing_job_are_static_404(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    foreign = add_job(factory, planning, revision, user_id=2)
    missing = client.post("/grocery/handoffs", json={"job_id": str(uuid4())})
    other = client.post("/grocery/handoffs", json={"job_id": foreign})
    assert missing.status_code == 404
    assert other.status_code == 404
    assert error_message(missing) == JOB_MISSING
    assert error_message(other) == JOB_MISSING


def test_snapshot_required_and_tampered_job_rebuilds(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    old = add_job(factory, planning, revision)
    with factory.begin() as session:
        job = session.get(Job, old)
        assert job is not None
        job.result = {key: planning[key] for key in PLANNING_KEYS}
    missing = client.post("/grocery/handoffs", json={"job_id": old})
    tampered_id = add_job(factory, planning, revision)
    with factory.begin() as session:
        job = session.get(Job, tampered_id)
        assert job is not None
        result = dict(cast(dict[str, object], job.result))
        plan = copy.deepcopy(cast(dict[str, object], result["plan"]))
        plan["accepted"] = not bool(plan["accepted"])
        result["plan"] = plan
        job.result = result
    tampered = client.post("/grocery/handoffs", json={"job_id": tampered_id})
    assert missing.status_code == 409
    assert tampered.status_code == 409
    assert error_message(missing) == REBUILD
    assert error_message(tampered) == REBUILD


def test_chat_result_snapshot_succeeds_once(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made = install_provider(monkeypatch, SUCCESS_URL)
    job_id = accepted_job(factory, extra=CHAT_EXTRA)
    first = client.post("/grocery/handoffs", json={"job_id": job_id})
    second = client.post("/grocery/handoffs", json={"job_id": job_id})
    body = view_body(first)
    cached = view_body(second)
    assert first.status_code == 200
    assert second.status_code == 200
    assert body["state"] == "succeeded"
    assert body["url"] == SUCCESS_URL
    assert body["retry_allowed"] is False
    assert cached == body
    assert len(made) == 1
    assert made[0].closed == 1
    assert len(made[0].payloads) == 1


def test_incomplete_rejected_and_all_pantry_are_denied(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs(plan_cap_cents=1)
    rejected_plan = genuine_planning(evidence_inputs=parsed, plan_cap_cents=1)
    rejected_rev = save_plan_evidence(factory, 1, rejected_plan, parsed)
    rejected_id = add_job(factory, rejected_plan, rejected_rev)
    pantry_id = accepted_job(
        factory,
        pantry_ingredients=BEAN_PANTRY,
    )
    incomplete = copy.deepcopy(genuine_planning())
    plan = cast(dict[str, object], incomplete["plan"])
    plan["total_cents"] = None
    plan["accepted"] = True
    incomplete["plan"] = plan
    snapshot = {
        "planning": incomplete,
        "budget_inputs": inputs().model_dump(mode="json"),
    }
    evidence_id = sha256(
        canonical_json({"user_id": 1, "snapshot": snapshot}).encode("utf-8")
    ).hexdigest()
    with factory.begin() as session:
        session.add(GroceryEvidence(id=evidence_id, user_id=1, snapshot=snapshot))
    incomplete_id = add_job(factory, incomplete, evidence_id)
    rejected = client.post("/grocery/handoffs", json={"job_id": rejected_id})
    pantry = client.post("/grocery/handoffs", json={"job_id": pantry_id})
    missing_total = client.post("/grocery/handoffs", json={"job_id": incomplete_id})
    assert rejected.status_code == 409
    assert pantry.status_code == 409
    assert missing_total.status_code == 409
    assert error_message(rejected) == DENIED
    assert error_message(pantry) == NO_ITEMS
    assert error_message(missing_total) == DENIED


def test_uncertainty_is_returned_without_replay(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made = install_provider(monkeypatch, InstacartUncertain())
    job_id = accepted_job(factory)
    first = client.post("/grocery/handoffs", json={"job_id": job_id})
    second = client.post("/grocery/handoffs", json={"job_id": job_id})
    body = view_body(first)
    assert first.status_code == 200
    assert body["state"] == "uncertain"
    assert body["url"] is None
    assert body["retry_allowed"] is True
    assert view_body(second)["state"] == "uncertain"
    assert len(made) == 1
    assert len(made[0].payloads) == 1
    assert made[0].closed == 1


def test_explicit_retry_fences_stale_and_cached_paths(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made = install_provider(monkeypatch, InstacartRejected())
    job_id = accepted_job(factory)
    failed = client.post("/grocery/handoffs", json={"job_id": job_id})
    handoff_id = view_body(failed)["id"]
    stale = client.post(
        f"/grocery/handoffs/{handoff_id}/retry", json={"expected_attempt": 9}
    )
    assert view_body(stale)["state"] == "failed"
    assert view_body(stale)["attempts"] == 1
    assert len(made) == 1
    assert len(made[0].payloads) == 1
    assert made[0].closed == 1
    retry_made = install_provider(monkeypatch, SUCCESS_URL)
    retried = client.post(
        f"/grocery/handoffs/{handoff_id}/retry", json={"expected_attempt": 1}
    )
    body = view_body(retried)
    assert body["state"] == "succeeded"
    assert body["url"] == SUCCESS_URL
    assert len(retry_made) == 1
    assert retry_made[0].closed == 1
    forbid_provider(monkeypatch)
    cached = client.post(
        f"/grocery/handoffs/{handoff_id}/retry", json={"expected_attempt": 2}
    )
    stale_success = client.post(
        f"/grocery/handoffs/{handoff_id}/retry", json={"expected_attempt": 1}
    )
    assert view_body(cached)["state"] == "succeeded"
    assert view_body(stale_success)["state"] == "succeeded"
    read = client.get(f"/grocery/handoffs/{handoff_id}")
    assert view_body(read)["url"] == SUCCESS_URL


def test_active_retry_does_not_construct_provider(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made = install_provider(monkeypatch, SUCCESS_URL)
    job_id = accepted_job(factory)
    created = client.post("/grocery/handoffs", json={"job_id": job_id})
    handoff_id = str(view_body(created)["id"])
    with factory.begin() as session:
        row = session.get(ShoppingHandoff, handoff_id)
        assert row is not None
        row.state = "dispatching"
        row.attempt_token = "attempt-1"
        row.attempts = 1
        row.started_at = datetime.now(UTC)
        row.url = None
        row.error_code = None
    forbid_provider(monkeypatch)
    active = client.post(
        f"/grocery/handoffs/{handoff_id}/retry", json={"expected_attempt": 1}
    )
    body = view_body(active)
    assert body["state"] == "dispatching"
    assert body["retry_allowed"] is False
    assert len(made) == 1


def test_config_unavailable_keeps_prepared_intent(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handoff_api, "load_provider_settings", lambda: GroceryProviderSettings()
    )
    job_id = accepted_job(factory)
    response = client.post("/grocery/handoffs", json={"job_id": job_id})
    assert response.status_code == 503
    assert error_message(response) == handoff_api._UNAVAILABLE
    with factory.begin() as session:
        rows = list(session.scalars(select(ShoppingHandoff)))
        assert len(rows) == 1
        assert rows[0].state == "prepared"
        handoff_id = rows[0].id
    forbid_provider(monkeypatch)
    shown = client.get(f"/grocery/handoffs/{handoff_id}")
    assert view_body(shown)["state"] == "prepared"
    assert view_body(shown)["url"] is None


def test_unsafe_url_is_blocked(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made = install_provider(monkeypatch, UNSAFE_URL)
    job_id = accepted_job(factory)
    response = client.post("/grocery/handoffs", json={"job_id": job_id})
    body = view_body(response)
    assert body["state"] == "uncertain"
    assert body["url"] is None
    assert UNSAFE_URL not in json.dumps(body)
    assert made[0].closed == 1


def test_get_missing_and_foreign_handoff_are_404(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    missing = client.get(f"/grocery/handoffs/{uuid4()}")
    other = prepare_handoff(factory, 2, shopping_payload())
    foreign = client.get(f"/grocery/handoffs/{other.id}")
    assert missing.status_code == 404
    assert foreign.status_code == 404
    assert error_message(missing) == handoff_api._HANDOFF_MISSING
    assert error_message(foreign) == handoff_api._HANDOFF_MISSING


def test_retry_requires_expected_attempt(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    response = client.post(f"/grocery/handoffs/{uuid4()}/retry", json={})
    zero = client.post(
        f"/grocery/handoffs/{uuid4()}/retry", json={"expected_attempt": 0}
    )
    assert response.status_code == 422
    assert zero.status_code == 422


def test_caught_http_errors_have_no_exception_context(
    factory: sessionmaker[Session], owners: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pantry_id = accepted_job(factory, pantry_ingredients=BEAN_PANTRY)
    caught: HandoffRouteError | None = None
    try:
        job_shopping_payload(factory, pantry_id)
    except HandoffRouteError as exc:
        caught = exc
    assert caught is not None
    assert caught.status == 409
    assert caught.detail == NO_ITEMS
    assert caught.__cause__ is None
    assert caught.__context__ is None
    create_error: HTTPException | None = None
    try:
        handoff_api.create_handoff(CreateHandoffBody(job_id=uuid4()), factory)
    except HTTPException as exc:
        create_error = exc
    assert create_error is not None
    assert create_error.status_code == 404
    assert create_error.__cause__ is None
    assert create_error.__context__ is None

    def boom(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise HandoffNotFound()

    provider = FakeProvider(SUCCESS_URL)
    monkeypatch.setattr(handoff_api, "build_instacart", lambda settings: provider)
    monkeypatch.setattr(handoff_api, "load_provider_settings", lambda: object())
    monkeypatch.setattr(handoff_api, "dispatch_handoff", boom)
    missing: HTTPException | None = None
    try:
        handoff_api._dispatch(factory, str(uuid4()))
    except HTTPException as exc:
        missing = exc
    assert missing is not None
    assert missing.status_code == 404
    assert missing.detail == handoff_api._HANDOFF_MISSING
    assert missing.__cause__ is None
    assert missing.__context__ is None
    assert provider.closed == 1


def test_config_error_is_static_503(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> object:
        raise ProviderConfigurationError()

    monkeypatch.setattr(handoff_api, "load_provider_settings", boom)
    error: HTTPException | None = None
    try:
        handoff_api._dispatch(factory, str(uuid4()))
    except HTTPException as exc:
        error = exc
    assert error is not None
    assert error.status_code == 503
    assert error.detail == handoff_api._UNAVAILABLE
    assert error.__cause__ is None
    assert error.__context__ is None
    assert ProviderConfigurationError.__name__ not in str(error.detail)
