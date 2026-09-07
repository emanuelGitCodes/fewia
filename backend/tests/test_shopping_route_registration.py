"""Tests for evidence and handoff registration on the main FastAPI app."""

import json
import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Connection, Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.agent.planning_tool import execute_plan
from app.api import evidence as evidence_api
from app.api import handoff as handoff_api
from app.api.handoff_models import PLANNING_KEYS
from app.db import Base
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.evidence_models import GroceryEvidence
from app.handoff_models import ShoppingHandoff
from app.job_models import Job
from app.main import app
from app.provider_settings import GroceryProviderSettings, ProviderConfigurationError
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import save_plan_evidence
from app.services.handoff_intents import prepare_handoff
from app.services.plan_job import SpendingInput

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
PERIOD = date(2026, 9, 1)
SECRET = "sk-test-not-for-models"
FOREIGN_PAYLOAD: dict[str, object] = {
    "title": "FEWIA grocery plan",
    "link_type": "shopping_list",
    "expires_in": 7,
    "line_items": [
        {
            "name": "black beans",
            "line_item_measurements": [{"quantity": 240, "unit": "g"}],
        }
    ],
}


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def shopping_engine(tmp_path: Path) -> Iterator[Engine]:
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'shopping-routes.db'}",
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
def factory(shopping_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=shopping_engine, expire_on_commit=False)


@pytest.fixture()
def owners(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))


@pytest.fixture()
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app.dependency_overrides[evidence_api.get_session_factory] = lambda: factory
    app.dependency_overrides[handoff_api.get_session_factory] = lambda: factory
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(evidence_api.get_session_factory, None)
        app.dependency_overrides.pop(handoff_api.get_session_factory, None)


def evidence_inputs() -> EvidenceInputs:
    return EvidenceInputs(
        monthly_limit_cents=10_000,
        spending=SpendingInput(
            period=PERIOD,
            posted_cents=2_500,
            pending_cents=400,
            refreshed_at=NOW - timedelta(hours=1),
        ),
        spending_source="fixture",
        calculated_at=NOW,
        plan_cap_cents=None,
    )


def accepted_planning(user_id: int = 1) -> tuple[dict[str, object], EvidenceInputs]:
    parsed = evidence_inputs()
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        SpendingSnapshot(
            parsed.spending.period,
            parsed.spending.posted_cents,
            parsed.spending.pending_cents,
            parsed.spending.refreshed_at,
        ),
        now=parsed.calculated_at,
        plan_cap_cents=parsed.plan_cap_cents,
    )
    planning = execute_plan(
        {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": PERIOD,
        },
        budget,
        parsed.spending.period,
        user_id=user_id,
        spending_source=parsed.spending_source,
    )
    plan = planning["plan"]
    assert isinstance(plan, dict)
    assert plan["accepted"] is True
    return planning, parsed


def save_owned_evidence(factory: sessionmaker[Session], user_id: int = 1) -> str:
    planning, parsed = accepted_planning(user_id=user_id)
    return save_plan_evidence(factory, user_id, planning, parsed)


def save_owned_job(factory: sessionmaker[Session]) -> str:
    planning, parsed = accepted_planning()
    revision = save_plan_evidence(factory, 1, planning, parsed)
    result: dict[str, object] = {key: planning[key] for key in PLANNING_KEYS}
    result["evidence_revision_id"] = revision
    job = Job(
        user_id=1,
        kind="agent",
        request_key=str(uuid4()),
        status="succeeded",
        payload={"marker": SECRET},
        result=result,
    )
    with factory.begin() as session:
        session.add(job)
        session.flush()
        return job.id


def assert_secret_absent(response: Response) -> None:
    rendered = json.dumps(response.json())
    assert SECRET not in rendered
    assert "attempt_token" not in rendered


def assert_not_found(response: Response, message: str) -> None:
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": message},
    }
    assert_secret_absent(response)


