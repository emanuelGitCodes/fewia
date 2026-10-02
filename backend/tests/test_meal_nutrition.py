from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict
from datetime import date

import pytest

from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import NUTRITION, NUTRITION_BASIS_G
from app.services.meal_nutrition import (
    GRAMS_PER_EACH,
    NOTICE,
    PORTION_NOTICE,
    MacroTotals,
    MealNutrition,
    MealPlanNutrition,
    meal_nutrition,
)

NOTICE_TEXT = (
    "Estimated nutrition from USDA FoodData Central for the selected "
    "recipe quantities. Pantry ingredients are included."
)
PORTION_TEXT = (
    "Portion estimates: one egg = 50 g, one corn tortilla = 24 g, "
    "one potato = 213 g. Actual sizes and preparation vary."
)


def grocery_request(**overrides: object) -> GroceryRequest:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "overnight_oats", "servings": 1}],
        "budget_period": date(2026, 9, 1),
    }
    values.update(overrides)
    return GroceryRequest.model_validate(values)


def facts(
    *,
    energy_kcal: int = 0,
    protein_mg: int = 0,
    carbohydrate_mg: int = 0,
    fat_mg: int = 0,
) -> NutritionFacts:
    return NutritionFacts(
        fdc_id=1,
        energy_kcal=energy_kcal,
        protein_mg=protein_mg,
        fat_mg=fat_mg,
        carbohydrate_mg=carbohydrate_mg,
        sodium_mg=0,
    )


def zeros_for(*recipe_ids: str) -> dict[str, NutritionFacts]:
    payload: dict[str, NutritionFacts] = {}
    for recipe_id in recipe_ids:
        for ingredient_id, _quantity in RECIPES[recipe_id].ingredients:
            payload[ingredient_id] = facts()
    return payload


def test_notices_match_required_text() -> None:
    assert NOTICE == NOTICE_TEXT
    assert PORTION_NOTICE == PORTION_TEXT
    assert NUTRITION_BASIS_G == 100
    assert GRAMS_PER_EACH == {"eggs": 50, "tortillas": 24, "potato": 213}


def test_hand_calculated_custom_fixture_macros() -> None:
    catalog = zeros_for("overnight_oats")
    catalog["oats"] = facts(
        energy_kcal=200,
        protein_mg=10000,
        carbohydrate_mg=40000,
        fat_mg=5000,
    )
    catalog["oat_milk"] = facts(
        energy_kcal=50,
        protein_mg=1000,
        carbohydrate_mg=8000,
        fat_mg=2000,
    )

    result = meal_nutrition(grocery_request(), facts=catalog)

    expected = MacroTotals(190, 6800, 34400, 6100)
    assert result.notice == NOTICE_TEXT
    assert result.portion_notice == PORTION_TEXT
    assert result.total == expected
    assert result.meals == (MealNutrition("overnight_oats", 1, expected, expected),)
    assert asdict(expected) == {
        "energy_kcal": 190,
        "protein_mg": 6800,
        "carbohydrate_mg": 34400,
        "fat_mg": 6100,
    }


def test_each_portions_use_grams_not_counts() -> None:
    catalog = zeros_for("breakfast_burritos")
    catalog["eggs"] = facts(energy_kcal=10)
    catalog["tortillas"] = facts(energy_kcal=5)
    portions = {"eggs": 50, "tortillas": 24, "potato": 213}

    result = meal_nutrition(
        grocery_request(
            meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
        ),
        facts=catalog,
        grams_per_each=portions,
    )

    assert result.total == MacroTotals(11, 0, 0, 0)
    assert result.meals[0].per_serving == MacroTotals(11, 0, 0, 0)


def test_serving_scaling_uses_unrounded_base() -> None:
    catalog = zeros_for("overnight_oats")
    catalog["oats"] = facts(energy_kcal=1)
    request = grocery_request(
        meals=[{"recipe_id": "overnight_oats", "servings": 3}],
    )

    result = meal_nutrition(request, facts=catalog)

    assert result.meals[0].per_serving == MacroTotals(1, 0, 0, 0)
    assert result.meals[0].total == MacroTotals(2, 0, 0, 0)
    assert result.total == MacroTotals(2, 0, 0, 0)
    assert result.meals[0].total.energy_kcal != (
        result.meals[0].per_serving.energy_kcal * 3
    )


def test_mixed_meals_round_unrounded_plan_sum() -> None:
    catalog = zeros_for("overnight_oats", "vegetable_pasta")
    catalog["oats"] = facts(energy_kcal=1)
    catalog["garlic"] = facts(energy_kcal=10)
    request = grocery_request(
        meals=[
            {"recipe_id": "overnight_oats", "servings": 1},
            {"recipe_id": "vegetable_pasta", "servings": 1},
        ],
    )

    result = meal_nutrition(request, facts=catalog)

    assert result.meals[0].total == MacroTotals(1, 0, 0, 0)
    assert result.meals[1].total == MacroTotals(1, 0, 0, 0)
    assert result.total == MacroTotals(1, 0, 0, 0)
    rounded_row_sum = (
        result.meals[0].total.energy_kcal + result.meals[1].total.energy_kcal
    )
    assert result.total is not None
    assert result.total.energy_kcal != rounded_row_sum


