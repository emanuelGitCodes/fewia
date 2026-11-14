"""Tests for plan proposal validation, storage, and the proposal routes."""

import importlib.util
import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from conftest import UserSeeder, require_test_database_url
from fastapi import HTTPException
from fastapi.responses import JSONResponse
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
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.domain.plan_proposal import (
    INVALID_PROPOSAL_MESSAGE,
    ApplyConstraints,
    ProposalInvalid,
    apply_operations,
    create_proposal,
    parse_operations,
)
from app.domain.plan_revision import PlanSnapshot
from app.plan_models import PlanProposal, PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.security_models import QuotaCounter
from app.services import security_admission
from app.services.grocery_planner import plan_groceries
from app.services.plan_job import SpendingInput

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0009_add_plan_proposals.py"
)
RECIPE_A, RECIPE_B, RECIPE_C, RECIPE_D = SUPPORTED_RECIPE_IDS[:4]
PANTRY = sorted(INGREDIENTS)[:2]
OTHER_INGREDIENT = sorted(INGREDIENTS)[2]
CONSTRAINTS = ApplyConstraints(
    monthly_limit_cents=100_000,
    plan_cap_cents=None,
    diet="omnivore",
    ingredient_exclusions=[],
)


@pytest.fixture(autouse=True)
def mutation_admission(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[Session, int, security_admission.Action]]:
    calls: list[tuple[Session, int, security_admission.Action]] = []
    real_reserve = security_admission.reserve_action

    def reserve(db: Session, user_id: int, action: security_admission.Action) -> None:
        if db.get_bind().dialect.name == "sqlite":
            status = db.scalar(
                select(models.User.status).where(models.User.id == user_id)
            )
            if status != "active":
                raise security_admission.OwnerUnavailableError()
        else:
            real_reserve(db, user_id, action)
        calls.append((db, user_id, action))

    monkeypatch.setattr(security_admission, "reserve_action", reserve)
    return calls


@pytest.fixture(autouse=True)
def commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "commit", session.flush)
    monkeypatch.setattr(
        proposals_api,
        "get_provider_settings",
        lambda: GroceryProviderSettings.model_construct(spending_source="manual"),
    )


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

    proposal_id = create_proposal(session, 1, base_id, ops, constraints=CONSTRAINTS)

    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    assert row.status == "pending"
    assert row.operations == ops
    assert row.apply_constraints == CONSTRAINTS.model_dump(mode="json")
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
        session,
        1,
        base_id,
        [{"op": "add", "recipe_id": RECIPE_B, "servings": 3}],
        constraints=CONSTRAINTS,
    )


def revision_count(session: Session) -> int:
    return len(session.scalars(select(PlanRevision)).all())


def pantry_proposal(
    session: Session,
    *,
    constraints: ApplyConstraints = CONSTRAINTS,
    cap: int | None = 1702,
    owned: bool = False,
) -> tuple[UUID, UUID]:
    snapshot = PlanSnapshot.model_validate(
        {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "pantry_ingredient_ids": ["olive_oil"],
            "plan_cap_cents": cap,
        }
    )
    base_id = seed_revision(session, snapshot)
    proposal_id = create_proposal(
        session,
        DEMO_USER_ID,
        base_id,
        [{"op": "set_pantry", "ingredient_id": "olive_oil", "owned": owned}],
        constraints=constraints,
    )
    return base_id, proposal_id


@pytest.mark.parametrize("request_cap,snapshot_cap", [(1702, 5000), (5000, 1702)])
def test_apply_rejects_one_cent_over_the_smaller_cap_without_mutation(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    request_cap: int,
    snapshot_cap: int,
) -> None:
    seed_user()
    base_id, proposal_id = pantry_proposal(
        session,
        cap=snapshot_cap,
        constraints=CONSTRAINTS.model_copy(update={"plan_cap_cents": request_cap}),
    )
    base = session.get(PlanRevision, base_id)
    row = session.get(PlanProposal, proposal_id)
    assert base is not None and row is not None
    original = PlanSnapshot.model_validate(base.snapshot)
    base_estimate = plan_groceries(
        GroceryRequest(
            meals=[MealRequest(recipe_id="bean_tacos", servings=2)],
            budget_period=datetime.now(UTC).date().replace(day=1),
            pantry_ingredients=original.pantry_ingredient_ids,
        ),
        BudgetResult(1702, 0, False, ()),
    )
    assert base_estimate.accepted and base_estimate.total_cents == 1104
    before = revision_count(session)
    updated_at = row.updated_at

    for _ in range(2):
        response = client.post(
            f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
        )
        assert response.status_code == 409
        assert response.json() == {
            "detail": {
                "code": "proposal_constraints",
                "reason": "over_budget",
                "total_cents": 1703,
                "available_cents": 1702,
            }
        }
        session.refresh(row)
        session.refresh(base)
        assert row.status == "pending"
        assert row.applied_plan_revision_id is None
        assert row.updated_at == updated_at
        assert revision_count(session) == before
        assert base.snapshot == original.model_dump(mode="json")


