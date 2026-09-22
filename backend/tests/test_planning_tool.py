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
    tool_error_body,
)
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import (
    SAMPLE_ESTIMATE_NOTICE,
    SUPPORTED_RECIPE_IDS,
    GroceryRequest,
    MealRequest,
)
from app.domain.supermarket_estimate import SPOONACULAR_COST_NOTICE
from app.providers.spoonacular import SpoonacularUnavailable
from app.services.grocery_planner import PlanEstimate, PlanningError
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


class _FakeEstimator:
    def __init__(
        self,
        *,
        cents: int = 25,
        error: type[BaseException] | None = None,
    ) -> None:
        self.cents = cents
        self.error = error

    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        if self.error is not None:
            raise self.error()
        return self.cents


def _assert_static(error: BaseException, token: str) -> None:
    assert token not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _tool_json(spec: dict[str, object]) -> dict[str, object]:
    tool_spec = _mapping(spec["toolSpec"])
    input_schema = _mapping(tool_spec["inputSchema"])
    return _mapping(input_schema["json"])


def test_planner_tool_spec_uses_grocery_request_schema_bounds() -> None:
    spec = planner_tool_spec()
    tool_spec = spec["toolSpec"]
    assert isinstance(tool_spec, dict)
    assert tool_spec["name"] == TOOL_NAME
    schema = _tool_json(spec)
    public = GroceryRequest.model_json_schema()
    meals = public["properties"]["meals"]
    tool_meals = _mapping(_mapping(schema["properties"])["meals"])
    assert meals["minItems"] == 1
    assert meals["maxItems"] == 3
    assert tool_meals["minItems"] == 1
    assert tool_meals["maxItems"] == 3
    servings = MealRequest.model_json_schema()["properties"]["servings"]
    tool_meal = _mapping(_mapping(schema["$defs"])["MealRequest"])
    tool_servings = _mapping(_mapping(tool_meal["properties"])["servings"])
    assert servings["minimum"] == 1
    assert servings["maximum"] == 8
    assert tool_servings["minimum"] == 1
    assert tool_servings["maximum"] == 8
    json.dumps(spec)


def _enum_list(schema: dict[str, object], *path: str) -> list[object]:
    current: object = schema
    for key in path:
        current = _mapping(current)[key]
    assert isinstance(current, list)
    return current


def test_planner_tool_spec_exposes_catalog_enums() -> None:
    schema = _tool_json(planner_tool_spec())
    catalog_ids = list(INGREDIENTS)
    recipe_enum = _enum_list(
        schema, "$defs", "MealRequest", "properties", "recipe_id", "enum"
    )
    pantry_enum = _enum_list(
        schema, "properties", "pantry_ingredients", "items", "enum"
    )
    exclusion_enum = _enum_list(
        schema, "properties", "ingredient_exclusions", "items", "enum"
    )
    assert recipe_enum == list(SUPPORTED_RECIPE_IDS)
    assert pantry_enum == catalog_ids
    assert exclusion_enum == catalog_ids
    assert "olive_oil" in pantry_enum
    assert "olive oil" not in pantry_enum
    public = GroceryRequest.model_json_schema()
    public_pantry = public["properties"]["pantry_ingredients"]["items"]
    public_recipe = public["$defs"]["MealRequest"]["properties"]["recipe_id"]
    assert "enum" not in public_pantry
    assert "enum" not in public_recipe


def test_planner_tool_spec_mutation_does_not_affect_later_call() -> None:
    first = _tool_json(planner_tool_spec())
    _enum_list(first, "$defs", "MealRequest", "properties", "recipe_id", "enum").append(
        "not_a_recipe"
    )
    _enum_list(first, "properties", "pantry_ingredients", "items", "enum").append(
        "olive oil"
    )
    _enum_list(first, "properties", "ingredient_exclusions", "items", "enum").append(
        "olive oil"
    )
    later = _tool_json(planner_tool_spec())
    catalog_ids = list(INGREDIENTS)
    assert _enum_list(
        later, "$defs", "MealRequest", "properties", "recipe_id", "enum"
    ) == list(SUPPORTED_RECIPE_IDS)
    assert (
        _enum_list(later, "properties", "pantry_ingredients", "items", "enum")
        == catalog_ids
    )
    assert (
        _enum_list(later, "properties", "ingredient_exclusions", "items", "enum")
        == catalog_ids
    )
    public = GroceryRequest.model_json_schema()
    assert "enum" not in public["properties"]["pantry_ingredients"]["items"]


def test_olive_oil_catalog_id_is_accepted() -> None:
    result = execute_plan(arguments(pantry_ingredients=["olive_oil"]), budget(), PERIOD)
    plan = result["plan"]
    assert isinstance(plan, dict)
    lines = plan["lines"]
    assert isinstance(lines, list)
    oil = next(line for line in lines if line["ingredient_id"] == "olive_oil")
    assert oil["from_pantry"] is True


def test_olive_oil_display_name_is_rejected_without_normalization() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(pantry_ingredients=["olive oil"]), budget(), PERIOD)
    _assert_static(caught.value, "olive oil")
    assert str(caught.value) == "catalog constraint is invalid"


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


