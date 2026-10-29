"""Tests for plan revision storage and the POST /grocery/plans route."""

import importlib.util
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from conftest import UserSeeder, require_test_database_url
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import models
from app.api.grocery import DEMO_NOT_READY_MESSAGE
from app.db import Base
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.plan_models import PlanRevision

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0008_add_plan_revisions.py"
)
RECIPE_A, RECIPE_B, RECIPE_C, RECIPE_D = SUPPORTED_RECIPE_IDS[:4]
PANTRY = sorted(INGREDIENTS)[:2]


def snapshot(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": RECIPE_A, "servings": 2}],
        "pantry_ingredient_ids": PANTRY,
        "plan_cap_cents": 5000,
    }
    values.update(overrides)
    return values


@pytest.fixture(autouse=True)
def commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "commit", session.flush)


def test_post_plan_stores_one_revision(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    response = client.post("/grocery/plans", json=snapshot())
    rows = session.scalars(select(PlanRevision)).all()

    assert response.status_code == 201
    assert len(rows) == 1
    assert response.json() == {"plan_revision_id": str(rows[0].id)}
    assert rows[0].user_id == 1
    assert rows[0].snapshot == snapshot()


def test_post_plan_requires_the_demo_user(client: TestClient) -> None:
    response = client.post("/grocery/plans", json=snapshot())

    assert response.status_code == 503
    assert response.json()["error"]["message"] == DEMO_NOT_READY_MESSAGE


@pytest.mark.parametrize(
    "body",
    [
        snapshot(meals=[{"recipe_id": "no_such_recipe", "servings": 2}]),
        snapshot(
            meals=[
                {"recipe_id": RECIPE_A, "servings": 1},
                {"recipe_id": RECIPE_A, "servings": 2},
            ]
        ),
        snapshot(meals=[{"recipe_id": RECIPE_A, "servings": 0}]),
        snapshot(meals=[{"recipe_id": RECIPE_A, "servings": 9}]),
        snapshot(
            meals=[
                {"recipe_id": recipe_id, "servings": 1}
                for recipe_id in (RECIPE_A, RECIPE_B, RECIPE_C, RECIPE_D)
            ]
        ),
        snapshot(pantry_ingredient_ids=["no_such_ingredient"]),
        snapshot(pantry_ingredient_ids=[PANTRY[0], PANTRY[0]]),
        {**snapshot(), "extra": 1},
    ],
    ids=[
        "unknown-recipe",
        "duplicate-meal",
        "servings-0",
        "servings-9",
        "four-meals",
        "unknown-pantry",
        "duplicate-pantry",
        "extra-key",
    ],
)
def test_post_plan_rejects_invalid_snapshots(
    client: TestClient, session: Session, seed_user: UserSeeder, body: object
) -> None:
    seed_user()
    response = client.post("/grocery/plans", json=body)

    assert response.status_code == 422
    assert session.scalars(select(PlanRevision)).all() == []


def test_migration_0008_compiles_with_immutable_trigger() -> None:
    spec = importlib.util.spec_from_file_location("alembic_rev_0008", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0008"
    assert module.down_revision == "0007"
    buffer = StringIO()
    context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
    )
    with Operations.context(context):
        module.upgrade()
    sql = buffer.getvalue()
    assert "plan_revisions" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "RAISE EXCEPTION" in sql
    with pytest.raises(RuntimeError, match="Forward-only"):
        module.downgrade()


@pytest.fixture()
def postgres_engine() -> Iterator[Engine]:
    url = require_test_database_url()
    schema = f"plans_{uuid4().hex}"
    admin = create_engine(url)
    if admin.dialect.name != "postgresql":
        admin.dispose()
        pytest.fail("The immutability test requires PostgreSQL.")
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_plan_revision_rows_are_immutable_on_postgresql(
    postgres_engine: Engine,
) -> None:
    spec = importlib.util.spec_from_file_location("alembic_rev_0008", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    revision_id = uuid4()
    with postgres_engine.begin() as connection:
        Base.metadata.create_all(
            connection,
            tables=[models.User.__table__, PlanRevision.__table__],
        )
        connection.execute(text(module.IMMUTABLE_FUNCTION_SQL))
        connection.execute(text(module.IMMUTABLE_TRIGGER_SQL))
        connection.execute(text("INSERT INTO users (id, display_name) VALUES (1, 'u')"))
        connection.execute(
            text(
                "INSERT INTO plan_revisions (id, user_id, snapshot) VALUES (:i, 1, '{}')"
            ),
            {"i": revision_id},
        )
    for statement in (
        "UPDATE plan_revisions SET user_id = 1",
        "DELETE FROM plan_revisions",
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            with postgres_engine.begin() as connection:
                connection.execute(text(statement))
    with postgres_engine.connect() as connection:
        stored = connection.execute(text("SELECT id FROM plan_revisions")).scalar_one()
    assert UUID(str(stored)) == revision_id
