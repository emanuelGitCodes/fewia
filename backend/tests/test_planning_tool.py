import copy
import json
from calendar import monthrange
from dataclasses import asdict
from datetime import date
from hashlib import sha256
from typing import cast
from unittest.mock import patch

import pytest
from botocore.exceptions import ParamValidationError
from botocore.session import Session
from botocore.validate import validate_parameters

from app.agent.chat_messages import tool_result_block
from app.agent.planning_tool import (
    TOOL_NAME,
    PlanningToolError,
    execute_plan,
    planner_tool_spec,
)
from app.domain.budget import BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest, MealRequest
from app.services.meal_nutrition import (
    NOTICE,
    PORTION_NOTICE,
    MacroTotals,
    MealPlanNutrition,
    meal_nutrition,
)
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
    properties = schema["properties"]
    for field in (
        "meals",
        "budget_period",
        "plan_cap_cents",
        "pantry_ingredients",
        "ingredient_exclusions",
        "diet",
    ):
        description = properties[field]["description"]
        assert isinstance(description, str)
        assert description.strip()
    meal_properties = schema["$defs"]["MealRequest"]["properties"]
    for field in ("recipe_id", "servings"):
        description = meal_properties[field]["description"]
        assert isinstance(description, str)
        assert description.strip()
    description = tool_spec["description"]
    assert isinstance(description, str)
    assert "does not purchase items" in description
    meals = schema["properties"]["meals"]
    assert meals["minItems"] == 1
    assert meals["maxItems"] == 3
    servings = MealRequest.model_json_schema()["properties"]["servings"]
    assert servings["minimum"] == 1
    assert servings["maximum"] == 8
    json.dumps(spec)


def test_grocery_request_dump_is_unchanged_by_schema_descriptions() -> None:
    request = GroceryRequest.model_validate(arguments())
    assert request.model_dump() == {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
        "plan_cap_cents": None,
        "pantry_ingredients": [],
        "ingredient_exclusions": [],
        "diet": "omnivore",
    }
    assert request.model_dump(mode="json") == {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": "2026-09-01",
        "plan_cap_cents": None,
        "pantry_ingredients": [],
        "ingredient_exclusions": [],
        "diet": "omnivore",
    }


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
    assert caught.value.error_code is None
    assert caught.value.detail == {}


def test_unsupported_recipe_raises_typed_error() -> None:
    unknown = "sushi"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(
            arguments(meals=[{"recipe_id": unknown, "servings": 1}]),
            budget(),
            PERIOD,
        )
    _assert_static(caught.value, unknown)
    assert str(caught.value) == "recipe is not supported"
    assert caught.value.error_code == "unsupported_recipe"
    assert caught.value.detail == {}
    assert unknown not in str(caught.value)
    assert unknown not in str(caught.value.detail)


def test_unsupported_recipe_with_invalid_servings_stays_generic() -> None:
    unknown = "sushi"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(
            arguments(meals=[{"recipe_id": unknown, "servings": 9}]),
            budget(),
            PERIOD,
        )
    _assert_static(caught.value, unknown)
    assert str(caught.value) == "arguments are invalid"
    assert caught.value.error_code is None
    assert caught.value.detail == {}
    assert unknown not in str(caught.value)
    assert unknown not in str(caught.value.detail)


def test_invalid_period_raises_without_raw_input() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(), budget(), date(2026, 9, 2))
    _assert_static(caught.value, "2026-09-02")
    assert str(caught.value) == "period is invalid"


def test_catalog_constraint_raises_without_raw_input() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(diet="vegan"), budget(), PERIOD)
    _assert_static(caught.value, "chicken_breast")
    assert str(caught.value) == "catalog constraint is invalid"
    assert caught.value.error_code is None
    assert caught.value.detail == {}


def test_unsupported_diet_raises_typed_error() -> None:
    unknown = "<script>do-not-echo-raw-input</script>"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(diet=unknown), budget(), PERIOD)
    _assert_static(caught.value, unknown)
    assert str(caught.value) == "diet is not supported"
    assert caught.value.error_code == "unsupported_diet"
    assert caught.value.detail == {}
    assert unknown not in str(caught.value)
    assert unknown not in str(caught.value.detail)
    assert "ValidationError" not in str(caught.value)


