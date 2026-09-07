"""Tests for the sample recipe catalog."""

from collections import Counter
from pathlib import Path

import pytest

from app.domain.catalog import (
    CATALOG_VERSION,
    ESTIMATE_NOTICE,
    INGREDIENTS,
    RECIPES,
    Ingredient,
    Recipe,
    _parse_recipe_record,
)
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS

_CATALOG_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "domain" / "catalog.py"
).read_text(encoding="utf-8")


def test_recipes_match_supported_recipe_ids() -> None:
    assert set(RECIPES) == set(SUPPORTED_RECIPE_IDS)
    assert len(RECIPES) == 10
    for recipe_id, recipe in RECIPES.items():
        assert recipe.id == recipe_id
        assert isinstance(recipe, Recipe)


def test_ingredient_keys_match_ids() -> None:
    assert len(INGREDIENTS) == len({item.id for item in INGREDIENTS.values()})
    for ingredient_id, ingredient in INGREDIENTS.items():
        assert ingredient.id == ingredient_id
        assert isinstance(ingredient, Ingredient)


def test_recipe_quantities_are_positive_integers() -> None:
    for recipe in RECIPES.values():
        assert recipe.ingredients
        assert type(recipe.servings) is int
        assert recipe.servings == 1
        for ingredient_id, quantity in recipe.ingredients:
            assert type(quantity) is int
            assert quantity > 0
            assert ingredient_id in INGREDIENTS
            assert INGREDIENTS[ingredient_id].unit in {"g", "each"}


def test_sample_prices_are_integer_cents() -> None:
    for ingredient in INGREDIENTS.values():
        assert type(ingredient.package_quantity) is int
        assert ingredient.package_quantity > 0
        assert ingredient.unit in {"g", "each"}
        assert type(ingredient.price_cents) is int
        assert ingredient.price_cents >= 0


def test_missing_price_constructs_an_incomplete_estimate() -> None:
    ingredient = Ingredient(
        "missing_price",
        "ingredient without a sample price",
        "g",
        100,
        None,
        True,
        True,
    )
    assert ingredient.price_cents is None


def test_pantry_status_is_explicit() -> None:
    assert all(
        type(ingredient.is_pantry) is bool for ingredient in INGREDIENTS.values()
    )
    assert {
        ingredient.id for ingredient in INGREDIENTS.values() if ingredient.is_pantry
    } == {
        "cumin",
        "curry_powder",
        "olive_oil",
        "salt",
    }


@pytest.mark.parametrize(
    "record",
    [
        None,
        {"id": "bad", "servings": 1, "ingredients": []},
        {"id": "bad", "servings": 0, "ingredients": [["salt", 1]]},
        {"id": "bad", "servings": 2, "ingredients": [["salt", 1]]},
        {"id": "bad", "servings": 8, "ingredients": [["salt", 1]]},
        {"id": "bad", "servings": True, "ingredients": [["salt", 1]]},
        {"id": "bad", "servings": 1, "ingredients": [["missing", 1]]},
        {"id": "bad", "servings": 1, "ingredients": [["salt", 0]]},
    ],
)
def test_recipe_loader_rejects_malformed_records(record: object) -> None:
    with pytest.raises(ValueError):
        _parse_recipe_record(record)


def test_vegan_ingredients_are_vegetarian() -> None:
    for ingredient in INGREDIENTS.values():
        if ingredient.vegan:
            assert ingredient.vegetarian is True


def test_chicken_is_not_vegetarian() -> None:
    chicken = INGREDIENTS["chicken_breast"]
    assert chicken.vegetarian is False
    assert chicken.vegan is False


def test_eggs_are_vegetarian_and_not_vegan() -> None:
    eggs = INGREDIENTS["eggs"]
    assert eggs.vegetarian is True
    assert eggs.vegan is False


def test_plant_ingredients_are_vegan() -> None:
    animal_ids = {"chicken_breast", "eggs"}
    for ingredient in INGREDIENTS.values():
        if ingredient.id in animal_ids:
            continue
        assert ingredient.vegan is True
        assert ingredient.vegetarian is True


def test_catalog_shares_ingredients_across_recipes() -> None:
    uses = Counter(
        ingredient_id
        for recipe in RECIPES.values()
        for ingredient_id, _quantity in recipe.ingredients
    )
    assert any(count >= 2 for count in uses.values())


def test_recipe_constructor_rejects_non_base_servings() -> None:
    with pytest.raises(ValueError):
        Recipe("invalid", (("salt", 1),), 2)


def test_estimate_notice_and_version_are_explicit() -> None:
    assert isinstance(CATALOG_VERSION, str)
    assert CATALOG_VERSION
    assert ESTIMATE_NOTICE == SAMPLE_ESTIMATE_NOTICE
    assert "Estimated from the demo price catalog" in ESTIMATE_NOTICE
    assert "not verified" in ESTIMATE_NOTICE


def test_catalog_does_not_claim_live_prices() -> None:
    blob = f"{CATALOG_VERSION}\n{ESTIMATE_NOTICE}\n{_CATALOG_SOURCE}".lower()
    assert "live price" not in blob
    assert "live availability" not in blob
    assert "purchase" not in blob
