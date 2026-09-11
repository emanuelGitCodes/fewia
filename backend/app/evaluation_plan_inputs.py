from collections.abc import Mapping

from app.domain.catalog import Ingredient
from app.domain.grocery import GroceryRequest, MealRequest
from app.evaluation_budget_inputs import fixture_budget
from app.services.grocery_planner import PlanEstimate, plan_groceries

MEALS_ERROR = "meals is invalid"


def _meal_requests(value: object) -> list[MealRequest]:
    if type(value) is not list:
        raise TypeError(MEALS_ERROR)
    raw: list[object] = value
    if len(raw) == 0:
        raise TypeError(MEALS_ERROR)
    meals: list[MealRequest] = []
    for item in raw:
        meals.append(MealRequest.model_validate(item))
    return meals


def fixture_plan(
    inputs: dict[str, object],
    *,
    ingredients: Mapping[str, Ingredient] | None = None,
) -> PlanEstimate:
    budget = fixture_budget(inputs)
    request = GroceryRequest.model_validate(
        {
            "meals": _meal_requests(inputs.get("meals")),
            "diet": inputs.get("diet", "omnivore"),
            "pantry_ingredients": inputs.get("pantry_ingredients", []),
            "ingredient_exclusions": inputs.get("ingredient_exclusions", []),
            "budget_period": inputs.get("budget_period"),
            "plan_cap_cents": inputs.get("plan_cap_cents"),
        }
    )
    if ingredients is None:
        return plan_groceries(request, budget)
    return plan_groceries(request, budget, ingredients=ingredients)
