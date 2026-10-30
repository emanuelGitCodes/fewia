"""Tests for plan proposal validation, storage, and the proposal routes."""

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
from app.db import Base
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.plan_proposal import (
    INVALID_PROPOSAL_MESSAGE,
    ProposalInvalid,
    apply_operations,
    create_proposal,
    parse_operations,
)
from app.domain.plan_revision import PlanSnapshot
from app.plan_models import PlanProposal, PlanRevision

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0009_add_plan_proposals.py"
)
RECIPE_A, RECIPE_B, RECIPE_C, RECIPE_D = SUPPORTED_RECIPE_IDS[:4]
PANTRY = sorted(INGREDIENTS)[:2]
OTHER_INGREDIENT = sorted(INGREDIENTS)[2]


@pytest.fixture(autouse=True)
def commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "commit", session.flush)


def base_snapshot(meals: int = 1) -> PlanSnapshot:
    return PlanSnapshot.model_validate(
        {
            "meals": [
                {"recipe_id": recipe_id, "servings": 2}
                for recipe_id in (RECIPE_A, RECIPE_B, RECIPE_C)[:meals]
            ],
            "pantry_ingredient_ids": PANTRY,
            "plan_cap_cents": 5000,
        }
    )


def seed_revision(session: Session, snapshot: PlanSnapshot, user_id: int = 1) -> UUID:
    revision_id = uuid4()
    session.add(
        PlanRevision(
            id=revision_id,
            user_id=user_id,
            snapshot=snapshot.model_dump(mode="json"),
        )
    )
    session.flush()
    return revision_id


def apply(snapshot: PlanSnapshot, *ops: dict[str, object]) -> PlanSnapshot:
    return apply_operations(snapshot, parse_operations(list(ops)))


def test_add_remove_and_set_servings() -> None:
    added = apply(base_snapshot(), {"op": "add", "recipe_id": RECIPE_B, "servings": 3})
    assert [(m.recipe_id, m.servings) for m in added.meals] == [
        (RECIPE_A, 2),
        (RECIPE_B, 3),
    ]
    changed = apply(added, {"op": "set_servings", "recipe_id": RECIPE_A, "servings": 5})
    assert changed.meals[0].servings == 5
    removed = apply(changed, {"op": "remove", "recipe_id": RECIPE_A})
    assert [m.recipe_id for m in removed.meals] == [RECIPE_B]


def test_set_pantry_adds_and_removes() -> None:
    added = apply(
        base_snapshot(),
        {"op": "set_pantry", "ingredient_id": OTHER_INGREDIENT, "owned": True},
    )
    assert OTHER_INGREDIENT in added.pantry_ingredient_ids
    removed = apply(
        added, {"op": "set_pantry", "ingredient_id": PANTRY[0], "owned": False}
    )
    assert PANTRY[0] not in removed.pantry_ingredient_ids
    assert removed.plan_cap_cents == 5000


def test_apply_does_not_mutate_the_input() -> None:
    snapshot = base_snapshot()
    apply(snapshot, {"op": "set_servings", "recipe_id": RECIPE_A, "servings": 7})
    assert snapshot.meals[0].servings == 2


@pytest.mark.parametrize(
    ("meals", "op"),
    [
        (3, {"op": "add", "recipe_id": RECIPE_D, "servings": 1}),
        (1, {"op": "add", "recipe_id": RECIPE_A, "servings": 1}),
        (1, {"op": "add", "recipe_id": RECIPE_B, "servings": 9}),
        (1, {"op": "remove", "recipe_id": RECIPE_B}),
        (1, {"op": "set_servings", "recipe_id": RECIPE_B, "servings": 2}),
        (1, {"op": "set_servings", "recipe_id": RECIPE_A, "servings": 9}),
        (1, {"op": "set_pantry", "ingredient_id": "nope", "owned": True}),
    ],
    ids=[
        "four-meals",
        "repeated-recipe",
        "servings-9",
        "remove-missing",
        "set-missing",
        "set-servings-9",
        "unknown-pantry",
    ],
)
def test_invalid_results_are_rejected(meals: int, op: dict[str, object]) -> None:
    with pytest.raises(ProposalInvalid, match=INVALID_PROPOSAL_MESSAGE):
        apply(base_snapshot(meals), op)


@pytest.mark.parametrize(
    "raw",
    [
        [],
        [{"op": "remove", "recipe_id": RECIPE_A}] * 7,
        [{"op": "substitute", "recipe_id": RECIPE_A}],
        [{"op": "remove", "recipe_id": RECIPE_A, "extra": 1}],
        [{"op": "add", "recipe_id": RECIPE_A, "servings": True}],
        "remove",
    ],
)
def test_malformed_operations_are_rejected(raw: object) -> None:
    with pytest.raises(ProposalInvalid):
        parse_operations(raw)


