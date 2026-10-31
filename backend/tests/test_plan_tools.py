from dataclasses import asdict
from datetime import date

import pytest

from app.agent.facts import collect_facts
from app.agent.plan_tools import (
    GET_MEAL_TOOL,
    GET_PLAN_TOOL,
    PlanToolError,
    execute_get_meal,
    execute_get_plan,
    get_meal_tool_spec,
    get_plan_tool_spec,
)
from app.domain.budget import BudgetResult
from app.domain.catalog import RECIPES
from app.domain.grocery import (
    SAMPLE_ESTIMATE_NOTICE,
    SUPPORTED_RECIPE_IDS,
    GroceryRequest,
    MealRequest,
)
from app.domain.meal_tags import MEAL_DIETS, MEAL_TAGS
from app.domain.plan_revision import PlanRevisionInput
from app.services.grocery_planner import plan_groceries
from app.services.meal_nutrition import meal_nutrition

BUDGET = BudgetResult(10_000, 0, False, ())
REVISION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _plan(
    meals: list[dict[str, object]], pantry: list[str], cap: int = 5_000
) -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": REVISION_ID,
            "snapshot": {
                "meals": meals,
                "pantry_ingredient_ids": pantry,
                "plan_cap_cents": cap,
            },
        }
    )


def test_specs_have_expected_schemas() -> None:
    plan_spec = get_plan_tool_spec()["toolSpec"]
    meal_spec = get_meal_tool_spec()["toolSpec"]
    assert plan_spec["name"] == GET_PLAN_TOOL  # type: ignore[index]
    assert plan_spec["inputSchema"]["json"] == {  # type: ignore[index]
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert meal_spec["name"] == GET_MEAL_TOOL  # type: ignore[index]
    schema = meal_spec["inputSchema"]["json"]  # type: ignore[index]
    assert schema["required"] == ["recipe_id"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["recipe_id"]["enum"] == list(SUPPORTED_RECIPE_IDS)


def test_get_plan_matches_nutrition_and_estimate() -> None:
    a, b = SUPPORTED_RECIPE_IDS[0], SUPPORTED_RECIPE_IDS[1]
    pantry = [RECIPES[a].ingredients[0][0]]
    plan = _plan(
        [{"recipe_id": a, "servings": 2}, {"recipe_id": b, "servings": 3}], pantry
    )
    out = execute_get_plan({}, plan, BUDGET)

    request = GroceryRequest(
        meals=[
            MealRequest(recipe_id=a, servings=2),
            MealRequest(recipe_id=b, servings=3),
        ],
        budget_period=date(2026, 9, 1),
        pantry_ingredients=pantry,
    )
    nutrition = meal_nutrition(request)
    estimate = plan_groceries(request, BudgetResult(5_000, 0, False, ()))
    assert out["plan_revision_id"] == REVISION_ID
    assert out["pantry_ingredient_ids"] == pantry
    assert out["plan_cap_cents"] == 5_000
    assert out["total"] == asdict(nutrition.total)  # type: ignore[arg-type]
    meals = out["meals"]
    assert isinstance(meals, list)
    for item, expected in zip(meals, nutrition.meals, strict=True):
        assert item == {
            "recipe_id": expected.recipe_id,
            "servings": expected.servings,
            "per_serving": asdict(expected.per_serving),
            "total": asdict(expected.total),
        }
    est = out["estimate"]
    assert isinstance(est, dict)
    assert est["total_cents"] == estimate.total_cents
    assert est["accepted"] == estimate.accepted
    assert est["notice"] == estimate.notice == SAMPLE_ESTIMATE_NOTICE
    assert est["price_complete"] == (estimate.total_cents is not None)
    assert est["available_cents"] == 5_000
    assert [
        (
            x["ingredient_id"],
            x["quantity"],
            x["unit"],
            x["packages"],
            x["cost_cents"],
            x["from_pantry"],
        )
        for x in est["lines"]
    ] == [
        (x.ingredient_id, x.quantity, x.unit, x.packages, x.cost_cents, x.from_pantry)
        for x in estimate.lines
    ]
    facts = collect_facts(GET_PLAN_TOOL, out)
    assert any(f.path == "meals[0].per_serving.energy_kcal" for f in facts)


def test_get_plan_cap_below_total_rejects_estimate() -> None:
    meals = [{"recipe_id": SUPPORTED_RECIPE_IDS[0], "servings": 2}]
    open_plan = _plan(meals, [], cap=BUDGET.available_cents)
    uncapped = execute_get_plan({}, open_plan, BUDGET)
    uncapped_est = uncapped["estimate"]
    assert isinstance(uncapped_est, dict)
    total = uncapped_est["total_cents"]
    assert isinstance(total, int) and total > 0
    assert uncapped_est["accepted"] is True

    capped = execute_get_plan({}, _plan(meals, [], cap=total - 1), BUDGET)
    est = capped["estimate"]
    assert isinstance(est, dict)
    assert est["total_cents"] == total
    assert est["available_cents"] == total - 1
    assert est["accepted"] is False


def test_get_plan_without_plan_is_empty_shape() -> None:
    assert execute_get_plan({}, None, BUDGET) == {
        "plan_revision_id": None,
        "meals": [],
        "pantry_ingredient_ids": [],
        "plan_cap_cents": None,
    }


def test_get_plan_with_no_meals_has_no_total_or_estimate() -> None:
    out = execute_get_plan({}, _plan([], []), BUDGET)
    assert out["meals"] == []
    assert out["total"] is None
    assert out["estimate"] is None


@pytest.mark.parametrize("arguments", [{"x": 1}, None, [], "x"])
def test_get_plan_rejects_arguments(arguments: object) -> None:
    with pytest.raises(PlanToolError):
        execute_get_plan(arguments, None, BUDGET)


def test_get_meal_returns_catalog_ingredients_and_macros() -> None:
    out = execute_get_meal({"recipe_id": "chicken_tacos"})
    assert out["recipe_id"] == "chicken_tacos"
    ingredients = out["ingredients"]
    assert isinstance(ingredients, list)
    assert [(i["ingredient_id"], i["quantity"]) for i in ingredients] == list(
        RECIPES["chicken_tacos"].ingredients
    )
    request = GroceryRequest(
        meals=[MealRequest(recipe_id="chicken_tacos", servings=1)],
        budget_period=date(2026, 9, 1),
    )
    assert out["per_serving"] == asdict(meal_nutrition(request).meals[0].per_serving)
    assert out["diets"] == list(MEAL_DIETS["chicken_tacos"])
    assert out["tags"] == list(MEAL_TAGS["chicken_tacos"])


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"recipe_id": "nope"},
        {"recipe_id": 1},
        {"recipe_id": "chicken_tacos", "x": 1},
        None,
    ],
)
def test_get_meal_rejects_invalid_arguments(arguments: object) -> None:
    with pytest.raises(PlanToolError):
        execute_get_meal(arguments)
