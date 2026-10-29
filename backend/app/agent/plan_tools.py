from dataclasses import asdict
from datetime import date
from typing import cast

from app.agent.estimate import priced_estimate
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.domain.meal_tags import MEAL_DIETS, MEAL_TAGS
from app.domain.plan_revision import PlanRevisionInput
from app.services.meal_nutrition import MacroTotals, meal_nutrition

GET_PLAN_TOOL = "get_plan"
GET_MEAL_TOOL = "get_meal"
_NO_PERIOD = date.min


class PlanToolError(ValueError):
    """A plan-tool failure with a static message and no raw input."""


def _spec(
    name: str, description: str, properties: dict[str, object], required: list[str]
) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return {
        "toolSpec": {
            "name": name,
            "description": description,
            "inputSchema": {"json": schema},
        }
    }


def get_plan_tool_spec() -> dict[str, object]:
    return _spec(
        GET_PLAN_TOOL,
        "Return the user's current plan with macros and a labeled estimate. "
        "The tool accepts no input. The tool does not purchase items.",
        {},
        [],
    )


def get_meal_tool_spec() -> dict[str, object]:
    return _spec(
        GET_MEAL_TOOL,
        "Return one catalog meal's ingredients per serving and macros.",
        {"recipe_id": {"type": "string", "enum": list(SUPPORTED_RECIPE_IDS)}},
        ["recipe_id"],
    )


def _macros(totals: MacroTotals) -> dict[str, object]:
    return cast(dict[str, object], asdict(totals))


def execute_get_plan(
    arguments: object, plan: PlanRevisionInput | None, budget: BudgetResult
) -> dict[str, object]:
    if type(arguments) is not dict or arguments:
        raise PlanToolError("arguments are invalid")
    if plan is None:
        return {
            "plan_revision_id": None,
            "meals": [],
            "pantry_ingredient_ids": [],
            "plan_cap_cents": None,
        }
    snapshot = plan.snapshot
    payload: dict[str, object] = {
        "plan_revision_id": str(plan.id),
        "meals": [],
        "pantry_ingredient_ids": list(snapshot.pantry_ingredient_ids),
        "plan_cap_cents": snapshot.plan_cap_cents,
        "total": None,
        "estimate": None,
    }
    if not snapshot.meals:
        return payload
    pairs = [(meal.recipe_id, meal.servings) for meal in snapshot.meals]
    nutrition = meal_nutrition(
        GroceryRequest(
            meals=[
                MealRequest(recipe_id=item, servings=count) for item, count in pairs
            ],
            budget_period=_NO_PERIOD,
        )
    )
    payload["meals"] = [
        {
            "recipe_id": meal.recipe_id,
            "servings": meal.servings,
            "per_serving": _macros(meal.per_serving),
            "total": _macros(meal.total),
        }
        for meal in nutrition.meals
    ]
    payload["total"] = None if nutrition.total is None else _macros(nutrition.total)
    payload["estimate"] = priced_estimate(
        pairs,
        snapshot.pantry_ingredient_ids,
        budget,
        snapshot.plan_cap_cents,
    )
    return payload


def execute_get_meal(arguments: object) -> dict[str, object]:
    if type(arguments) is not dict or set(arguments) != {"recipe_id"}:
        raise PlanToolError("arguments are invalid")
    recipe_id = arguments["recipe_id"]
    if type(recipe_id) is not str or recipe_id not in SUPPORTED_RECIPE_IDS:
        raise PlanToolError("arguments are invalid")
    request = GroceryRequest(
        meals=[MealRequest(recipe_id=recipe_id, servings=1)],
        budget_period=_NO_PERIOD,
    )
    nutrition = meal_nutrition(request)
    if not nutrition.meals:
        raise PlanToolError("meal is unavailable")
    return {
        "recipe_id": recipe_id,
        "ingredients": [
            {
                "ingredient_id": ingredient_id,
                "name": INGREDIENTS[ingredient_id].name,
                "quantity": quantity,
                "unit": INGREDIENTS[ingredient_id].unit,
            }
            for ingredient_id, quantity in RECIPES[recipe_id].ingredients
        ],
        "per_serving": _macros(nutrition.meals[0].per_serving),
        "diets": list(MEAL_DIETS[recipe_id]),
        "tags": list(MEAL_TAGS[recipe_id]),
    }
