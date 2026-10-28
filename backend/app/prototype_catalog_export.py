"""Export the backend catalog as JSON for the /prototype page.

Run from the repository root:
cd backend && uv run python -m app.prototype_catalog_export \
    --out ../frontend/src/prototype/catalog.generated.json
"""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.catalog import CATALOG_VERSION, INGREDIENTS, RECIPES, Recipe
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.services.meal_nutrition import meal_nutrition


def recipe_name(recipe_id: str) -> str:
    text = recipe_id.replace("_", " ")
    return text[:1].upper() + text[1:]


def _diets(recipe: Recipe) -> list[str]:
    items = [INGREDIENTS[ingredient_id] for ingredient_id, _ in recipe.ingredients]
    diets: list[str] = []
    if all(item.vegan for item in items):
        diets.append("vegan")
    if all(item.vegetarian for item in items):
        diets.append("vegetarian")
    return diets


HIGH_PROTEIN_G = 30
LOWER_CARB_G = 30
PROTEIN_TAGS = (
    ("chicken", "chicken_breast"),
    ("egg", "eggs"),
    ("beans", "black_beans"),
    ("lentils", "lentils"),
    ("chickpeas", "chickpeas"),
)
# Oats and oat milk count as gluten ingredients.
GLUTEN_INGREDIENT_IDS = frozenset({"pasta", "soy_sauce", "oats", "oat_milk"})


def _tags(recipe: Recipe, nutrition: dict[str, Any]) -> list[str]:
    ids = {ingredient_id for ingredient_id, _ in recipe.ingredients}
    tags = [tag for tag, ingredient_id in PROTEIN_TAGS if ingredient_id in ids]
    if nutrition["proteinG"] >= HIGH_PROTEIN_G:
        tags.append("high_protein")
    if nutrition["carbsG"] <= LOWER_CARB_G:
        tags.append("lower_carb")
    if not ids & GLUTEN_INGREDIENT_IDS:
        tags.append("gluten_free_ingredients")
    return tags


def _recipe_entry(recipe_id: str) -> dict[str, Any]:
    recipe = RECIPES[recipe_id]
    nutrition = _nutrition(recipe_id)
    return {
        "id": recipe_id,
        "name": recipe_name(recipe_id),
        "diets": _diets(recipe),
        "tags": _tags(recipe, nutrition),
        "ingredients": [
            [ingredient_id, quantity] for ingredient_id, quantity in recipe.ingredients
        ],
        "nutrition": nutrition,
    }


def _nutrition(recipe_id: str) -> dict[str, Any]:
    request = GroceryRequest(
        meals=[MealRequest(recipe_id=recipe_id, servings=1)],
        budget_period=date(2026, 1, 1),
    )
    plan = meal_nutrition(request)
    if len(plan.meals) != 1:
        raise ValueError(f"nutrition is unavailable for {recipe_id}")
    per = plan.meals[0].per_serving
    return {
        "energyKcal": per.energy_kcal,
        "proteinG": round(per.protein_mg / 1000, 1),
        "carbsG": round(per.carbohydrate_mg / 1000, 1),
        "fatG": round(per.fat_mg / 1000, 1),
    }


def build_catalog() -> dict[str, Any]:
    return {
        "catalogVersion": CATALOG_VERSION,
        "ingredients": [
            {
                "id": item.id,
                "name": item.name,
                "unit": item.unit,
                "packageQuantity": item.package_quantity,
                "priceCents": item.price_cents,
                "isPantry": item.is_pantry,
            }
            for item in INGREDIENTS.values()
        ],
        "recipes": [_recipe_entry(recipe_id) for recipe_id in SUPPORTED_RECIPE_IDS],
    }


def render_catalog() -> str:
    return json.dumps(build_catalog(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the JSON here, not to stdout")
    args = parser.parse_args(argv)
    text = render_catalog()
    if args.out is None:
        print(text, end="")
        return
    args.out.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
