from dataclasses import asdict
from typing import cast

from app.agent.estimate import priced_estimate
from app.agent.plan_tools import _spec
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.recipe_variant import (
    CHANGE_FIELDS,
    MAX_QUANTITY,
    MAX_SCALE_PERCENT,
    MIN_QUANTITY,
    MIN_SCALE_PERCENT,
    RecipeChange,
    RecipeVariantError,
    ingredient_grams,
    parse_change,
    round_half_up,
    variant_recipes,
)
from app.services.meal_nutrition import MacroTotals, ingredients_macros

SUBSTITUTE_TOOL = "what_if_substitute"
_MACRO_KEYS = ("energy_kcal", "protein_mg", "carbohydrate_mg", "fat_mg")


class SubstituteToolError(ValueError):
    """A what-if failure with a static message and no raw input."""


def substitute_tool_spec() -> dict[str, object]:
    ingredient = {"type": "string", "enum": sorted(INGREDIENTS)}
    return _spec(
        SUBSTITUTE_TOOL,
        "Recompute one catalog meal with one ingredient replaced or scaled. "
        "Return before, after, and delta macros. The tool does not change the "
        "plan. Use either replace_ingredient_id with with_ingredient_id, or "
        "scale_ingredient_id with scale_factor_percent.",
        {
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
        ["recipe_id", "servings"],
    )


def _macros(totals: MacroTotals) -> dict[str, int]:
    return cast(dict[str, int], asdict(totals))


def _lines(ingredients: tuple[tuple[str, int], ...]) -> list[dict[str, object]]:
    return [
        {
            "ingredient_id": ingredient_id,
            "name": INGREDIENTS[ingredient_id].name,
            "quantity": quantity,
            "unit": INGREDIENTS[ingredient_id].unit,
        }
        for ingredient_id, quantity in ingredients
    ]


def _side(
    ingredients: tuple[tuple[str, int], ...], servings: int
) -> tuple[dict[str, object], MacroTotals, MacroTotals]:
    per_serving = ingredients_macros(ingredients)
    total = ingredients_macros(ingredients, servings=servings)
    if per_serving is None or total is None:
        raise SubstituteToolError("meal is unavailable")
    side: dict[str, object] = {
        "ingredients": _lines(ingredients),
        "per_serving": _macros(per_serving),
        "total": _macros(total),
    }
    return side, per_serving, total


def _delta(after: MacroTotals, before: MacroTotals) -> dict[str, int]:
    return {key: getattr(after, key) - getattr(before, key) for key in _MACRO_KEYS}


def _percent(delta: int, base: int) -> int | None:
    if base == 0:
        return None
    magnitude = (2 * abs(delta) * 100 + base) // (2 * base)
    return -magnitude if delta < 0 else magnitude


def _assumptions(
    recipe_id: str, change: RecipeChange, after: tuple[tuple[str, int], ...]
) -> list[str]:
    before = dict(RECIPES[recipe_id].ingredients)
    now = dict(after)
    if change.scale_ingredient_id is not None:
        target = change.scale_ingredient_id
        percent = cast(int, change.scale_factor_percent)
        if now[target] == round_half_up(before[target] * percent, 100):
            return [f"Scaled to {percent} percent."]
        return [f"Scaled to the minimum of 1 {INGREDIENTS[target].unit} per serving."]
    new = cast(str, change.with_ingredient_id)
    unit = INGREDIENTS[new].unit
    if change.quantity_per_serving is not None:
        return [f"Quantity set to {change.quantity_per_serving} {unit} per serving."]
    old = cast(str, change.replace_ingredient_id)
    old_g = ingredient_grams(old, before[old])
    new_g = ingredient_grams(new, now[new])
    if new_g == old_g:
        return [f"Same weight per serving: {old_g} g."]
    return [
        f"Closest whole amount: {now[new]} {unit} ({new_g} g) per serving "
        f"instead of {old_g} g."
    ]


def _price(
    recipe_id: str,
    servings: int,
    change: RecipeChange,
    budget: BudgetResult,
) -> dict[str, object]:
    meals = [(recipe_id, servings)]
    before = priced_estimate(meals, [], budget)
    after = priced_estimate(
        meals, [], budget, recipes=variant_recipes({recipe_id: change})
    )
    before_total = before["total_cents"]
    after_total = after["total_cents"]
    delta = None
    if isinstance(before_total, int) and isinstance(after_total, int):
        delta = after_total - before_total
    return {"before": before, "after": after, "delta_cents": delta}


def _diets(ingredients: tuple[tuple[str, int], ...]) -> list[str]:
    items = [INGREDIENTS[ingredient_id] for ingredient_id, _ in ingredients]
    diets: list[str] = []
    if all(item.vegan for item in items):
        diets.append("vegan")
    if all(item.vegetarian for item in items):
        diets.append("vegetarian")
    return diets


def execute_substitute(arguments: object, budget: BudgetResult) -> dict[str, object]:
    if type(arguments) is not dict:
        raise SubstituteToolError("arguments are invalid")
    if (
        not {"recipe_id", "servings"}
        <= set(arguments)
        <= {
            "recipe_id",
            "servings",
            *CHANGE_FIELDS,
        }
    ):
        raise SubstituteToolError("arguments are invalid")
    recipe_id = arguments["recipe_id"]
    servings = arguments["servings"]
    if type(recipe_id) is not str or recipe_id not in SUPPORTED_RECIPE_IDS:
        raise SubstituteToolError("arguments are invalid")
    if type(servings) is not int or not 1 <= servings <= 8:
        raise SubstituteToolError("arguments are invalid")
    try:
        change = parse_change(arguments)
        if change is None:
            raise SubstituteToolError("arguments are invalid")
        after_list = variant_recipes({recipe_id: change})[recipe_id].ingredients
    except RecipeVariantError:
        raise SubstituteToolError("arguments are invalid") from None
    before_list = RECIPES[recipe_id].ingredients
    before, before_each, before_total = _side(before_list, servings)
    after, after_each, after_total = _side(after_list, servings)
    per_serving_delta = _delta(after_each, before_each)
    return {
        "recipe_id": recipe_id,
        "servings": servings,
        "change": {
            key: value for key, value in asdict(change).items() if value is not None
        },
        "before": before,
        "after": after,
        "delta": {
            "per_serving": per_serving_delta,
            "total": _delta(after_total, before_total),
        },
        "delta_percent": {
            key: _percent(per_serving_delta[key], getattr(before_each, key))
            for key in _MACRO_KEYS
        },
        "diets_after": _diets(after_list),
        "assumptions": _assumptions(recipe_id, change, after_list),
        "price": _price(recipe_id, servings, change, budget),
    }
