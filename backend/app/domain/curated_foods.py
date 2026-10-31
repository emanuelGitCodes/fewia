"""Versioned curated foods outside the recipe catalog, then bundled USDA foods.

Neither carries a price yet."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.domain.catalog import INGREDIENTS, Ingredient
from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import NUTRITION
from app.domain.usda_foods import (
    USDA_FOODS,
    USDA_INGREDIENTS,
    USDA_NUTRITION,
    load_defaults,
)

_FOOD_KEYS = {
    "id",
    "name",
    "synonyms",
    "fdc_id",
    "fdc_description",
    "per_100g",
    "vegetarian",
    "vegan",
    "package_grams",
}
_PER_100G_KEYS = {
    "energy_kcal",
    "protein_mg",
    "fat_mg",
    "carbohydrate_mg",
    "sodium_mg",
}


@dataclass(frozen=True)
class _Food:
    ingredient: Ingredient
    facts: NutritionFacts
    synonyms: tuple[str, ...]


def _fail(message: str) -> ValueError:
    return ValueError(f"curated foods are invalid: {message}")


def _int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise _fail("numbers must be non-negative integers")
    return value


def _parse_food(record: object) -> _Food:
    if not isinstance(record, dict) or set(record) != _FOOD_KEYS:
        raise _fail("food has unexpected fields")
    food = cast(dict[str, object], record)
    food_id, name, synonyms = food["id"], food["name"], food["synonyms"]
    per_100g, vegetarian, vegan = food["per_100g"], food["vegetarian"], food["vegan"]
    if type(food_id) is not str or type(name) is not str or not food_id or not name:
        raise _fail("id and name must be non-empty strings")
    if not isinstance(synonyms, list) or not all(
        type(item) is str and item and item == item.lower() for item in synonyms
    ):
        raise _fail("synonyms must be lowercase strings")
    if not isinstance(per_100g, dict) or set(per_100g) != _PER_100G_KEYS:
        raise _fail("per_100g has unexpected fields")
    if type(vegetarian) is not bool or type(vegan) is not bool:
        raise _fail("diet flags must be booleans")
    package, fdc_id = _int(food["package_grams"]), _int(food["fdc_id"])
    if package == 0 or fdc_id == 0 or type(food["fdc_description"]) is not str:
        raise _fail("package_grams and fdc_id must be positive")
    amounts = {key: _int(value) for key, value in per_100g.items()}
    return _Food(
        Ingredient(food_id, name, "g", package, None, vegetarian, vegan, False),
        NutritionFacts(fdc_id, **amounts),
        tuple(synonyms),
    )


def _load() -> tuple[str, list[_Food]]:
    path = Path(__file__).with_name("curated_foods.json")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _fail(f"could not load {path}") from error
    if not isinstance(payload, dict) or set(payload) != {"version", "foods"}:
        raise _fail("file has unexpected fields")
    version, records = payload["version"], payload["foods"]
    if type(version) is not str or not isinstance(records, list):
        raise _fail("version or foods are invalid")
    foods = [_parse_food(record) for record in records]
    ids = [food.ingredient.id for food in foods]
    if len(set(ids)) != len(ids) or set(ids) & set(INGREDIENTS):
        raise _fail("ids must be unique and not in the catalog")
    return version, foods


CURATED_FOODS_VERSION, _FOODS = _load()
CURATED_INGREDIENTS = {food.ingredient.id: food.ingredient for food in _FOODS}
CURATED_NUTRITION = {food.ingredient.id: food.facts for food in _FOODS}
CURATED_SYNONYMS = {food.ingredient.id: food.synonyms for food in _FOODS}
ALL_INGREDIENTS: dict[str, Ingredient] = {
    **INGREDIENTS,
    **CURATED_INGREDIENTS,
    **USDA_INGREDIENTS,
}
ALL_NUTRITION: dict[str, NutritionFacts] = {
    **NUTRITION,
    **CURATED_NUTRITION,
    **USDA_NUTRITION,
}
# Terms a USDA default must not shadow: catalog and curated IDs, names, synonyms.
_NAMED = {**INGREDIENTS, **CURATED_INGREDIENTS}
FOOD_TERMS = frozenset(
    {
        *_NAMED,
        *(item.name.lower() for item in _NAMED.values()),
        *(term for terms in CURATED_SYNONYMS.values() for term in terms),
    }
)
_BUNDLED_IDS = {food.facts.fdc_id for food in USDA_FOODS}
USDA_DEFAULTS = load_defaults(FOOD_TERMS, _BUNDLED_IDS or None)
