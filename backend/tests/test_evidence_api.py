"""Tests for the grocery evidence HTTP route."""

import copy
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Connection, Engine, create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_evidence_contract import genuine_planning, inputs

from app import models
from app.api.evidence import (
    NOT_FOUND_MESSAGE,
    get_session_factory,
    router,
)
from app.db import Base
from app.evidence_models import GroceryEvidence
from app.services.evidence_contract import normalize_snapshot
from app.services.evidence_store import load_evidence, save_plan_evidence

JOB_FIELDS = (
    "payload",
    "lease_token",
    "lease_expires_at",
    "request_key",
    "user_id",
    "attempts",
    "kind",
    "status",
    "result",
    "error_code",
    "job_id",
    "created_at",
)


@pytest.fixture()
def evidence_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "evidence-api.db"
    test_engine = create_engine(
        f"sqlite:///{database_path}",
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

    tables = [models.User.__table__, GroceryEvidence.__table__]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def factory(evidence_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=evidence_engine, expire_on_commit=False)


@pytest.fixture()
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_factory] = lambda: factory
    with TestClient(app) as test_client:
        yield test_client


def seed_users(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))


def count_rows(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(GroceryEvidence)) or 0
        )


def save_owned(factory: sessionmaker[Session]) -> tuple[str, dict[str, object]]:
    parsed = inputs()
    planning = genuine_planning(user_id=1, evidence_inputs=parsed)
    revision_id = save_plan_evidence(factory, 1, planning, parsed)
    snapshot = normalize_snapshot(1, planning, parsed)
    return revision_id, snapshot


def assert_static_404(response: Response) -> None:
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_MESSAGE}


def test_owned_snapshot_matches_store_and_does_not_mutate(
    client: TestClient, factory: sessionmaker[Session]
) -> None:
    seed_users(factory)
    revision_id, snapshot = save_owned(factory)
    rows = count_rows(factory)
    response = client.get(f"/grocery/evidence/{revision_id}")
    body = response.json()
    original = copy.deepcopy(body)
    body["snapshot"]["tamper"] = True
    stored = load_evidence(factory, 1, revision_id)
    second = client.get(f"/grocery/evidence/{revision_id}")

    assert response.status_code == 200
    assert original == {"revision_id": revision_id, "snapshot": snapshot}
    assert set(original) == {"revision_id", "snapshot"}
    assert set(original["snapshot"]) == {"planning", "budget_inputs"}
    assert stored == snapshot
    assert second.json() == original
    assert count_rows(factory) == rows


def test_foreign_missing_and_malformed_use_static_404(
    client: TestClient, factory: sessionmaker[Session]
) -> None:
    seed_users(factory)
    parsed = inputs()
    foreign_planning = genuine_planning(user_id=2, evidence_inputs=parsed)
    foreign_id = save_plan_evidence(factory, 2, foreign_planning, parsed)
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

    assert_static_404(foreign)
    assert_static_404(missing)
    assert "snapshot" not in foreign.json()
    assert "planning" not in foreign.json()
    for value in malformed:
        assert_static_404(client.get(f"/grocery/evidence/{value}"))


def test_response_omits_job_fields_and_does_not_write(
    client: TestClient, factory: sessionmaker[Session]
) -> None:
    seed_users(factory)
    revision_id, snapshot = save_owned(factory)
    rows = count_rows(factory)
    response = client.get(f"/grocery/evidence/{revision_id}")
    body = response.json()

    assert response.status_code == 200
    assert body["revision_id"] == revision_id
    assert body["snapshot"] == snapshot
    for field in JOB_FIELDS:
        assert field not in body
        assert field not in body["snapshot"]
    assert count_rows(factory) == rows
    assert load_evidence(factory, 1, revision_id) == snapshot