def test_unsupported_diet_with_invalid_servings_stays_generic() -> None:
    unknown = "keto"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(
            arguments(
                diet=unknown,
                meals=[{"recipe_id": "chicken_tacos", "servings": 9}],
            ),
            budget(),
            PERIOD,
        )
    _assert_static(caught.value, unknown)
    assert str(caught.value) == "arguments are invalid"
    assert caught.value.error_code is None
    assert caught.value.detail == {}
    assert unknown not in str(caught.value)
    assert "unsupported_diet" not in str(caught.value)


def test_unsupported_diet_wrong_type_stays_generic() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(diet=1), budget(), PERIOD)
    _assert_static(caught.value, "1")
    assert str(caught.value) == "arguments are invalid"
    assert caught.value.error_code is None
    assert caught.value.detail == {}


def test_unknown_pantry_ingredient_raises_typed_error() -> None:
    unknown = "not_in_catalog"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(pantry_ingredients=[unknown]), budget(), PERIOD)
    _assert_static(caught.value, unknown)
    assert str(caught.value) == "ingredient is not supported"
    assert caught.value.error_code == "unsupported_ingredient"
    assert caught.value.detail == {"field": "pantry_ingredients"}
    assert unknown not in str(caught.value)
    assert unknown not in str(caught.value.detail)


def test_unknown_exclusion_ingredient_raises_typed_error() -> None:
    unknown = "not_in_catalog"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(ingredient_exclusions=[unknown]), budget(), PERIOD)
    _assert_static(caught.value, unknown)
    assert str(caught.value) == "ingredient is not supported"
    assert caught.value.error_code == "unsupported_ingredient"
    assert caught.value.detail == {"field": "ingredient_exclusions"}
    assert unknown not in str(caught.value)
    assert unknown not in str(caught.value.detail)


def test_unknown_ingredient_ids_never_leak() -> None:
    malicious = "<script>do-not-echo-raw-input</script>"
    pantry_unknowns = [malicious, "also_unknown"]
    with pytest.raises(PlanningToolError) as pantry_caught:
        execute_plan(
            arguments(pantry_ingredients=pantry_unknowns),
            budget(),
            PERIOD,
        )
    _assert_static(pantry_caught.value, malicious)
    _assert_static(pantry_caught.value, "also_unknown")
    assert pantry_caught.value.error_code == "unsupported_ingredient"
    assert pantry_caught.value.detail == {"field": "pantry_ingredients"}
    with pytest.raises(PlanningToolError) as mixed_caught:
        execute_plan(
            arguments(
                pantry_ingredients=[malicious],
                ingredient_exclusions=["also_unknown"],
            ),
            budget(),
            PERIOD,
        )
    _assert_static(mixed_caught.value, malicious)
    _assert_static(mixed_caught.value, "also_unknown")
    assert mixed_caught.value.detail == {"field": "pantry_ingredients"}
    with pytest.raises(PlanningToolError) as exclusion_caught:
        execute_plan(
            arguments(
                pantry_ingredients=["salt"],
                ingredient_exclusions=[malicious, "also_unknown"],
            ),
            budget(),
            PERIOD,
        )
    _assert_static(exclusion_caught.value, malicious)
    _assert_static(exclusion_caught.value, "also_unknown")
    assert exclusion_caught.value.detail == {"field": "ingredient_exclusions"}


def test_exclusion_conflict_raises_static_typed_error() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(
            arguments(
                meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
                ingredient_exclusions=["onion"],
            ),
            budget(),
            PERIOD,
        )
    _assert_static(caught.value, "onion")
    assert caught.value.args == ("ingredient is excluded",)
    assert caught.value.error_code == "exclusion_reject"
    assert caught.value.detail == {
        "recipe_id": "vegetable_pasta",
        "ingredient_id": "onion",
    }


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


def test_manual_source_is_retained_and_unknown_raises() -> None:
    manual = execute_plan(arguments(), budget(), PERIOD, spending_source="manual")
    assert manual["spending_source"] == "manual"
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(), budget(), PERIOD, spending_source="unknown")
    _assert_static(caught.value, "unknown")
    assert str(caught.value) == "spending_source is invalid"