def test_repeated_meal_rows_stay_separate() -> None:
    catalog = zeros_for("overnight_oats")
    catalog["oats"] = facts(energy_kcal=1)
    request = grocery_request(
        meals=[
            {"recipe_id": "overnight_oats", "servings": 1},
            {"recipe_id": "overnight_oats", "servings": 2},
        ],
    )

    result = meal_nutrition(request, facts=catalog)

    assert len(result.meals) == 2
    assert result.meals[0] == MealNutrition(
        "overnight_oats",
        1,
        MacroTotals(1, 0, 0, 0),
        MacroTotals(1, 0, 0, 0),
    )
    assert result.meals[1] == MealNutrition(
        "overnight_oats",
        2,
        MacroTotals(1, 0, 0, 0),
        MacroTotals(1, 0, 0, 0),
    )
    assert result.total == MacroTotals(2, 0, 0, 0)


def test_pantry_list_does_not_subtract_nutrients() -> None:
    catalog = zeros_for("chicken_tacos")
    catalog["olive_oil"] = facts(energy_kcal=884)
    catalog["chicken_breast"] = facts(energy_kcal=120)
    with_pantry = grocery_request(
        meals=[{"recipe_id": "chicken_tacos", "servings": 1}],
        pantry_ingredients=["olive_oil", "chicken_breast", "salt"],
    )
    without_pantry = grocery_request(
        meals=[{"recipe_id": "chicken_tacos", "servings": 1}],
        pantry_ingredients=[],
    )

    included = meal_nutrition(with_pantry, facts=catalog)
    omitted = meal_nutrition(without_pantry, facts=catalog)

    assert included.total == omitted.total
    assert included.meals == omitted.meals
    assert included.total == MacroTotals(208, 0, 0, 0)


def test_all_supported_recipes_are_available() -> None:
    assert len(SUPPORTED_RECIPE_IDS) == 40
    for recipe_id in SUPPORTED_RECIPE_IDS:
        for servings in (1, 8):
            result = meal_nutrition(
                grocery_request(
                    meals=[{"recipe_id": recipe_id, "servings": servings}],
                ),
            )
            assert result.total is not None
            assert result.meals != ()
            assert result.meals[0].recipe_id == recipe_id
            assert result.meals[0].servings == servings
            assert result.notice == NOTICE_TEXT
            assert result.portion_notice == PORTION_TEXT


def test_missing_facts_are_unavailable() -> None:
    catalog = zeros_for("overnight_oats")
    del catalog["oats"]
    pantry_request = grocery_request(pantry_ingredients=["oats"])

    result = meal_nutrition(pantry_request, facts=catalog)

    assert result.total is None
    assert result.meals == ()
    assert result.notice == NOTICE_TEXT
    assert result.portion_notice == PORTION_TEXT


@pytest.mark.parametrize(
    "portions",
    [
        {"tortillas": 24, "potato": 213},
        {"eggs": True, "tortillas": 24, "potato": 213},
        {"eggs": 0, "tortillas": 24, "potato": 213},
        {"eggs": -1, "tortillas": 24, "potato": 213},
        {"eggs": 50.0, "tortillas": 24, "potato": 213},
        {"eggs": "50", "tortillas": 24, "potato": 213},
    ],
)
def test_invalid_or_missing_portions_are_unavailable(
    portions: dict[str, object],
) -> None:
    request = grocery_request(
        meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
    )

    result = meal_nutrition(request, grams_per_each=portions)  # type: ignore[arg-type]

    assert result.total is None
    assert result.meals == ()


def test_unknown_recipe_is_unavailable() -> None:
    request = GroceryRequest.model_construct(
        meals=[
            MealRequest.model_construct(
                recipe_id="unknown_recipe",
                servings=1,
            ),
        ],
        budget_period=date(2026, 9, 1),
        plan_cap_cents=None,
        pantry_ingredients=[],
        ingredient_exclusions=[],
        diet="omnivore",
    )

    result = meal_nutrition(request)

    assert result.total is None
    assert result.meals == ()
    assert result.notice == NOTICE_TEXT


def test_unused_invalid_portions_do_not_block_gram_recipes() -> None:
    catalog = zeros_for("overnight_oats")
    catalog["oats"] = facts(energy_kcal=200)

    result = meal_nutrition(
        grocery_request(),
        facts=catalog,
        grams_per_each={"eggs": True},
    )

    assert result.total == MacroTotals(100, 0, 0, 0)


def test_request_and_catalog_are_not_mutated() -> None:
    request = grocery_request(
        meals=[{"recipe_id": "breakfast_burritos", "servings": 2}],
        pantry_ingredients=["eggs"],
    )
    request_before = request.model_dump()
    nutrition_before = deepcopy(NUTRITION)
    portions_before = dict(GRAMS_PER_EACH)
    ingredients_before = dict(INGREDIENTS)
    recipes_before = dict(RECIPES)

    result = meal_nutrition(request)

    assert result.total is not None
    assert request.model_dump() == request_before
    assert NUTRITION == nutrition_before
    assert GRAMS_PER_EACH == portions_before
    assert INGREDIENTS == ingredients_before
    assert RECIPES == recipes_before


def test_return_types_are_frozen() -> None:
    result = meal_nutrition(grocery_request())
    assert isinstance(result, MealPlanNutrition)
    assert result.total is not None
    with pytest.raises(FrozenInstanceError):
        result.total = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.total.energy_kcal = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.meals[0].servings = 8  # type: ignore[misc]


def test_energy_is_not_derived_from_macro_formula() -> None:
    catalog = zeros_for("overnight_oats")
    catalog["oats"] = facts(
        energy_kcal=1,
        protein_mg=100000,
        carbohydrate_mg=100000,
        fat_mg=100000,
    )

    result = meal_nutrition(grocery_request(), facts=catalog)

    assert result.total == MacroTotals(1, 50000, 50000, 50000)