@pytest.mark.parametrize(
    "browser_cap,request_cap,snapshot_cap",
    [(1702, 5000, 5000), (5000, 1702, 5000), (5000, 5000, 1702)],
)
def test_apply_browser_cap_can_only_tighten_stored_caps(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    browser_cap: int,
    request_cap: int,
    snapshot_cap: int,
) -> None:
    seed_user()
    base_id, proposal_id = pantry_proposal(
        session,
        cap=snapshot_cap,
        constraints=CONSTRAINTS.model_copy(update={"plan_cap_cents": request_cap}),
    )
    base = session.get(PlanRevision, base_id)
    row = session.get(PlanProposal, proposal_id)
    assert base is not None and row is not None
    original = PlanSnapshot.model_validate(base.snapshot).model_dump(mode="json")
    before = revision_count(session)
    updated_at = row.updated_at

    for _ in range(2):
        response = client.post(
            f"/grocery/proposals/{proposal_id}/apply",
            json={"plan_cap_cents": browser_cap},
        )
        assert response.status_code == 409
        assert response.json() == {
            "detail": {
                "code": "proposal_constraints",
                "reason": "over_budget",
                "total_cents": 1703,
                "available_cents": 1702,
            }
        }
        session.refresh(row)
        session.refresh(base)
        assert row.status == "pending"
        assert row.applied_plan_revision_id is None
        assert row.updated_at == updated_at
        assert revision_count(session) == before
        assert base.snapshot == original


def test_apply_browser_cap_commits_snapshot_and_applied_retries(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    _, proposal_id = pantry_proposal(
        session,
        cap=5000,
        constraints=CONSTRAINTS.model_copy(update={"plan_cap_cents": 5000}),
    )
    preview = client.get(f"/grocery/proposals/{proposal_id}").json()["preview"]
    preview["plan_cap_cents"] = 1703
    path = f"/grocery/proposals/{proposal_id}/apply"
    response = client.post(path, json={"plan_cap_cents": 1703})
    assert response.status_code == 200
    saved = session.get(PlanRevision, UUID(response.json()["plan_revision_id"]))
    assert saved is not None and saved.snapshot == preview
    assert response.json()["snapshot"] == saved.snapshot
    replay = client.post(path, json={"plan_cap_cents": 0})
    assert replay.status_code == 200
    assert replay.json() == response.json()
    assert client.get(f"/grocery/proposals/{proposal_id}").json()["preview"] == preview
    assert revision_count(session) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"plan_cap_cents": -1},
        {"plan_cap_cents": True},
        {"plan_cap_cents": False},
        {"plan_cap_cents": 1702.5},
        {"plan_cap_cents": 1702.0},
        {"plan_cap_cents": "1702"},
        {"plan_cap_cents": None},
        {"plan_cap_cents": 5000, "diet": "vegan"},
    ],
)
def test_apply_rejects_invalid_browser_caps_without_mutation(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    payload: dict[str, object],
) -> None:
    seed_user()
    base_id, proposal_id = pantry_proposal(session, cap=5000)
    base = session.get(PlanRevision, base_id)
    row = session.get(PlanProposal, proposal_id)
    assert base is not None and row is not None
    original = PlanSnapshot.model_validate(base.snapshot).model_dump(mode="json")
    before = revision_count(session)
    updated_at = row.updated_at
    response = client.post(f"/grocery/proposals/{proposal_id}/apply", json=payload)
    assert response.status_code == 422
    session.refresh(row)
    session.refresh(base)
    assert row.status == "pending"
    assert row.applied_plan_revision_id is None
    assert row.updated_at == updated_at
    assert revision_count(session) == before
    assert base.snapshot == original