def _expected_evidence(result: dict[str, object], user_id: int = 1) -> str:
    last_day = monthrange(PERIOD.year, PERIOD.month)[1]
    digest = sha256(
        json.dumps(
            {
                "budget": result["budget"],
                "meal_nutrition": result["meal_nutrition"],
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
        "meal_nutrition",
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


def _converse_tool_result_params(payload: dict[str, object]) -> dict[str, object]:
    return {
        "modelId": "model-id",
        "messages": [
            {
                "role": "user",
                "content": [tool_result_block("call-1", payload, success=True)],
            }
        ],
    }


def test_execute_plan_tool_result_matches_converse_input_shape() -> None:
    result = execute_plan(arguments(), budget(), PERIOD)
    plan_payload = result["plan"]
    assert isinstance(plan_payload, dict)
    lines = plan_payload["lines"]
    warnings = plan_payload["warnings"]
    assert isinstance(lines, list)
    assert isinstance(warnings, list)
    session = Session()
    service_model = session.get_service_model("bedrock-runtime")
    operation = service_model.operation_model("Converse")
    input_shape = operation.input_shape
    validate_parameters(_converse_tool_result_params(result), input_shape)
    rejected = dict(result)
    rejected_plan = dict(plan_payload)
    rejected_plan["lines"] = tuple(lines)
    rejected_plan["warnings"] = tuple(warnings)
    rejected["plan"] = rejected_plan
    with pytest.raises(ParamValidationError):
        validate_parameters(_converse_tool_result_params(rejected), input_shape)


def test_default_execute_plan_omits_supermarket_estimate() -> None:
    result = execute_plan(arguments(), budget(), PERIOD)
    assert "supermarket_estimate" not in result
    assert set(result) == {
        "request",
        "plan",
        "budget",
        "meal_nutrition",
        "spending_source",
        "evidence_id",
    }


def test_execute_plan_returns_json_native_meal_nutrition() -> None:
    request = GroceryRequest.model_validate(arguments())
    expected = json.loads(json.dumps(asdict(meal_nutrition(request)), allow_nan=False))
    result = execute_plan(arguments(), budget(), PERIOD)
    nutrition = result["meal_nutrition"]
    assert nutrition == expected
    assert isinstance(nutrition, dict)
    total = nutrition["total"]
    meals = nutrition["meals"]
    assert isinstance(total, dict)
    assert isinstance(meals, list)
    assert nutrition["notice"] == NOTICE
    assert nutrition["portion_notice"] == PORTION_NOTICE
    assert type(total["energy_kcal"]) is int


def test_pantry_does_not_change_meal_nutrition() -> None:
    without = execute_plan(arguments(), budget(), PERIOD)
    with_pantry = execute_plan(
        arguments(pantry_ingredients=["chicken_breast"]), budget(), PERIOD
    )
    assert without["meal_nutrition"] == with_pantry["meal_nutrition"]
    without_plan = without["plan"]
    pantry_plan = with_pantry["plan"]
    assert isinstance(without_plan, dict)
    assert isinstance(pantry_plan, dict)
    assert without_plan["total_cents"] != pantry_plan["total_cents"]


def test_meal_nutrition_tool_result_is_json_native() -> None:
    result = execute_plan(arguments(), budget(), PERIOD)
    nutrition = result["meal_nutrition"]
    assert isinstance(nutrition, dict)
    meals = nutrition["meals"]
    assert isinstance(meals, list)
    session = Session()
    service_model = session.get_service_model("bedrock-runtime")
    operation = service_model.operation_model("Converse")
    input_shape = operation.input_shape
    validate_parameters(_converse_tool_result_params(result), input_shape)
    rejected = dict(result)
    rejected_nutrition = dict(nutrition)
    rejected_nutrition["meals"] = tuple(meals)
    rejected["meal_nutrition"] = rejected_nutrition
    with pytest.raises(ParamValidationError):
        validate_parameters(_converse_tool_result_params(rejected), input_shape)


def test_changed_nutrition_changes_evidence_id() -> None:
    first = execute_plan(arguments(), budget(), PERIOD)
    alt = MealPlanNutrition(
        NOTICE,
        PORTION_NOTICE,
        MacroTotals(1, 2, 3, 4),
        (),
    )
    with patch("app.agent.planning_tool.meal_nutrition", return_value=alt):
        second = execute_plan(arguments(), budget(), PERIOD)
    assert first["evidence_id"] != second["evidence_id"]
    assert first["plan"] == second["plan"]
    assert first["budget"] == second["budget"]
    assert first["request"] == second["request"]
