"""Versioned sample recipe catalog. Prices are estimates, not live quotes."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS

CATALOG_VERSION = "sample-prices-v2"
ESTIMATE_NOTICE = SAMPLE_ESTIMATE_NOTICE
Unit = Literal["g", "each"]


@dataclass(frozen=True)
class Ingredient:
    """One catalog ingredient.

    price_cents is a sample package estimate or None for an incomplete estimate.
    Callers MUST NOT treat is_pantry as authorization to omit the ingredient.
    """

    id: str
    name: str
    unit: Unit
    package_quantity: int
    price_cents: int | None
    vegetarian: bool
    vegan: bool
    is_pantry: bool = False


@dataclass(frozen=True)
class Recipe:
    """One recipe with quantities per base serving. Base servings MUST equal 1."""

    id: str
    ingredients: tuple[tuple[str, int], ...]
    servings: int = 1

    def __post_init__(self) -> None:
        if type(self.servings) is not int or self.servings != 1:
            raise ValueError("recipe base servings must equal 1")


INGREDIENTS: dict[str, Ingredient] = {
    item.id: item
    for item in (
        Ingredient(
            "chicken_breast",
            "chicken breast",
            "g",
            454,
            799,
            False,
            False,
            False,
        ),
        Ingredient("eggs", "eggs", "each", 12, 349, True, False, False),
        Ingredient("black_beans", "black beans", "g", 425, 129, True, True, False),
        Ingredient("tortillas", "corn tortillas", "each", 8, 299, True, True, False),
        Ingredient("salsa", "salsa", "g", 454, 249, True, True, False),
        Ingredient("rice", "white rice", "g", 907, 199, True, True, False),
        Ingredient("pasta", "dry pasta", "g", 454, 149, True, True, False),
        Ingredient("tomato", "canned tomato", "g", 411, 179, True, True, False),
        Ingredient("onion", "onion", "g", 454, 129, True, True, False),
        Ingredient("garlic", "garlic", "g", 100, 89, True, True, False),
        Ingredient("olive_oil", "olive oil", "g", 500, 599, True, True, True),
        Ingredient("cumin", "ground cumin", "g", 42, 199, True, True, True),
        Ingredient("salt", "salt", "g", 737, 99, True, True, True),
        Ingredient("lentils", "brown lentils", "g", 454, 179, True, True, False),
        Ingredient("chickpeas", "chickpeas", "g", 425, 129, True, True, False),
        Ingredient("coconut_milk", "coconut milk", "g", 400, 249, True, True, False),
        Ingredient("curry_powder", "curry powder", "g", 42, 249, True, True, True),
        Ingredient(
            "mixed_vegetables", "mixed vegetables", "g", 454, 199, True, True, False
        ),
        Ingredient("soy_sauce", "soy sauce", "g", 296, 199, True, True, False),
        Ingredient("potato", "russet potato", "each", 5, 399, True, True, False),
        Ingredient("oats", "rolled oats", "g", 454, 349, True, True, False),
        Ingredient("oat_milk", "oat milk", "g", 946, 399, True, True, False),
    )
}


def _parse_recipe_record(record: object) -> Recipe:
    if not isinstance(record, dict) or not all(isinstance(key, str) for key in record):
        raise ValueError("recipe record must be an object with string keys")
    recipe_record = cast(dict[str, object], record)
    if set(recipe_record) != {"id", "ingredients", "servings"}:
        raise ValueError("recipe record has unexpected fields")
    recipe_id = recipe_record["id"]
    servings = recipe_record["servings"]
    raw_ingredients = recipe_record["ingredients"]
    if type(recipe_id) is not str or not recipe_id:
        raise ValueError("recipe id must be a non-empty string")
    if type(servings) is not int or servings != 1:
        raise ValueError("recipe servings must equal 1")
    if not isinstance(raw_ingredients, list) or not raw_ingredients:
        raise ValueError("recipe ingredients must be a non-empty list")
    ingredients: list[tuple[str, int]] = []
    for raw_ingredient in raw_ingredients:
        if not isinstance(raw_ingredient, list) or len(raw_ingredient) != 2:
            raise ValueError("recipe ingredients must contain id and quantity")
        ingredient_id, quantity = raw_ingredient
        if type(ingredient_id) is not str or type(quantity) is not int:
            raise ValueError("recipe ingredient values have invalid types")
        if quantity <= 0 or ingredient_id not in INGREDIENTS:
            raise ValueError("recipe ingredient is unknown or not positive")
        ingredients.append((ingredient_id, quantity))
    return Recipe(recipe_id, tuple(ingredients), servings)


def _load_recipes() -> dict[str, Recipe]:
    recipe_path = Path(__file__).with_name("catalog_recipes.json")
    try:
        payload: object = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not load recipe catalog: {recipe_path}") from error
    if not isinstance(payload, list):
        raise ValueError("recipe catalog must contain a list")
    recipes = [_parse_recipe_record(record) for record in payload]
    if len({recipe.id for recipe in recipes}) != len(recipes):
        raise ValueError("recipe catalog contains duplicate ids")
    return {recipe.id: recipe for recipe in recipes}


RECIPES = _load_recipes()
if set(RECIPES) != set(SUPPORTED_RECIPE_IDS):
    raise ValueError("RECIPES must match SUPPORTED_RECIPE_IDS")