def forbid_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def settings() -> NoReturn:
        raise AssertionError("load_provider_settings MUST NOT run")

    def build(value: object) -> NoReturn:
        del value
        raise AssertionError("build_instacart MUST NOT run")

    monkeypatch.setattr(handoff_api, "load_provider_settings", settings)
    monkeypatch.setattr(handoff_api, "build_instacart", build)


def test_existing_and_shopping_get_paths_are_registered() -> None:
    operations = frozenset(
        {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
    )
    inventory = app.openapi()["paths"]
    routes = {
        (path, method.upper())
        for path, spec in inventory.items()
        for method in spec
        if method in operations
    }
    assert ("/healthz", "GET") in routes
    assert ("/grocery/jobs", "POST") in routes
    assert ("/grocery/chat/jobs", "POST") in routes
    assert ("/predict/activity", "GET") in routes
    assert ("/grocery/evidence/{revision_id}", "GET") in routes
    assert ("/grocery/handoffs/{handoff_id}", "GET") in routes
    assert ("/grocery/handoffs", "POST") in routes
    assert not any(path.startswith("/grocery/sync") for path, _method in routes)


def test_evidence_get_path_returns_saved_snapshot(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    revision_id = save_owned_evidence(factory)
    response = client.get(f"/grocery/evidence/{revision_id}")
    body = response.json()
    assert response.status_code == 200
    assert body["revision_id"] == revision_id
    assert set(body) == {"revision_id", "snapshot"}
    assert set(body["snapshot"]) == {"planning", "budget_inputs"}
    assert_secret_absent(response)


def test_evidence_missing_foreign_malformed_use_main_error_envelope(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    foreign_id = save_owned_evidence(factory, user_id=2)
    missing_id = "ab" * 32
    malformed = (
        "AB" * 32,
        "0" * 63,
        "0" * 65,
        "g" + "0" * 63,
        "not-a-revision",
    )
    foreign = client.get(f"/grocery/evidence/{foreign_id}")
    missing = client.get(f"/grocery/evidence/{missing_id}")
    assert_not_found(foreign, evidence_api.NOT_FOUND_MESSAGE)
    assert_not_found(missing, evidence_api.NOT_FOUND_MESSAGE)
    for value in malformed:
        assert_not_found(
            client.get(f"/grocery/evidence/{value}"),
            evidence_api.NOT_FOUND_MESSAGE,
        )


def test_handoff_missing_foreign_malformed_use_main_error_envelope(
    client: TestClient, factory: sessionmaker[Session], owners: None
) -> None:
    missing = client.get(f"/grocery/handoffs/{uuid4()}")
    other = prepare_handoff(factory, 2, FOREIGN_PAYLOAD)
    foreign = client.get(f"/grocery/handoffs/{other.id}")
    malformed = client.get("/grocery/handoffs/not-a-uuid")
    assert_not_found(missing, handoff_api._HANDOFF_MISSING)
    assert_not_found(foreign, handoff_api._HANDOFF_MISSING)
    assert malformed.status_code == 422
    body = malformed.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "The request has invalid parameters."
    assert_secret_absent(malformed)


def test_handoff_create_unconfigured_returns_503_and_cached_get_skips_providers(
    client: TestClient,
    factory: sessionmaker[Session],
    owners: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handoff_api, "load_provider_settings", lambda: GroceryProviderSettings()
    )
    job_id = save_owned_job(factory)
    response = client.post("/grocery/handoffs", json={"job_id": job_id})
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": handoff_api._UNAVAILABLE,
        }
    }
    assert_secret_absent(response)
    with factory.begin() as session:
        rows = list(session.scalars(select(ShoppingHandoff)))
        assert len(rows) == 1
        assert rows[0].state == "prepared"
        handoff_id = rows[0].id
    forbid_provider(monkeypatch)
    shown = client.get(f"/grocery/handoffs/{handoff_id}")
    body = shown.json()
    assert shown.status_code == 200
    assert body["state"] == "prepared"
    assert body["url"] is None
    assert_secret_absent(shown)
    rendered = json.dumps(response.json())
    assert ProviderConfigurationError.__name__ not in rendered
    assert SECRET not in rendered
