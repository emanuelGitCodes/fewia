from typing import get_args

from app.agent.catalog_tool import catalog_answer
from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS, Diet

_CHANGE = "Change the recipe or the restriction."
_MISSING_PRICE = "A purchase price is missing, so this estimate is incomplete."
_OVER_BUDGET = "The estimate exceeds the available budget."
_DIET = (
    "Choose no preference, vegetarian, or vegan. "
    "You MAY name a catalog ingredient to exclude."
)
_PANTRY_INGREDIENT = "Name a listed pantry ingredient."
_UNKNOWN_RESTRICTION = (
    "I cannot map the named restrictions to catalog ingredients. "
    "Which catalog ingredients should I exclude?"
)
_QUESTION = (
    "Which meal should I plan, and what servings, restrictions, and pantry items apply?"
)


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    return f"USD {sign}${magnitude // 100}.{magnitude % 100:02d}"


def _vegan_meal_names() -> list[str]:
    names: list[str] = []
    for recipe_id in SUPPORTED_RECIPE_IDS:
        recipe = RECIPES[recipe_id]
        if all(INGREDIENTS[item_id].vegan for item_id, _qty in recipe.ingredients):
            names.append(recipe_id.replace("_", " "))
        if len(names) == 3:
            break
    return names


def _examples_question() -> str:
    names = _vegan_meal_names()
    if not names:
        return _QUESTION
    return f"Examples: {', '.join(names)}. {_QUESTION}"


CLARIFICATION = _examples_question()
TYPE_CLARIFICATION = (
    "I did not search the catalog for that meal type. "
    f"Ask for the meal type again, or name a catalog meal. {_QUESTION}"
)


def _over_budget_line(candidate: dict[str, object]) -> str:
    budget = candidate.get("budget")
    if not isinstance(budget, dict):
        return _OVER_BUDGET
    available = budget.get("available_cents")
    if type(available) is int:
        return f"The estimate exceeds the available budget of {_usd(available)}."
    return _OVER_BUDGET


def _plan_answer(candidate: dict[str, object]) -> str | None:
    plan = candidate.get("plan")
    if not isinstance(plan, dict):
        return None
    total = plan.get("total_cents")
    accepted = plan.get("accepted")
    if accepted is not True and accepted is not False:
        return None
    if total is not None and type(total) is not int:
        return None
    if accepted is True:
        if type(total) is not int:
            return None
        lead = f"The plan is accepted. The estimate total is {_usd(total)}."
    elif type(total) is int:
        lead = (
            f"The plan is over budget. The estimate total is {_usd(total)}. "
            f"{_over_budget_line(candidate)}"
        )
    else:
        lead = _MISSING_PRICE
    parts = [lead, SAMPLE_ESTIMATE_NOTICE]
    budget = candidate.get("budget")
    if isinstance(budget, dict) and budget.get("stale") is True:
        parts.append(STALE_SPENDING_WARNING)
    return " ".join(parts)


def _exclusion_answer(error: dict[str, object]) -> str | None:
    if error.get("error_code") != "exclusion_reject":
        return None
    recipe_id = error.get("recipe_id")
    ingredient_id = error.get("ingredient_id")
    if type(recipe_id) is not str or type(ingredient_id) is not str:
        return None
    recipe = RECIPES.get(recipe_id)
    ingredient = INGREDIENTS.get(ingredient_id)
    if recipe is None or ingredient is None:
        return None
    if not any(item_id == ingredient_id for item_id, _qty in recipe.ingredients):
        return None
    return f"The selected recipe includes {ingredient.name}. {_CHANGE}"


def _diet_conflict_answer(error: dict[str, object]) -> str | None:
    if error.get("error_code") != "diet_conflict":
        return None
    recipe_id = error.get("recipe_id")
    ingredient_id = error.get("ingredient_id")
    diet = error.get("diet")
    if type(recipe_id) is not str or type(ingredient_id) is not str:
        return None
    if type(diet) is not str or diet not in get_args(Diet):
        return None
    recipe = RECIPES.get(recipe_id)
    ingredient = INGREDIENTS.get(ingredient_id)
    if recipe is None or ingredient is None:
        return None
    if not any(item_id == ingredient_id for item_id, _qty in recipe.ingredients):
        return None
    if not (
        (diet == "vegetarian" and not ingredient.vegetarian)
        or (diet == "vegan" and not ingredient.vegan)
    ):
        return None
    name = recipe_id.replace("_", " ")
    verb = "are" if name.endswith("s") else "is"
    return f"{name[:1].upper()}{name[1:]} {verb} not {diet}. {_CHANGE}"


def _unsupported_answer(
    error: dict[str, object], *, meal_type: bool = False
) -> str | None:
    if error.get("error_code") != "unsupported_recipe":
        return None
    if meal_type:
        return f"That recipe is not in the catalog. {TYPE_CLARIFICATION}"
    names = _vegan_meal_names()
    if not names:
        return None
    return f"That recipe is not in the catalog. {CLARIFICATION}"


def _input_clarification(error: dict[str, object]) -> str | None:
    code = error.get("error_code")
    if code == "unsupported_diet":
        return _DIET
    if code != "unsupported_ingredient":
        return None
    field = error.get("field")
    if field == "pantry_ingredients":
        return _PANTRY_INGREDIENT
    if field == "ingredient_exclusions":
        return _UNKNOWN_RESTRICTION
    return None


def render_public_answer(
    candidate: dict[str, object] | None,
    tool_error: dict[str, object] | None = None,
    discovery: dict[str, object] | None = None,
    *,
    meal_type: bool = False,
) -> str:
    if candidate is not None:
        planned = _plan_answer(candidate)
        if planned is not None:
            return planned
    if tool_error is not None:
        exclusion = _exclusion_answer(tool_error)
        if exclusion is not None:
            return exclusion
        diet_conflict = _diet_conflict_answer(tool_error)
        if diet_conflict is not None:
            return diet_conflict
        unsupported = _unsupported_answer(tool_error, meal_type=meal_type)
        if unsupported is not None:
            return unsupported
        typed = _input_clarification(tool_error)
        if typed is not None:
            return typed
    if discovery is not None and tool_error is None:
        return catalog_answer(discovery)
    return TYPE_CLARIFICATION if meal_type else CLARIFICATION
