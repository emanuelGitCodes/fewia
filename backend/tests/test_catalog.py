"""Tests for the sample recipe catalog."""

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from app.domain.budget import BudgetResult
from app.domain.catalog import (
    CATALOG_VERSION,
    ESTIMATE_NOTICE,
    INGREDIENTS,
    RECIPES,
    Ingredient,
    Recipe,
    _parse_recipe_record,
)
from app.domain.grocery import (
    SAMPLE_ESTIMATE_NOTICE,
    SUPPORTED_RECIPE_IDS,
    GroceryRequest,
)
from app.services.grocery_planner import PlanningError, plan_groceries

_CATALOG_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "domain" / "catalog.py"
).read_text(encoding="utf-8")

LEGACY_RECIPE_IDS = (
    "chicken_tacos",
    "bean_tacos",
    "vegetable_pasta",
    "chicken_and_rice_bowls",
    "lentil_soup",
    "chickpea_curry",
    "vegetable_stir_fry",
    "baked_potatoes_with_beans",
    "breakfast_burritos",
    "overnight_oats",
)
LEGACY_RECIPE_INGREDIENTS: dict[str, tuple[tuple[str, int], ...]] = {
    "chicken_tacos": (
        ("chicken_breast", 100),
        ("tortillas", 2),
        ("salsa", 40),
        ("onion", 30),
        ("cumin", 1),
        ("olive_oil", 10),
        ("salt", 1),
    ),
    "bean_tacos": (
        ("black_beans", 120),
        ("tortillas", 2),
        ("salsa", 40),
        ("onion", 30),
        ("cumin", 1),
        ("olive_oil", 10),
        ("salt", 1),
    ),
    "vegetable_pasta": (
        ("pasta", 90),
        ("tomato", 80),
        ("mixed_vegetables", 80),
        ("onion", 30),
        ("garlic", 5),
        ("olive_oil", 10),
        ("salt", 1),
    ),
    "chicken_and_rice_bowls": (
        ("chicken_breast", 100),
        ("rice", 75),
        ("mixed_vegetables", 80),
        ("onion", 30),
        ("garlic", 5),
        ("olive_oil", 10),
        ("salt", 1),
    ),
    "lentil_soup": (
        ("lentils", 80),
        ("tomato", 80),
        ("onion", 40),
        ("garlic", 5),
        ("cumin", 1),
        ("olive_oil", 10),
        ("salt", 1),
    ),
    "chickpea_curry": (
        ("chickpeas", 120),
        ("coconut_milk", 80),
        ("rice", 75),
        ("onion", 40),
        ("garlic", 5),
        ("curry_powder", 3),
        ("olive_oil", 10),
        ("salt", 1),
    ),
    "vegetable_stir_fry": (
        ("mixed_vegetables", 150),
        ("rice", 75),
        ("soy_sauce", 15),
        ("garlic", 5),
        ("onion", 30),
        ("olive_oil", 10),
    ),
    "baked_potatoes_with_beans": (
        ("potato", 1),
        ("black_beans", 100),
        ("salsa", 40),
        ("olive_oil", 5),
        ("salt", 1),
    ),
    "breakfast_burritos": (
        ("eggs", 2),
        ("tortillas", 1),
        ("black_beans", 60),
        ("salsa", 30),
        ("onion", 20),
        ("olive_oil", 5),
        ("salt", 1),
    ),
    "overnight_oats": (("oats", 50), ("oat_milk", 180)),
}
LEGACY_ESTIMATE_TOTALS = {
    "chicken_tacos": 2373,
    "bean_tacos": 1703,
    "vegetable_pasta": 1443,
    "chicken_and_rice_bowls": 2113,
    "lentil_soup": 1473,
    "chickpea_curry": 1742,
    "vegetable_stir_fry": 1414,
    "baked_potatoes_with_beans": 1475,
    "breakfast_burritos": 1853,
    "overnight_oats": 748,
}


def _plan_request(
    recipe_id: str, servings: int = 1, **overrides: object
) -> GroceryRequest:
    values: dict[str, object] = {
        "meals": [{"recipe_id": recipe_id, "servings": servings}],
        "budget_period": date(2026, 9, 1),
    }
    values.update(overrides)
    return GroceryRequest.model_validate(values)