def test_estimator_attaches_overlay_and_keeps_plan_total() -> None:
    without = execute_plan(arguments(), budget(), PERIOD)
    with_overlay = execute_plan(
        arguments(), budget(), PERIOD, supermarket_estimator=_FakeEstimator()
    )
    estimate = with_overlay["supermarket_estimate"]
    without_plan = without["plan"]
    overlay_plan = with_overlay["plan"]
    assert isinstance(estimate, dict)
    assert isinstance(without_plan, dict)
    assert isinstance(overlay_plan, dict)
    assert type(estimate["total_cents"]) is int
    assert estimate["notice"] == SPOONACULAR_COST_NOTICE
    assert overlay_plan["total_cents"] == without_plan["total_cents"]


def test_estimator_does_not_change_evidence_id() -> None:
    without = execute_plan(arguments(), budget(), PERIOD)
    with_overlay = execute_plan(
        arguments(), budget(), PERIOD, supermarket_estimator=_FakeEstimator()
    )
    assert with_overlay["evidence_id"] == without["evidence_id"]


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


def test_unavailable_overlay_is_none_and_keeps_accepted() -> None:
    without = execute_plan(arguments(), budget(), PERIOD)
    failed = execute_plan(
        arguments(),
        budget(),
        PERIOD,
        supermarket_estimator=_FakeEstimator(error=SpoonacularUnavailable),
    )
    estimate = failed["supermarket_estimate"]
    without_plan = without["plan"]
    failed_plan = failed["plan"]
    assert isinstance(estimate, dict)
    assert isinstance(without_plan, dict)
    assert isinstance(failed_plan, dict)
    assert estimate["total_cents"] is None
    assert failed_plan["accepted"] == without_plan["accepted"]


def test_vegan_breakfast_burritos_raises_static_diet_conflict() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(
            arguments(
                meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
                diet="vegan",
            ),
            budget(),
            PERIOD,
        )
    error = caught.value
    assert str(error) == "catalog constraint is invalid"
    _assert_static(error, "eggs")
    assert error.code == "diet_conflict"
    assert error.ingredient_id == "eggs"
    assert tool_error_body(error) == {
        "error": "diet_conflict",
        "ingredient_id": "eggs",
    }


def test_excluded_pantry_chicken_raises_static_exclusion_conflict() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(
            arguments(
                pantry_ingredients=["chicken_breast"],
                ingredient_exclusions=["chicken_breast"],
            ),
            budget(),
            PERIOD,
        )
    error = caught.value
    assert str(error) == "catalog constraint is invalid"
    _assert_static(error, "chicken_breast")
    assert error.code == "exclusion_conflict"
    assert error.ingredient_id == "chicken_breast"
    assert tool_error_body(error) == {
        "error": "exclusion_conflict",
        "ingredient_id": "chicken_breast",
    }


def test_unknown_pantry_stays_generic_catalog_constraint() -> None:
    with pytest.raises(PlanningToolError) as caught:
        execute_plan(arguments(pantry_ingredients=["not_in_catalog"]), budget(), PERIOD)
    error = caught.value
    assert str(error) == "catalog constraint is invalid"
    _assert_static(error, "not_in_catalog")
    assert error.code is None
    assert error.ingredient_id is None
    assert tool_error_body(error) == {"error": "arguments are invalid"}


def test_planning_tool_error_string_constructor_stays_compatible() -> None:
    error = PlanningToolError("arguments are invalid")
    assert str(error) == "arguments are invalid"
    assert error.code is None
    assert error.ingredient_id is None
    assert tool_error_body(error) == {"error": "arguments are invalid"}


def test_planning_error_message_is_not_parsed_into_conflict() -> None:
    def boom(*_args: object, **_kwargs: object) -> PlanEstimate:
        raise PlanningError("ingredient conflicts with diet: eggs")

    with patch("app.agent.planning_tool.plan_groceries", boom):
        with pytest.raises(PlanningToolError) as caught:
            execute_plan(arguments(), budget(), PERIOD)
    error = caught.value
    assert str(error) == "catalog constraint is invalid"
    _assert_static(error, "eggs")
    assert error.code is None
    assert error.ingredient_id is None
    assert tool_error_body(error) == {"error": "arguments are invalid"}


def test_malicious_tool_error_metadata_is_generic() -> None:
    unknown_code = PlanningToolError(
        "catalog constraint is invalid",
        code="leak",
        ingredient_id="eggs",
    )
    unknown_id = PlanningToolError(
        "catalog constraint is invalid",
        code="diet_conflict",
        ingredient_id="not_in_catalog",
    )
    assert tool_error_body(unknown_code) == {"error": "arguments are invalid"}
    assert tool_error_body(unknown_id) == {"error": "arguments are invalid"}
    dumped = json.dumps([tool_error_body(unknown_code), tool_error_body(unknown_id)])
    assert "diet_conflict" not in dumped
    assert "eggs" not in dumped
    assert "not_in_catalog" not in dumped
    assert "leak" not in dumped


def test_vegan_overnight_oats_execute_plan_is_unchanged() -> None:
    result = execute_plan(
        arguments(
            meals=[{"recipe_id": "overnight_oats", "servings": 2}],
            diet="vegan",
        ),
        budget(),
        PERIOD,
    )
    plan = result["plan"]
    assert isinstance(plan, dict)
    assert plan["accepted"] is True
    assert "error" not in result
    assert "ingredient_id" not in result
