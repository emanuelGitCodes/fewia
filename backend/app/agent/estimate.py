from collections.abc import Mapping, Sequence
from datetime import date

from app.domain.budget import BudgetResult
from app.domain.catalog import RECIPES, Recipe
from app.domain.curated_foods import ALL_INGREDIENTS
from app.domain.grocery import GroceryRequest, MealRequest
from app.services.grocery_planner import PlanEstimate, plan_groceries

_NO_PERIOD = date.min


def estimate_payload(estimate: PlanEstimate, available_cents: int) -> dict[str, object]:
    return {
        "lines": [
            {
                "ingredient_id": line.ingredient_id,
                "quantity": line.quantity,
                "unit": line.unit,
                "packages": line.packages,
                "cost_cents": line.cost_cents,
                "from_pantry": line.from_pantry,
            }
            for line in estimate.lines
        ],
        "total_cents": estimate.total_cents,
        "price_complete": estimate.total_cents is not None,
        "available_cents": available_cents,
        "accepted": estimate.accepted,
        "notice": estimate.notice,
    }


def priced_estimate(
    meals: Sequence[tuple[str, int]],
    pantry: Sequence[str],
    budget: BudgetResult,
    plan_cap_cents: int | None = None,
    recipes: Mapping[str, Recipe] = RECIPES,
) -> dict[str, object]:
    """Price meals with plan_groceries; the cap can only lower the budget."""
    available_cents = budget.available_cents
    if plan_cap_cents is not None:
        available_cents = min(available_cents, plan_cap_cents)
    request = GroceryRequest(
        meals=[MealRequest(recipe_id=item, servings=count) for item, count in meals],
        budget_period=_NO_PERIOD,
        plan_cap_cents=plan_cap_cents,
        pantry_ingredients=list(pantry),
    )
    estimate = plan_groceries(
        request,
        BudgetResult(
            available_cents, budget.pending_cents, budget.stale, budget.warnings
        ),
        ingredients=ALL_INGREDIENTS,
        recipes=recipes,
    )
    return estimate_payload(estimate, available_cents)