def test_create_proposal_stores_validated_operations(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    base_id = seed_revision(session, base_snapshot())
    ops = [{"op": "add", "recipe_id": RECIPE_B, "servings": 3}]

    proposal_id = create_proposal(session, 1, base_id, ops)

    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    assert row.status == "pending"
    assert row.operations == ops
    assert row.applied_plan_revision_id is None


def test_create_proposal_rejects_invalid_and_foreign_bases(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    base_id = seed_revision(session, base_snapshot())
    with pytest.raises(ProposalInvalid):
        create_proposal(session, 1, base_id, [{"op": "remove", "recipe_id": RECIPE_B}])
    with pytest.raises(ProposalInvalid):
        create_proposal(session, 2, base_id, [{"op": "remove", "recipe_id": RECIPE_A}])
    with pytest.raises(ProposalInvalid):
        create_proposal(session, 1, uuid4(), [{"op": "remove", "recipe_id": RECIPE_A}])
    assert session.scalars(select(PlanProposal)).all() == []


def make_proposal(session: Session) -> UUID:
    base_id = seed_revision(session, base_snapshot())
    return create_proposal(
        session, 1, base_id, [{"op": "add", "recipe_id": RECIPE_B, "servings": 3}]
    )


def revision_count(session: Session) -> int:
    return len(session.scalars(select(PlanRevision)).all())


def test_get_returns_preview(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    proposal_id = make_proposal(session)

    response = client.get(f"/grocery/proposals/{proposal_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(proposal_id)
    assert body["status"] == "pending"
    assert body["applied_plan_revision_id"] is None
    assert body["operations"] == [{"op": "add", "recipe_id": RECIPE_B, "servings": 3}]
    assert [m["recipe_id"] for m in body["preview"]["meals"]] == [RECIPE_A, RECIPE_B]


def test_missing_and_foreign_proposals_are_404(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    session.add(models.User(id=2, display_name="other"))
    session.flush()
    base_id = seed_revision(session, base_snapshot(), user_id=2)
    foreign_id = create_proposal(
        session, 2, base_id, [{"op": "remove", "recipe_id": RECIPE_A}]
    )

    for path in (
        f"/grocery/proposals/{foreign_id}",
        f"/grocery/proposals/{uuid4()}",
    ):
        assert client.get(path).status_code == 404
    for action in ("apply", "discard"):
        response = client.post(f"/grocery/proposals/{foreign_id}/{action}")
        assert response.status_code == 404


def test_apply_creates_one_revision_and_is_idempotent(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    before = revision_count(session)

    first = client.post(f"/grocery/proposals/{proposal_id}/apply")
    second = client.post(f"/grocery/proposals/{proposal_id}/apply")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert revision_count(session) == before + 1
    revision = session.get(PlanRevision, UUID(first.json()["plan_revision_id"]))
    assert revision is not None
    assert [m["recipe_id"] for m in revision.snapshot["meals"]] == [  # type: ignore[index, union-attr]
        RECIPE_A,
        RECIPE_B,
    ]
    detail = client.get(f"/grocery/proposals/{proposal_id}").json()
    assert detail["status"] == "applied"
    assert detail["applied_plan_revision_id"] == first.json()["plan_revision_id"]


def test_discard_is_idempotent_and_blocks_apply(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    before = revision_count(session)

    assert client.post(f"/grocery/proposals/{proposal_id}/discard").status_code == 200
    assert client.post(f"/grocery/proposals/{proposal_id}/discard").status_code == 200
    response = client.post(f"/grocery/proposals/{proposal_id}/apply")

    assert response.status_code == 409
    assert revision_count(session) == before
    assert client.get(f"/grocery/proposals/{proposal_id}").json()["status"] == (
        "discarded"
    )


def test_discarding_an_applied_proposal_is_409(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    client.post(f"/grocery/proposals/{proposal_id}/apply")

    response = client.post(f"/grocery/proposals/{proposal_id}/discard")

    assert response.status_code == 409
    assert client.get(f"/grocery/proposals/{proposal_id}").json()["status"] == (
        "applied"
    )


def test_migration_0009_compiles_and_downgrades() -> None:
    spec = importlib.util.spec_from_file_location("alembic_rev_0009", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0009"
    assert module.down_revision == "0008"
    for direction, expected in (("upgrade", "CREATE TABLE"), ("downgrade", "DROP")):
        buffer = StringIO()
        context = MigrationContext.configure(
            dialect=postgresql.dialect(),
            opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
        )
        with Operations.context(context):
            getattr(module, direction)()
        sql = buffer.getvalue()
        assert "plan_proposals" in sql
        assert expected in sql


@pytest.fixture()
def postgres_engine() -> Iterator[Engine]:
    url = require_test_database_url()
    schema = f"proposals_{uuid4().hex}"
    admin = create_engine(url)
    if admin.dialect.name != "postgresql":
        admin.dispose()
        pytest.fail("The constraint test requires PostgreSQL.")
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


def test_status_checks_on_postgresql(postgres_engine: Engine) -> None:
    revision_id = uuid4()
    with postgres_engine.begin() as connection:
        Base.metadata.create_all(
            connection,
            tables=[
                models.User.__table__,
                PlanRevision.__table__,
                PlanProposal.__table__,
            ],
        )
        connection.execute(text("INSERT INTO users (id, display_name) VALUES (1, 'u')"))
        connection.execute(
            text(
                "INSERT INTO plan_revisions (id, user_id, snapshot) "
                "VALUES (:i, 1, '{}')"
            ),
            {"i": revision_id},
        )
    insert = (
        "INSERT INTO plan_proposals "
        "(id, user_id, base_plan_revision_id, operations, status, "
        "applied_plan_revision_id) "
        "VALUES (:p, 1, :r, '[]', :s, :a)"
    )
    bad = [("bogus", None), ("applied", None), ("pending", revision_id)]
    for status, applied in bad:
        with pytest.raises(DBAPIError):
            with postgres_engine.begin() as connection:
                connection.execute(
                    text(insert),
                    {"p": uuid4(), "r": revision_id, "s": status, "a": applied},
                )
    with postgres_engine.begin() as connection:
        for status, applied in (
            ("pending", None),
            ("discarded", None),
            ("applied", revision_id),
        ):
            connection.execute(
                text(insert),
                {"p": uuid4(), "r": revision_id, "s": status, "a": applied},
            )