def _plan_budget() -> BudgetResult:
    return BudgetResult(100_000, 100_000, False, ())


def test_recipes_match_supported_recipe_ids() -> None:
    assert list(RECIPES) == list(SUPPORTED_RECIPE_IDS)
    assert len(RECIPES) == 40
    assert len(set(RECIPES)) == 40
    for recipe_id, recipe in RECIPES.items():
        assert recipe.id == recipe_id
        assert isinstance(recipe, Recipe)


def test_legacy_ten_recipes_keep_ids_ingredients_servings_and_order() -> None:
    assert tuple(RECIPES)[:10] == LEGACY_RECIPE_IDS
    assert tuple(SUPPORTED_RECIPE_IDS)[:10] == LEGACY_RECIPE_IDS
    for recipe_id, ingredients in LEGACY_RECIPE_INGREDIENTS.items():
        recipe = RECIPES[recipe_id]
        assert recipe.id == recipe_id
        assert recipe.servings == 1
        assert recipe.ingredients == ingredients


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
        ingredient_ids = [
            ingredient_id for ingredient_id, _quantity in recipe.ingredients
        ]
        assert len(ingredient_ids) == len(set(ingredient_ids))
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
    assert CATALOG_VERSION == "sample-prices-v2"
    assert ESTIMATE_NOTICE == SAMPLE_ESTIMATE_NOTICE
    assert "Estimated from the demo price catalog" in ESTIMATE_NOTICE
    assert "not verified" in ESTIMATE_NOTICE


def test_all_recipes_plan_labeled_integer_estimates_for_serving_bounds() -> None:
    budget = _plan_budget()
    for recipe_id in SUPPORTED_RECIPE_IDS:
        for servings in (1, 8):
            result = plan_groceries(_plan_request(recipe_id, servings), budget)
            assert result.accepted is True
            assert type(result.total_cents) is int
            assert result.total_cents >= 0
            assert result.notice == SAMPLE_ESTIMATE_NOTICE
            assert result.catalog_version == CATALOG_VERSION
            assert result.lines
            for line in result.lines:
                ingredient = INGREDIENTS[line.ingredient_id]
                assert line.unit == ingredient.unit
                assert type(line.quantity) is int
                assert line.quantity > 0
                assert type(line.packages) is int
                assert line.packages >= 0
                assert type(line.from_pantry) is bool
                if line.from_pantry:
                    assert line.packages == 0
                    assert line.cost_cents == 0
                    continue
                assert line.packages > 0
                assert type(line.cost_cents) is int
                assert line.cost_cents >= 0


def test_legacy_per_serving_estimate_totals_stay_fixed() -> None:
    budget = _plan_budget()
    for recipe_id, total_cents in LEGACY_ESTIMATE_TOTALS.items():
        result = plan_groceries(_plan_request(recipe_id, 1), budget)
        assert result.total_cents == total_cents


def test_recipe_diet_follows_ingredient_flags() -> None:
    budget = _plan_budget()
    has_chicken = False
    has_vegetarian_only = False
    has_vegan = False
    for recipe in RECIPES.values():
        vegetarian = all(
            INGREDIENTS[ingredient_id].vegetarian
            for ingredient_id, _quantity in recipe.ingredients
        )
        vegan = all(
            INGREDIENTS[ingredient_id].vegan
            for ingredient_id, _quantity in recipe.ingredients
        )
        if not vegetarian:
            has_chicken = True
        elif not vegan:
            has_vegetarian_only = True
        else:
            has_vegan = True
        for diet, allowed in (
            ("omnivore", True),
            ("vegetarian", vegetarian),
            ("vegan", vegan),
        ):
            request = _plan_request(recipe.id, 1, diet=diet)
            if allowed:
                result = plan_groceries(request, budget)
                assert result.total_cents is not None
                continue
            with pytest.raises(PlanningError, match="diet"):
                plan_groceries(request, budget)
    assert has_chicken
    assert has_vegetarian_only
    assert has_vegan


def test_catalog_does_not_claim_live_prices() -> None:
    blob = f"{CATALOG_VERSION}\n{ESTIMATE_NOTICE}\n{_CATALOG_SOURCE}".lower()
    assert "live price" not in blob
    assert "live availability" not in blob
    assert "purchase" not in blob
