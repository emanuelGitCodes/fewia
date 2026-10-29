from dataclasses import asdict

from app.agent.estimate import priced_estimate
from app.agent.plan_tools import _spec
from app.domain.budget import BudgetResult
from app.agent.substitute_tool import resolve_servings, servings_assumption
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.plan_revision import PlanRevisionInput
from app.domain.recipe_variant import (
    CHANGE_FIELDS,
    MAX_QUANTITY,
    MAX_SCALE_PERCENT,
    MIN_QUANTITY,
    MIN_SCALE_PERCENT,
    RecipeChange,
    RecipeVariantError,
    parse_change,
    variant_recipes,
)

PRICE_TOOL = "price_lines"
_MAX_MEALS = 3
_INVALID = "arguments are invalid"


class PriceToolError(ValueError):
    """A pricing failure with a static message and no raw input."""


def meal_name(recipe_id: object) -> str:
    name = str(recipe_id).replace("_", " ")
    return f"{name[:1].upper()}{name[1:]}"


def price_tool_spec() -> dict[str, object]:
    ingredient = {"type": "string", "description": "A catalog ingredient ID."}
    meal: dict[str, object] = {
        "type": "object",
        "properties": {
            "recipe_id": {"type": "string", "enum": list(SUPPORTED_RECIPE_IDS)},
            "servings": {"type": "integer", "minimum": 1, "maximum": 8},
            "replace_ingredient_id": ingredient,
            "with_ingredient_id": ingredient,
            "quantity_per_serving": {
                "type": "integer",
                "minimum": MIN_QUANTITY,
                "maximum": MAX_QUANTITY,
            },
            "scale_ingredient_id": ingredient,
            "scale_factor_percent": {
                "type": "integer",
                "minimum": MIN_SCALE_PERCENT,
                "maximum": MAX_SCALE_PERCENT,
            },
        },
        "required": ["recipe_id"],
        "additionalProperties": False,
    }
    return _spec(
        PRICE_TOOL,
        "Price one to three catalog meals with sample prices against the "
        "user's budget. Each meal may carry one swap (replace_ingredient_id "
        "with with_ingredient_id) or one portion change (scale_ingredient_id "
        "with scale_factor_percent). Recipe IDs must be unique. The tool does "
        "not change the plan. "
        "Omit servings for a meal in the user's plan to use the plan's servings.",
        {
            "meals": {"type": "array", "minItems": 1, "maxItems": 3, "items": meal},
            "pantry_ingredient_ids": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(INGREDIENTS)},
            },
        },
        ["meals"],
    )


def _parse_meal(
    raw: object, plan: PlanRevisionInput | None
) -> tuple[str, int, str, RecipeChange | None]:
    if (
        type(raw) is not dict
        or "recipe_id" not in raw
        or not set(raw) <= {"recipe_id", "servings"} | set(CHANGE_FIELDS)
    ):
        raise PriceToolError(_INVALID)
    recipe_id = raw["recipe_id"]
    if type(recipe_id) is not str or recipe_id not in SUPPORTED_RECIPE_IDS:
        raise PriceToolError(_INVALID)
    resolved = resolve_servings(raw, recipe_id, plan)
    if resolved is None:
        raise PriceToolError(_INVALID)
    try:
        return recipe_id, resolved[0], resolved[1], parse_change(raw)
    except RecipeVariantError:
        raise PriceToolError(_INVALID) from None


def _pantry(arguments: dict[object, object]) -> list[str]:
    pantry = arguments.get("pantry_ingredient_ids", [])
    if type(pantry) is not list:
        raise PriceToolError(_INVALID)
    for ingredient_id in pantry:
        if type(ingredient_id) is not str or ingredient_id not in INGREDIENTS:
            raise PriceToolError(_INVALID)
    if len(set(pantry)) != len(pantry):
        raise PriceToolError(_INVALID)
    return pantry


def execute_price_lines(
    arguments: object,
    budget: BudgetResult,
    plan_cap_cents: int | None,
    plan: PlanRevisionInput | None = None,
) -> dict[str, object]:
    if (
        type(arguments) is not dict
        or "meals" not in arguments
        or not set(arguments) <= {"meals", "pantry_ingredient_ids"}
    ):
        raise PriceToolError(_INVALID)
    raw_meals = arguments["meals"]
    if type(raw_meals) is not list or not 1 <= len(raw_meals) <= _MAX_MEALS:
        raise PriceToolError(_INVALID)
    parsed = [_parse_meal(raw, plan) for raw in raw_meals]
    if len({recipe_id for recipe_id, _, _, _ in parsed}) != len(parsed):
        raise PriceToolError(_INVALID)
    pantry = _pantry(arguments)
    changes = {
        recipe_id: change for recipe_id, _, _, change in parsed if change is not None
    }
    assumptions = []
    for recipe_id, servings, source, _ in parsed:
        note = servings_assumption(servings, source)
        if note is not None:
            assumptions.append(f"{meal_name(recipe_id)}: {note}")
    try:
        recipes = variant_recipes(changes)
    except RecipeVariantError:
        raise PriceToolError(_INVALID) from None
    return {
        "meals": [
            {
                "recipe_id": recipe_id,
                "servings": servings,
                "servings_source": source,
                "change": None
                if change is None
                else {k: v for k, v in asdict(change).items() if v is not None},
                "ingredients": [
                    {
                        "ingredient_id": ingredient_id,
                        "name": INGREDIENTS[ingredient_id].name,
                        "quantity": quantity,
                        "unit": INGREDIENTS[ingredient_id].unit,
                    }
                    for ingredient_id, quantity in recipes[recipe_id].ingredients
                ],
            }
            for recipe_id, servings, source, change in parsed
        ],
        "assumptions": assumptions,
        "estimate": priced_estimate(
            [(recipe_id, servings) for recipe_id, servings, _, _ in parsed],
            pantry,
            budget,
            plan_cap_cents,
            recipes,
        ),
    }