@pytest.mark.parametrize("action", ["apply", "discard"])
@pytest.mark.parametrize("body", [None, "{}", "null", "[]", '{"confirm": false}'])
def test_proposal_mutations_require_explicit_json_proof(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    action: str,
    body: str | None,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/{action}",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    row = session.get(PlanProposal, proposal_id)
    assert row is not None and row.status == "pending"
    assert revision_count(session) == 1


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_discard_requires_a_strict_true_confirmation(
    client: TestClient, session: Session, seed_user: UserSeeder, value: object
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/discard", json={"confirm": value}
    )
    assert response.status_code == 422
    row = session.get(PlanProposal, proposal_id)
    assert row is not None and row.status == "pending"


def test_apply_accepts_the_final_pantry_at_the_cap(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    _, proposal_id = pantry_proposal(session, cap=1104, owned=True)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )
    assert response.status_code == 200
    saved = session.get(PlanRevision, UUID(response.json()["plan_revision_id"]))
    assert saved is not None
    assert saved.snapshot["pantry_ingredient_ids"] == ["olive_oil"]
    assert saved.snapshot["plan_cap_cents"] == 1104


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"diet": "vegan"}, "diet_conflict"),
        ({"ingredient_exclusions": ["chicken_breast"]}, "exclusion_conflict"),
        (
            {"ingredient_exclusions": ["unrecognized restriction"]},
            "estimate_unavailable",
        ),
    ],
)
def test_apply_checks_diet_and_exclusions_even_for_pantry_ingredients(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    changes: dict[str, object],
    reason: str,
) -> None:
    seed_user()
    snapshot = base_snapshot().model_copy(
        update={"pantry_ingredient_ids": list(INGREDIENTS)}
    )
    base_id = seed_revision(session, snapshot)
    proposal_id = create_proposal(
        session,
        DEMO_USER_ID,
        base_id,
        [{"op": "add", "recipe_id": RECIPE_B, "servings": 3}],
        constraints=ApplyConstraints.model_validate(
            {**CONSTRAINTS.model_dump(mode="json"), **changes}
        ),
    )
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    before = revision_count(session)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "proposal_constraints", "reason": reason}
    }
    session.refresh(row)
    assert row.status == "pending"
    assert row.applied_plan_revision_id is None
    assert revision_count(session) == before


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {**CONSTRAINTS.model_dump(), "monthly_limit_cents": True},
        {**CONSTRAINTS.model_dump(), "plan_cap_cents": -1},
        {**CONSTRAINTS.model_dump(), "diet": "paleo"},
        {**CONSTRAINTS.model_dump(), "ingredient_exclusions": [1]},
    ],
)
def test_apply_fails_closed_for_missing_or_invalid_metadata(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    metadata: dict[str, object] | None,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    row.apply_constraints = metadata
    session.flush()
    before = revision_count(session)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "proposal_constraints", "reason": "estimate_unavailable"}
    }
    session.refresh(row)
    assert row.status == "pending"
    assert revision_count(session) == before


