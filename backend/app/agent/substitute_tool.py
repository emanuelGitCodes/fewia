from dataclasses import asdict
from typing import cast

from app.agent.estimate import priced_estimate
from app.agent.ingredient_tool import IngredientToolError, resolve_food
from app.agent.plan_tools import _spec
from app.domain.budget import BudgetResult
from app.domain.catalog import RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS, ALL_NUTRITION
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
    ingredient_grams,
    parse_change,
    protein_ingredient_ids,
    round_half_up,
    variant_recipes,
)
from app.services.meal_nutrition import MacroTotals

SUBSTITUTE_TOOL = "what_if_substitute"
INGREDIENT_ID_HELP = "An ingredient ID from get_ingredient_facts or get_meal."
_ID_FORM_FIELDS = frozenset(
    {"with_ingredient_id", "scale_ingredient_id", "scale_factor_percent"}
)
_MACRO_KEYS = ("energy_kcal", "protein_mg", "carbohydrate_mg", "fat_mg")


class SubstituteToolError(ValueError):
    """A what-if failure with a static message and no raw input."""


def substitute_tool_spec() -> dict[str, object]:
    ingredient = {"type": "string", "description": INGREDIENT_ID_HELP}
    return _spec(
        SUBSTITUTE_TOOL,
        "Recompute one catalog meal with one ingredient replaced or scaled. "
        "Return before, after, and delta macros. The tool does not change the "
        "plan. To swap, give with_food (a food name) or with_ingredient_id. "
        "replace_ingredient_id defaults to the meal's only protein. "
        "To scale, use scale_ingredient_id with scale_factor_percent. "
        "Omit servings for a meal in the user's plan to use the plan's servings.",
        {
            "recipe_id": {"type": "string", "enum": list(SUPPORTED_RECIPE_IDS)},
            "servings": {"type": "integer", "minimum": 1, "maximum": 8},
            "replace_ingredient_id": ingredient,
            "with_food": {"type": "string", "minLength": 1, "maxLength": 64},
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
        ["recipe_id"],
    )


def _macros(totals: MacroTotals) -> dict[str, int]:
    return cast(dict[str, int], asdict(totals))


def _lines(ingredients: tuple[tuple[str, int], ...]) -> list[dict[str, object]]:
    return [
        {
            "ingredient_id": ingredient_id,
            "name": ALL_INGREDIENTS[ingredient_id].name,
            "quantity": quantity,
            "unit": ALL_INGREDIENTS[ingredient_id].unit,
        }
        for ingredient_id, quantity in ingredients
    ]


def _round_macros(sums: tuple[int, int, int, int], servings: int = 1) -> MacroTotals:
    energy, protein, carb, fat = ((value * servings + 50) // 100 for value in sums)
    return MacroTotals(energy, protein, carb, fat)


def _side(
    ingredients: tuple[tuple[str, int], ...], servings: int
) -> tuple[dict[str, object], MacroTotals, MacroTotals]:
    # meal_nutrition.ingredients_macros only knows catalog ingredients, so sum
    # over ALL_NUTRITION here and round once from unrounded sums.
    sums = [0, 0, 0, 0]
    for ingredient_id, quantity in ingredients:
        grams = ingredient_grams(ingredient_id, quantity)
        facts = ALL_NUTRITION[ingredient_id]
        for index, value in enumerate(
            (
                facts.energy_kcal,
                facts.protein_mg,
                facts.carbohydrate_mg,
                facts.fat_mg,
            )
        ):
            sums[index] += value * grams
    unrounded = (sums[0], sums[1], sums[2], sums[3])
    per_serving = _round_macros(unrounded)
    total = _round_macros(unrounded, servings)
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
        unit = ALL_INGREDIENTS[target].unit
        return [f"Scaled to the minimum of 1 {unit} per serving."]
    new = cast(str, change.with_ingredient_id)
    unit = ALL_INGREDIENTS[new].unit
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
    items = [ALL_INGREDIENTS[ingredient_id] for ingredient_id, _ in ingredients]
    diets: list[str] = []
    if all(item.vegan for item in items):
        diets.append("vegan")
    if all(item.vegetarian for item in items):
        diets.append("vegetarian")
    return diets


def resolve_servings(
    raw: dict[object, object], recipe_id: str, plan: PlanRevisionInput | None
) -> tuple[int, str] | None:
    """Return (servings, source), or None when an explicit value is invalid."""
    if "servings" in raw:
        servings = raw["servings"]
        if type(servings) is not int or not 1 <= servings <= 8:
            return None
        return servings, "request"
    if plan is not None:
        for meal in plan.snapshot.meals:
            if meal.recipe_id == recipe_id:
                return meal.servings, "plan"
    return 1, "default"


def servings_assumption(servings: int, source: str) -> str | None:
    if source == "plan":
        return f"Servings from your plan: {servings}."
    if source == "default":
        return "Servings not given; used 1."
    return None


def _question(status: str, recipe_id: str, ids: tuple[str, ...]) -> dict[str, object]:
    return {
        "status": status,
        "recipe_id": recipe_id,
        "candidates": [
            {"ingredient_id": item, "name": ALL_INGREDIENTS[item].name} for item in ids
        ],
    }


def _fill_food(
    arguments: dict[str, object], recipe_id: str
) -> tuple[dict[str, object] | None, dict[str, object]]:
    """Return (question, arguments with the food and protein IDs filled in)."""
    if not _ID_FORM_FIELDS.isdisjoint(arguments):
        raise SubstituteToolError("arguments are invalid")
    present = {item for item, _ in RECIPES[recipe_id].ingredients}
    old = arguments.get("replace_ingredient_id")
    quantity = arguments.get("quantity_per_serving")
    if ("replace_ingredient_id" in arguments and old not in present) or (
        "quantity_per_serving" in arguments
        and (type(quantity) is not int or not MIN_QUANTITY <= quantity <= MAX_QUANTITY)
    ):
        raise SubstituteToolError("arguments are invalid")
    try:
        food = resolve_food(arguments["with_food"])
    except IngredientToolError:
        raise SubstituteToolError("arguments are invalid") from None
    if food.status != "found":
        status = "needs_food_choice" if food.status == "ambiguous" else "unknown_food"
        return _question(status, recipe_id, food.ids), arguments
    filled = {key: value for key, value in arguments.items() if key != "with_food"}
    filled["with_ingredient_id"] = food.ids[0]
    if "replace_ingredient_id" not in filled:
        proteins = protein_ingredient_ids(recipe_id)
        if len(proteins) != 1:
            ids = proteins or tuple(item for item, _ in RECIPES[recipe_id].ingredients)
            return _question("needs_ingredient_choice", recipe_id, ids), filled
        filled["replace_ingredient_id"] = proteins[0]
    return None, filled


def execute_substitute(
    arguments: object, budget: BudgetResult, plan: PlanRevisionInput | None = None
) -> dict[str, object]:
    if type(arguments) is not dict:
        raise SubstituteToolError("arguments are invalid")
    if "recipe_id" not in arguments or not set(arguments) <= {
        "recipe_id",
        "servings",
        "with_food",
        *CHANGE_FIELDS,
    }:
        raise SubstituteToolError("arguments are invalid")
    recipe_id = arguments["recipe_id"]
    if type(recipe_id) is not str or recipe_id not in SUPPORTED_RECIPE_IDS:
        raise SubstituteToolError("arguments are invalid")
    resolved = resolve_servings(arguments, recipe_id, plan)
    if resolved is None:
        raise SubstituteToolError("arguments are invalid")
    servings, source = resolved
    if "with_food" in arguments:
        question, arguments = _fill_food(arguments, recipe_id)
        if question is not None:
            return question
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
    assumptions = _assumptions(recipe_id, change, after_list)
    note = servings_assumption(servings, source)
    if note is not None:
        assumptions.append(note)
    return {
        "status": "swapped",
        "recipe_id": recipe_id,
        "servings": servings,
        "servings_source": source,
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
        "assumptions": assumptions,
        "price": _price(recipe_id, servings, change, budget),
    }
