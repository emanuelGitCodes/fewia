import copy
import json
from calendar import monthrange
from datetime import date
from hashlib import sha256
from typing import cast

import pytest

from app.agent.planning_tool import (
    TOOL_NAME,
    PlanningToolError,
    execute_plan,
    planner_tool_spec,
)
from app.domain.budget import BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest, MealRequest
from app.tools.base import build_evidence_id

PERIOD = date(2026, 9, 1)


def arguments(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
    }
    values.update(overrides)
    return values


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 250, False, ())


def _assert_static(error: BaseException, token: str) -> None:
    assert token not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_planner_tool_spec_uses_grocery_request_schema_bounds() -> None:
    spec = planner_tool_spec()
    tool_spec = spec["toolSpec"]
    assert isinstance(tool_spec, dict)
    assert tool_spec["name"] == TOOL_NAME
    input_schema = tool_spec["inputSchema"]
    assert isinstance(input_schema, dict)
    schema = GroceryRequest.model_json_schema()
    assert input_schema["json"] == schema
    meals = schema["properties"]["meals"]
    assert meals["minItems"] == 1
    assert meals["maxItems"] == 3
    servings = MealRequest.model_json_schema()["properties"]["servings"]
    assert servings["minimum"] == 1
    assert servings["maximum"] == 8
    json.dumps(spec)


def test_model_cap_cannot_increase_available() -> None:
    result = execute_plan(arguments(plan_cap_cents=50_000), budget(1_000), PERIOD)
    budget_payload = result["budget"]
    assert isinstance(budget_payload, dict)
    assert budget_payload["available_cents"] == 1_000


def test_smaller_cap_applies() -> None:
    result = execute_plan(arguments(plan_cap_cents=100), budget(1_000), PERIOD)
    budget_payload = result["budget"]
    assert isinstance(budget_payload, dict)
    assert budget_payload["available_cents"] == 100
    plan_payload = result["plan"]
    assert isinstance(plan_payload, dict)
    assert plan_payload["accepted"] is False


def test_zero_available_does_not_raise() -> None:
    result = execute_plan(arguments(), budget(0), PERIOD)
    budget_payload = result["budget"]
    plan_payload = result["plan"]
    assert isinstance(budget_payload, dict)
    assert isinstance(plan_payload, dict)
    assert budget_payload["available_cents"] == 0
    assert plan_payload["accepted"] is False


def test_period_mismatch_raises() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(), budget(), date(2026, 8, 1))
    _assert_static(caught.value, "2026")
    assert str(caught.value) == "budget_period does not match the server period"


@pytest.mark.parametrize(
    ("kwargs", "token", "message"),
    [
        ({"user_id": 0}, "0", "user_id is invalid"),
        ({"user_id": -1}, "-1", "user_id is invalid"),
        ({"user_id": True}, "True", "user_id is invalid"),
        ({"spending_source": "live"}, "live", "spending_source is invalid"),
    ],
)
def test_invalid_user_and_source_raise_static_errors(
    kwargs: dict[str, object], token: str, message: str
) -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(), budget(), PERIOD, **kwargs)  # type: ignore[arg-type]
    _assert_static(caught.value, token)
    assert str(caught.value) == message


@pytest.mark.parametrize(
    ("args", "token"),
    [
        (arguments(meals=[{"recipe_id": "chicken_tacos", "servings": 9}]), "9"),
        (
            arguments(meals=[{"recipe_id": "bean_tacos", "servings": 2}] * 4),
            "bean_tacos",
        ),
        (arguments(user_id=7), "7"),
        (arguments(budget_period=date(2026, 9, 2)), "2026-09-02"),
    ],
)
def test_invalid_arguments_raise_static_errors(
    args: dict[str, object], token: str
) -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(args, budget(), PERIOD)
    _assert_static(caught.value, token)
    assert str(caught.value) == "arguments are invalid"


def test_invalid_period_raises_without_raw_input() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(), budget(), date(2026, 9, 2))
    _assert_static(caught.value, "2026-09-02")
    assert str(caught.value) == "period is invalid"


def test_catalog_constraint_raises_without_raw_input() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(pantry_ingredients=["not_in_catalog"]), budget(), PERIOD)
    _assert_static(caught.value, "not_in_catalog")
    assert str(caught.value) == "catalog constraint is invalid"


def test_notice_and_source_are_retained() -> None:
    fixture = execute_plan(arguments(), budget(), PERIOD)
    sandbox = execute_plan(
        arguments(), budget(), PERIOD, spending_source="plaid_sandbox"
    )
    fixture_plan = fixture["plan"]
    sandbox_plan = sandbox["plan"]
    assert isinstance(fixture_plan, dict)
    assert isinstance(sandbox_plan, dict)
    assert fixture_plan["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert sandbox_plan["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert fixture["spending_source"] == "fixture"
    assert sandbox["spending_source"] == "plaid_sandbox"


def _expected_evidence(result: dict[str, object], user_id: int = 1) -> str:
    last_day = monthrange(PERIOD.year, PERIOD.month)[1]
    digest = sha256(
        json.dumps(
            {
                "budget": result["budget"],
                "plan": result["plan"],
                "request": result["request"],
                "source": result["spending_source"],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:24]
    return build_evidence_id(
        f"grocery-{digest}",
        user_id,
        PERIOD,
        date(PERIOD.year, PERIOD.month, last_day),
    )


def test_evidence_id_is_deterministic() -> None:
    first = execute_plan(arguments(), budget(), PERIOD)
    second = execute_plan(arguments(), budget(), PERIOD)
    expected = _expected_evidence(first)
    assert first["evidence_id"] == second["evidence_id"] == expected
    assert cast(str, first["evidence_id"]).startswith("grocery-")
    assert cast(str, first["evidence_id"]).endswith(":user-1:2026-09")
    assert set(first) == {
        "request",
        "plan",
        "budget",
        "spending_source",
        "evidence_id",
    }
    json.dumps(first)


def test_pantry_and_budget_changes_change_evidence() -> None:
    base = execute_plan(arguments(), budget(), PERIOD)
    pantry = execute_plan(
        arguments(pantry_ingredients=["chicken_breast"]), budget(), PERIOD
    )
    cheaper = execute_plan(arguments(), budget(1), PERIOD)
    assert base["evidence_id"] != pantry["evidence_id"]
    assert base["evidence_id"] != cheaper["evidence_id"]
    assert pantry["evidence_id"] != cheaper["evidence_id"]


def test_execute_plan_does_not_mutate_inputs() -> None:
    args = arguments(pantry_ingredients=["salt"], plan_cap_cents=500)
    original_args = copy.deepcopy(args)
    original_budget = budget(1_000)
    result = execute_plan(args, original_budget, PERIOD)
    assert args == original_args
    assert original_budget == budget(1_000)
    budget_payload = result["budget"]
    assert isinstance(budget_payload, dict)
    assert budget_payload["available_cents"] == 500
    assert original_budget.available_cents == 1_000