def test_apply_refreshes_spending_before_each_attempt(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    monkeypatch.setattr(proposals_api.grocery_api, "_ny_now", lambda: now)
    spending = SpendingInput(
        period=now.date().replace(day=1),
        posted_cents=8298,
        pending_cents=400,
        refreshed_at=now,
    )
    loads: list[str] = []

    def load(db: Session, source: str, clock: datetime, user_id: int) -> SpendingInput:
        assert db is session and clock == now
        assert user_id == 1
        loads.append(source)
        return spending

    monkeypatch.setattr(proposals_api.grocery_api, "require_spending", load)
    _, proposal_id = pantry_proposal(
        session,
        cap=5000,
        constraints=CONSTRAINTS.model_copy(update={"monthly_limit_cents": 10_000}),
    )
    path = f"/grocery/proposals/{proposal_id}/apply"
    rejected = client.post(path, json={"plan_cap_cents": 5000})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["available_cents"] == 1702
    assert revision_count(session) == 1
    spending = spending.model_copy(update={"posted_cents": 8297})
    assert client.post(path, json={"plan_cap_cents": 5000}).status_code == 200
    assert revision_count(session) == 2
    assert loads == ["manual", "manual"]


@pytest.mark.parametrize("unavailable", [False, True])
def test_apply_requires_spending_and_uses_explicit_cap_when_stale(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    unavailable: bool,
) -> None:
    seed_user()
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    monkeypatch.setattr(proposals_api.grocery_api, "_ny_now", lambda: now)

    def load(db: Session, source: str, clock: datetime, user_id: int) -> SpendingInput:
        if unavailable:
            raise HTTPException(status_code=503, detail="Spending is unavailable")
        return SpendingInput(
            period=now.date().replace(day=1),
            posted_cents=0,
            pending_cents=0,
            refreshed_at=now - timedelta(days=2),
        )

    monkeypatch.setattr(proposals_api.grocery_api, "require_spending", load)
    _, proposal_id = pantry_proposal(session, cap=None)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )
    assert response.status_code == (503 if unavailable else 200)
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    assert row.status == ("pending" if unavailable else "applied")
    assert (row.applied_plan_revision_id is None) is unavailable
    assert revision_count(session) == (1 if unavailable else 2)


def test_apply_rejects_missing_purchase_estimate_without_echoing_catalog_data(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    _, proposal_id = pantry_proposal(session)
    monkeypatch.setitem(
        INGREDIENTS, "olive_oil", replace(INGREDIENTS["olive_oil"], price_cents=None)
    )
    response = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "proposal_constraints", "reason": "estimate_unavailable"}
    }
    row = session.get(PlanProposal, proposal_id)
    assert row is not None and row.status == "pending"
    assert revision_count(session) == 1


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
        response = client.post(
            f"/grocery/proposals/{foreign_id}/{action}",
            json={"plan_cap_cents": 5000} if action == "apply" else {"confirm": True},
        )
        assert response.status_code == 404


def test_apply_creates_one_revision_and_is_idempotent(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    before = revision_count(session)

    first = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )
    second = client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )

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
    assert mutation_admission == [(session, 1, "mutation")]


