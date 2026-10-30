from collections.abc import Callable
from dataclasses import asdict
from datetime import date

from app.agent.estimate import priced_estimate
from app.agent.plan_tools import _spec
from app.domain.budget import BudgetResult
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.domain.plan_proposal import (
    INVALID_PROPOSAL_MESSAGE,
    ProposalInvalid,
    apply_operations,
    parse_operations,
)
from app.domain.plan_revision import PlanRevisionInput, PlanSnapshot
from app.services.meal_nutrition import meal_nutrition

PROPOSAL_TOOL = "propose_plan_change"
PROPOSAL_ONCE = "A plan change was already proposed in this reply."
Propose = Callable[[list[dict[str, object]]], str]
_OPERATION: dict[str, object] = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": ["add", "remove", "set_servings", "set_pantry"],
        },
        "recipe_id": {"type": "string", "enum": list(SUPPORTED_RECIPE_IDS)},
        "servings": {"type": "integer", "minimum": 1, "maximum": 8},
        "ingredient_id": {"type": "string"},
        "owned": {"type": "boolean"},
    },
    "required": ["op"],
    "additionalProperties": False,
}


class ProposalToolError(ValueError):
    """A proposal failure with a static message and no raw input."""


def proposal_tool_spec() -> dict[str, object]:
    return _spec(
        PROPOSAL_TOOL,
        "Propose a change to the user's saved plan for the user to apply. "
        "Operations: add (recipe_id, servings), remove (recipe_id), "
        "set_servings (recipe_id, servings), set_pantry (ingredient_id, owned). "
        "The tool never changes the plan and is not for swapping a food.",
        {
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": _OPERATION,
            }
        },
        ["operations"],
    )


def _side(snapshot: PlanSnapshot, budget: BudgetResult) -> dict[str, object]:
    pairs = [(meal.recipe_id, meal.servings) for meal in snapshot.meals]
    meals = [MealRequest(recipe_id=item, servings=count) for item, count in pairs]
    nutrition = meal_nutrition(GroceryRequest(meals=meals, budget_period=date.min))
    return {
        "meals": [{"recipe_id": item, "servings": count} for item, count in pairs],
        "pantry_ingredient_ids": list(snapshot.pantry_ingredient_ids),
        "estimate": priced_estimate(
            pairs, snapshot.pantry_ingredient_ids, budget, snapshot.plan_cap_cents
        ),
        "nutrition": [
            {"recipe_id": meal.recipe_id, "per_serving": asdict(meal.per_serving)}
            for meal in nutrition.meals
        ],
    }


def execute_propose(
    arguments: object,
    budget: BudgetResult,
    plan: PlanRevisionInput,
    propose: Propose,
) -> dict[str, object]:
    if type(arguments) is not dict or set(arguments) != {"operations"}:
        raise ProposalToolError(INVALID_PROPOSAL_MESSAGE)
    try:
        ops = parse_operations(arguments["operations"])
        after = apply_operations(plan.snapshot, ops)
        operations: list[dict[str, object]] = [op.model_dump(mode="json") for op in ops]
        proposal_id = propose(operations)
    except ProposalInvalid:
        raise ProposalToolError(INVALID_PROPOSAL_MESSAGE) from None
    return {
        "status": "proposed",
        "proposal_id": proposal_id,
        "operations": operations,
        "before": _side(plan.snapshot, budget),
        "after": _side(after, budget),
    }
