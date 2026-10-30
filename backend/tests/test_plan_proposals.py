"""Tests for plan proposal validation, storage, and the proposal routes."""

import importlib.util
from collections.abc import Iterator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from conftest import UserSeeder, require_test_database_url
from fastapi.testclient import TestClient
from sqlalchemy import (
    Connection,
    Engine,
    ScalarResult,
    Select,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import models
from app.api import proposals as proposals_api
from app.db import Base
from app.demo import DEMO_USER_ID
from app.domain import plan_revision
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
        (1, {"op": "set_pantry", "ingredient_id": "nope", "owned": False}),
        (1, {"op": "remove", "recipe_id": RECIPE_A}),
    ],
    ids=[
        "four-meals",
        "repeated-recipe",
        "servings-9",
        "remove-missing",
        "set-missing",
        "set-servings-9",
        "unknown-pantry",
        "unknown-pantry-not-owned",
        "zero-meals",
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
        [{"op": "remove", "recipe_id": ""}],
        [{"op": "remove", "recipe_id": "r" * 65}],
        [{"op": "set_pantry", "ingredient_id": "i" * 65, "owned": False}],
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
    base_id = seed_revision(session, base_snapshot(2), user_id=2)
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


@pytest.mark.parametrize("first", ["get", "apply"])
def test_stale_pending_proposal_is_409_and_becomes_discarded(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    before = revision_count(session)
    monkeypatch.setattr(
        plan_revision,
        "SUPPORTED_RECIPE_IDS",
        tuple(item for item in SUPPORTED_RECIPE_IDS if item != RECIPE_A),
    )
    path = f"/grocery/proposals/{proposal_id}"

    response = client.get(path) if first == "get" else client.post(f"{path}/apply")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == proposals_api.PROPOSAL_STALE_MESSAGE
    assert RECIPE_A not in response.text
    assert revision_count(session) == before
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    assert row.status == "discarded"

    again = client.get(path)

    assert again.status_code == 200
    assert again.json()["status"] == "discarded"
    assert again.json()["preview"] is None
    assert client.post(f"{path}/apply").status_code == 409
    assert revision_count(session) == before


def test_stale_discard_leaves_an_applied_proposal_alone(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    assert client.post(f"/grocery/proposals/{proposal_id}/apply").status_code == 200
    monkeypatch.setattr(
        plan_revision,
        "SUPPORTED_RECIPE_IDS",
        tuple(item for item in SUPPORTED_RECIPE_IDS if item != RECIPE_A),
    )

    client.get(f"/grocery/proposals/{proposal_id}")

    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    session.refresh(row)
    assert row.status == "applied"


@pytest.mark.parametrize("action", ["apply", "discard"])
def test_apply_and_discard_change_updated_at(
    client: TestClient, session: Session, seed_user: UserSeeder, action: str
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    old = datetime(2000, 1, 1, tzinfo=UTC)
    row.updated_at = old
    session.flush()

    assert client.post(f"/grocery/proposals/{proposal_id}/{action}").status_code == 200

    session.refresh(row)
    assert row.updated_at.replace(tzinfo=UTC) > old


@pytest.mark.parametrize(
    ("method", "suffix", "locks"),
    [("get", "", False), ("post", "/apply", True), ("post", "/discard", True)],
)
def test_proposal_routes_lock_the_row_for_changes(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    suffix: str,
    locks: bool,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    flags: list[bool] = []
    statements: list[str] = []
    real_load = proposals_api._load
    real_scalars = session.scalars

    def record_load(
        db: Session, requested: UUID, *, lock: bool = False
    ) -> PlanProposal:
        flags.append(lock)
        return real_load(db, requested, lock=lock)

    def record_scalars(
        statement: Select[Any], *args: object, **kwargs: object
    ) -> ScalarResult[Any]:
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return real_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(proposals_api, "_load", record_load)
    monkeypatch.setattr(session, "scalars", record_scalars)

    response = getattr(client, method)(f"/grocery/proposals/{proposal_id}{suffix}")

    assert response.status_code == 200
    assert flags == [locks]
    selects = [sql for sql in statements if "FROM plan_proposals" in sql]
    assert len(selects) == 1
    assert ("FOR UPDATE" in selects[0]) is locks


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


def test_migration_0010_compiles_and_downgrades() -> None:
    path = MIGRATION_PATH.with_name("0010_add_kroger_customer_tokens.py")
    spec = importlib.util.spec_from_file_location("alembic_rev_0010", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0010"
    assert module.down_revision == "0009"
    for direction, expected in (("upgrade", "CREATE TABLE"), ("downgrade", "DROP")):
        buffer = StringIO()
        context = MigrationContext.configure(
            dialect=postgresql.dialect(),
            opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
        )
        with Operations.context(context):
            getattr(module, direction)()
        sql = buffer.getvalue()
        assert "kroger_customer_tokens" in sql
        assert expected in sql
        if direction == "upgrade":
            assert "BYTEA" in sql
            assert "REFERENCES users (id)" in sql


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


@pytest.fixture()
def migrated_rows() -> Iterator[tuple[Connection, int, UUID]]:
    """Give a connection to the migrated database inside a rolled-back transaction."""
    engine = create_engine(require_test_database_url())
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("The constraint test requires PostgreSQL.")
    connection = engine.connect()
    transaction = connection.begin()
    try:
        registered = connection.execute(
            text("SELECT to_regclass('plan_proposals')")
        ).scalar_one()
        if registered is None:
            pytest.fail("Run `uv run alembic upgrade head` on the test database.")
        user_id = -(uuid4().int % 2_000_000_000 + 1)
        revision_id = uuid4()
        connection.execute(
            text("INSERT INTO users (id, display_name) VALUES (:u, 'fixture')"),
            {"u": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO plan_revisions (id, user_id, snapshot) "
                "VALUES (:i, :u, '{}')"
            ),
            {"i": revision_id, "u": user_id},
        )
        yield connection, user_id, revision_id
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


INSERT_PROPOSAL = (
    "INSERT INTO plan_proposals "
    "(id, user_id, base_plan_revision_id, operations, status, "
    "applied_plan_revision_id) "
    "VALUES (:p, :u, :r, '[]', :s, :a)"
)


def test_migrated_table_rejects_bad_status_combinations(
    migrated_rows: tuple[Connection, int, UUID],
) -> None:
    connection, user_id, revision_id = migrated_rows
    bad = [
        ("bogus", None, revision_id),
        ("applied", None, revision_id),
        ("pending", revision_id, revision_id),
        ("discarded", revision_id, revision_id),
        ("pending", None, uuid4()),
        ("applied", uuid4(), revision_id),
    ]
    for status, applied, base in bad:
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    text(INSERT_PROPOSAL),
                    {
                        "p": uuid4(),
                        "u": user_id,
                        "r": base,
                        "s": status,
                        "a": applied,
                    },
                )
    for status, applied in (
        ("pending", None),
        ("discarded", None),
        ("applied", revision_id),
    ):
        with connection.begin_nested():
            connection.execute(
                text(INSERT_PROPOSAL),
                {
                    "p": uuid4(),
                    "u": user_id,
                    "r": revision_id,
                    "s": status,
                    "a": applied,
                },
            )


def test_migrated_table_defaults_status_to_pending(
    migrated_rows: tuple[Connection, int, UUID],
) -> None:
    connection, user_id, revision_id = migrated_rows
    row = connection.execute(
        text(
            "INSERT INTO plan_proposals "
            "(id, user_id, base_plan_revision_id, operations) "
            "VALUES (:p, :u, :r, '[]') "
            "RETURNING status, applied_plan_revision_id, "
            "created_at IS NOT NULL, updated_at IS NOT NULL"
        ),
        {"p": uuid4(), "u": user_id, "r": revision_id},
    ).one()
    assert tuple(row) == ("pending", None, True, True)


def test_a_locked_proposal_row_blocks_apply_on_postgresql(
    postgres_engine: Engine,
) -> None:
    ops = [{"op": "add", "recipe_id": RECIPE_B, "servings": 3}]
    with Session(postgres_engine) as setup:
        Base.metadata.create_all(
            setup.connection(),
            tables=[
                models.User.__table__,
                PlanRevision.__table__,
                PlanProposal.__table__,
            ],
        )
        setup.add(models.User(id=DEMO_USER_ID, display_name="demo"))
        setup.flush()
        base_id = seed_revision(setup, base_snapshot(), user_id=DEMO_USER_ID)
        proposal_id = create_proposal(setup, DEMO_USER_ID, base_id, ops)
        setup.commit()

    with Session(postgres_engine) as holder, Session(postgres_engine) as waiter:
        holder.scalars(
            select(PlanProposal).where(PlanProposal.id == proposal_id).with_for_update()
        ).one()
        waiter.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            proposals_api.apply_proposal(proposal_id, waiter)
        waiter.rollback()
        holder.rollback()

        with Session(postgres_engine) as check:
            count = check.scalars(select(func.count()).select_from(PlanRevision))
            assert count.one() == 1
            pending = check.get(PlanProposal, proposal_id)
            assert pending is not None
            assert pending.status == "pending"

        result = proposals_api.apply_proposal(proposal_id, waiter)

    with Session(postgres_engine) as check:
        count = check.scalars(select(func.count()).select_from(PlanRevision))
        assert count.one() == 2
        applied = check.get(PlanProposal, proposal_id)
        assert applied is not None
        assert str(applied.applied_plan_revision_id) == result["plan_revision_id"]