def test_applied_replay_needs_no_metadata_or_backend_context(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    path = f"/grocery/proposals/{proposal_id}/apply"
    first = client.post(path, json={"plan_cap_cents": 5000})
    assert first.status_code == 200
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    row.apply_constraints = None
    session.flush()

    def unavailable() -> GroceryProviderSettings:
        raise AssertionError("Applied replay MUST NOT load provider settings")

    monkeypatch.setattr(proposals_api, "get_provider_settings", unavailable)
    replay = client.post(path, json={"plan_cap_cents": 5000})
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert revision_count(session) == 2


def test_discard_is_idempotent_and_blocks_apply(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    before = revision_count(session)

    path = f"/grocery/proposals/{proposal_id}"
    assert client.post(f"{path}/discard", json={"confirm": True}).status_code == 200
    assert client.post(f"{path}/discard", json={"confirm": True}).status_code == 200
    assert client.post(f"{path}/discard").status_code == 422
    response = client.post(f"{path}/apply", json={"plan_cap_cents": 5000})

    assert response.status_code == 409
    assert revision_count(session) == before
    assert client.get(f"/grocery/proposals/{proposal_id}").json()["status"] == (
        "discarded"
    )
    assert mutation_admission == [(session, 1, "mutation")]


def test_discarding_an_applied_proposal_is_409(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    client.post(
        f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
    )

    response = client.post(
        f"/grocery/proposals/{proposal_id}/discard", json={"confirm": True}
    )

    assert response.status_code == 409
    assert client.get(f"/grocery/proposals/{proposal_id}").json()["status"] == (
        "applied"
    )


@pytest.mark.parametrize("first", ["get", "apply"])
def test_stale_proposal_reads_preserve_state_and_apply_discards(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
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

    response = (
        client.get(path)
        if first == "get"
        else client.post(f"{path}/apply", json={"plan_cap_cents": 5000})
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == proposals_api.PROPOSAL_STALE_MESSAGE
    assert RECIPE_A not in response.text
    assert revision_count(session) == before
    row = session.get(PlanProposal, proposal_id)
    assert row is not None
    assert row.status == ("pending" if first == "get" else "discarded")
    if first == "get":
        assert mutation_admission == []
        assert client.get(path).status_code == 409
        stale_apply = client.post(f"{path}/apply", json={"plan_cap_cents": 5000})
        assert stale_apply.status_code == 409
        session.refresh(row)
        assert row.status == "discarded"
    assert mutation_admission == [(session, 1, "mutation")]

    again = client.get(path)

    assert again.status_code == 200
    assert again.json()["status"] == "discarded"
    assert again.json()["preview"] is None
    blocked = client.post(f"{path}/apply", json={"plan_cap_cents": 5000})
    assert blocked.status_code == 409
    assert revision_count(session) == before


def test_stale_discard_leaves_an_applied_proposal_alone(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    assert (
        client.post(
            f"/grocery/proposals/{proposal_id}/apply", json={"plan_cap_cents": 5000}
        ).status_code
        == 200
    )
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

    response = client.post(
        f"/grocery/proposals/{proposal_id}/{action}",
        json={"plan_cap_cents": 5000} if action == "apply" else {"confirm": True},
    )
    assert response.status_code == 200

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
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
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
        db: Session, requested: UUID, user_id: int, *, lock: bool = False
    ) -> PlanProposal:
        assert len(mutation_admission) == int(lock)
        flags.append(lock)
        return real_load(db, requested, user_id, lock=lock)

    def record_scalars(
        statement: Select[Any], *args: object, **kwargs: object
    ) -> ScalarResult[Any]:
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return real_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(proposals_api, "_load", record_load)
    monkeypatch.setattr(session, "scalars", record_scalars)

    path = f"/grocery/proposals/{proposal_id}{suffix}"
    response = (
        client.get(path)
        if method == "get"
        else client.post(
            path,
            json={"plan_cap_cents": 5000} if suffix == "/apply" else {"confirm": True},
        )
    )

    assert response.status_code == 200
    assert flags == ([False, True] if locks else [False])
    selects = [sql for sql in statements if "FROM plan_proposals" in sql]
    assert len(selects) == (2 if locks else 1)
    assert "FOR UPDATE" not in selects[0]
    if locks:
        assert "FOR UPDATE" in selects[1]


@pytest.mark.parametrize("action", ["apply", "discard"])
@pytest.mark.parametrize("status", ["applied", "discarded"])
def test_proposal_mutations_recheck_state_after_lock(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    mutation_admission: list[tuple[Session, int, security_admission.Action]],
    action: str,
    status: str,
) -> None:
    seed_user()
    proposal_id = make_proposal(session)
    row = session.get(PlanProposal, proposal_id)
    assert row is not None and row.status == "pending"
    applied_id: UUID | None = None
    if status == "applied":
        applied_id = seed_revision(session, base_snapshot())
    before = revision_count(session)
    load = proposals_api._load

    def change_at_lock(
        db: Session, requested: UUID, user_id: int, *, lock: bool = False
    ) -> PlanProposal:
        if lock:
            assert mutation_admission == [(session, 1, "mutation")]
            db.execute(
                PlanProposal.__table__.update()
                .where(PlanProposal.id == requested)
                .values(status=status, applied_plan_revision_id=applied_id)
            )
            assert row.status == "pending"
        return load(db, requested, user_id, lock=lock)

    monkeypatch.setattr(proposals_api, "_load", change_at_lock)
    response = client.post(
        f"/grocery/proposals/{proposal_id}/{action}",
        json={"plan_cap_cents": 5000} if action == "apply" else {"confirm": True},
    )
    matching = (action, status) in (("apply", "applied"), ("discard", "discarded"))
    assert response.status_code == (200 if matching else 409)
    if action == "apply" and status == "applied":
        assert response.status_code == 200
        assert response.json()["plan_revision_id"] == str(applied_id)
    assert row.status == status
    assert row.applied_plan_revision_id == applied_id
    assert revision_count(session) == before
    assert mutation_admission == [(session, 1, "mutation")]


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


def test_migration_0011_adds_nullable_constraints_and_downgrades() -> None:
    path = MIGRATION_PATH.with_name("0011_add_plan_proposal_constraints.py")
    spec = importlib.util.spec_from_file_location("alembic_rev_0011", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0011"
    assert module.down_revision == "0010"
    for direction, expected in (
        ("upgrade", "ADD COLUMN"),
        ("downgrade", "DROP COLUMN"),
    ):
        buffer = StringIO()
        context = MigrationContext.configure(
            dialect=postgresql.dialect(),
            opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
        )
        with Operations.context(context):
            getattr(module, direction)()
        sql = buffer.getvalue()
        assert "plan_proposals" in sql and "apply_constraints" in sql
        assert expected in sql
        assert "NOT NULL" not in sql
        assert "DEFAULT" not in sql


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
            "created_at IS NOT NULL, updated_at IS NOT NULL, apply_constraints"
        ),
        {"p": uuid4(), "u": user_id, "r": revision_id},
    ).one()
    assert tuple(row) == ("pending", None, True, True, None)


def test_postgres_apply_rejection_preserves_the_committed_plan_and_proposal(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as setup:
        Base.metadata.create_all(
            setup.connection(),
            tables=[
                models.User.__table__,
                PlanRevision.__table__,
                PlanProposal.__table__,
                QuotaCounter.__table__,
            ],
        )
        setup.add(models.User(id=DEMO_USER_ID, display_name="demo"))
        setup.flush()
        base_id, proposal_id = pantry_proposal(setup)
        setup.commit()
        original = setup.get(PlanRevision, base_id)
        assert original is not None
        snapshot = dict(original.snapshot)

    for _ in range(2):
        with Session(postgres_engine) as attempt:
            user = attempt.get(models.User, 1)
            assert user is not None
            result = proposals_api.apply_proposal(
                proposal_id,
                proposals_api.ApplyProposalRequest(plan_cap_cents=5000),
                attempt,
                user,
            )
            assert isinstance(result, JSONResponse)
            assert result.status_code == 409
            assert json.loads(bytes(result.body)) == {
                "detail": {
                    "code": "proposal_constraints",
                    "reason": "over_budget",
                    "total_cents": 1703,
                    "available_cents": 1702,
                }
            }

    with Session(postgres_engine) as check:
        assert revision_count(check) == 1
        assert check.scalar(select(func.count()).select_from(QuotaCounter)) == 0
        base = check.get(PlanRevision, base_id)
        row = check.get(PlanProposal, proposal_id)
        assert base is not None and base.snapshot == snapshot
        assert row is not None and row.status == "pending"
        assert row.applied_plan_revision_id is None


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
                QuotaCounter.__table__,
            ],
        )
        setup.add(models.User(id=DEMO_USER_ID, display_name="demo"))
        setup.flush()
        base_id = seed_revision(setup, base_snapshot(), user_id=DEMO_USER_ID)
        proposal_id = create_proposal(
            setup, DEMO_USER_ID, base_id, ops, constraints=CONSTRAINTS
        )
        setup.commit()

    with Session(postgres_engine) as holder, Session(postgres_engine) as waiter:
        user = waiter.get(models.User, 1)
        assert user is not None
        holder.scalars(
            select(PlanProposal).where(PlanProposal.id == proposal_id).with_for_update()
        ).one()
        waiter.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            proposals_api.apply_proposal(
                proposal_id,
                proposals_api.ApplyProposalRequest(plan_cap_cents=5000),
                waiter,
                user,
            )
        waiter.rollback()
        holder.rollback()

        with Session(postgres_engine) as check:
            count = check.scalars(select(func.count()).select_from(PlanRevision))
            assert count.one() == 1
            pending = check.get(PlanProposal, proposal_id)
            assert pending is not None
            assert pending.status == "pending"

        result = proposals_api.apply_proposal(
            proposal_id,
            proposals_api.ApplyProposalRequest(plan_cap_cents=5000),
            waiter,
            user,
        )

    with Session(postgres_engine) as check:
        count = check.scalars(select(func.count()).select_from(PlanRevision))
        assert count.one() == 2
        mutation_count = check.scalar(
            select(QuotaCounter.count).where(
                QuotaCounter.action == "mutation",
                QuotaCounter.scope == "user",
                QuotaCounter.scope_key == DEMO_USER_ID,
            )
        )
        assert mutation_count == 1
        applied = check.get(PlanProposal, proposal_id)
        assert applied is not None
        assert isinstance(result, proposals_api.AppliedProposalResponse)
        assert str(applied.applied_plan_revision_id) == result.plan_revision_id
