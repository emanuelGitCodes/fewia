"""Apply one hypothetical ingredient change to a catalog recipe."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from app.domain.catalog import INGREDIENTS, RECIPES, Recipe
from app.services.meal_nutrition import GRAMS_PER_EACH

MIN_QUANTITY = 1
MAX_QUANTITY = 1000
MIN_SCALE_PERCENT = 10
MAX_SCALE_PERCENT = 400
CHANGE_FIELDS = (
    "replace_ingredient_id",
    "with_ingredient_id",
    "quantity_per_serving",
    "scale_ingredient_id",
    "scale_factor_percent",
)
_INT_FIELDS = ("quantity_per_serving", "scale_factor_percent")


class RecipeVariantError(ValueError):
    """An invalid recipe change."""


@dataclass(frozen=True)
class RecipeChange:
    replace_ingredient_id: str | None = None
    with_ingredient_id: str | None = None
    quantity_per_serving: int | None = None
    scale_ingredient_id: str | None = None
    scale_factor_percent: int | None = None


def parse_change(fields: Mapping[str, object]) -> RecipeChange | None:
    """Return the change in fields, or None when no change key is present."""
    present = [key for key in CHANGE_FIELDS if key in fields]
    if not present:
        return None
    for key in present:
        if type(fields[key]) is not (int if key in _INT_FIELDS else str):
            raise RecipeVariantError("change fields are invalid")
    return RecipeChange(
        replace_ingredient_id=cast("str | None", fields.get("replace_ingredient_id")),
        with_ingredient_id=cast("str | None", fields.get("with_ingredient_id")),
        quantity_per_serving=cast("int | None", fields.get("quantity_per_serving")),
        scale_ingredient_id=cast("str | None", fields.get("scale_ingredient_id")),
        scale_factor_percent=cast("int | None", fields.get("scale_factor_percent")),
    )


def round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def ingredient_grams(ingredient_id: str, quantity: int) -> int:
    if INGREDIENTS[ingredient_id].unit == "g":
        return quantity
    return quantity * GRAMS_PER_EACH[ingredient_id]


def _is_str(value: object) -> bool:
    return value is None or type(value) is str


def _is_int(value: object) -> bool:
    return value is None or type(value) is int


def _validate_form(change: RecipeChange) -> bool:
    """Return True for the substitute form and False for the scale form."""
    if not (
        _is_str(change.replace_ingredient_id)
        and _is_str(change.with_ingredient_id)
        and _is_str(change.scale_ingredient_id)
        and _is_int(change.quantity_per_serving)
        and _is_int(change.scale_factor_percent)
    ):
        raise RecipeVariantError("change fields are invalid")
    substitute = (
        change.replace_ingredient_id is not None
        and change.with_ingredient_id is not None
        and change.scale_ingredient_id is None
        and change.scale_factor_percent is None
    )
    scale = (
        change.scale_ingredient_id is not None
        and change.scale_factor_percent is not None
        and change.replace_ingredient_id is None
        and change.with_ingredient_id is None
        and change.quantity_per_serving is None
    )
    if substitute == scale:
        raise RecipeVariantError("change must be one substitute or one scale")
    return substitute


def apply_change(recipe_id: str, change: RecipeChange) -> tuple[tuple[str, int], ...]:
    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        raise RecipeVariantError("recipe is unknown")
    ingredients = recipe.ingredients
    present = {ingredient_id for ingredient_id, _ in ingredients}
    if not _validate_form(change):
        target = change.scale_ingredient_id
        percent = change.scale_factor_percent
        if target not in present:
            raise RecipeVariantError("ingredient is not in the recipe")
        if percent is None or not MIN_SCALE_PERCENT <= percent <= MAX_SCALE_PERCENT:
            raise RecipeVariantError("scale factor is out of range")
        return tuple(
            (item, max(1, round_half_up(quantity * percent, 100)))
            if item == target
            else (item, quantity)
            for item, quantity in ingredients
        )
    old = change.replace_ingredient_id
    new = change.with_ingredient_id
    explicit = change.quantity_per_serving
    if old not in present:
        raise RecipeVariantError("ingredient is not in the recipe")
    if new not in INGREDIENTS or new in present:
        raise RecipeVariantError("replacement is not allowed")
    assert old is not None and new is not None
    if explicit is not None:
        if not MIN_QUANTITY <= explicit <= MAX_QUANTITY:
            raise RecipeVariantError("quantity is out of range")
        quantity = explicit
    else:
        old_quantity = dict(ingredients)[old]
        grams = ingredient_grams(old, old_quantity)
        if INGREDIENTS[new].unit == "g":
            quantity = grams
        else:
            quantity = max(1, round_half_up(grams, GRAMS_PER_EACH[new]))
    return tuple(
        (new, quantity) if item == old else (item, amount)
        for item, amount in ingredients
    )


def variant_recipes(changes: Mapping[str, RecipeChange]) -> dict[str, Recipe]:
    """Return RECIPES with each changed recipe replaced by its variant."""
    recipes = dict(RECIPES)
    for recipe_id, change in changes.items():
        recipes[recipe_id] = Recipe(recipe_id, apply_change(recipe_id, change))
    return recipes
