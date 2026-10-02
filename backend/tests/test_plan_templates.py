"""Tests for deterministic reusable meal template suggestions."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime

import pytest

from app.domain.budget import BudgetResult
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest
from app.services.grocery_planner import PlanningError, plan_groceries
from app.services.plan_templates import (
    MealTemplateSuggestion,
    _suggest_templates_cached,
    suggest_templates,
)

PERIOD = date(2026, 9, 1)
TWO_SERVING_TOTALS = (2898, 2917, 3338, 1821, 2231, 748)
TWO_SERVING_IDS = (
    "bean_lentil_oats",
    "curry_stir_fry_baked_potato",
    "chicken_bowl_tacos_burritos",
    "pasta_lentil_soup",
    "bean_tacos_baked_potato",
    "overnight_oats",
)
TWO_SERVING_RECIPES = (
    ("bean_tacos", "lentil_soup", "overnight_oats"),
    ("chickpea_curry", "vegetable_stir_fry", "baked_potatoes_with_beans"),
    ("chicken_and_rice_bowls", "chicken_tacos", "breakfast_burritos"),
    ("vegetable_pasta", "lentil_soup"),
    ("bean_tacos", "baked_potatoes_with_beans"),
    ("overnight_oats",),
)


@pytest.fixture(autouse=True)
def clear_template_cache() -> None:
    _suggest_templates_cached.cache_clear()


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 50_000, False, ())


def test_two_serving_presets_match_stable_order_cents_and_fields() -> None:
    suggestions = suggest_templates(PERIOD, budget(10_000), servings=2)

    assert len(suggestions) == 6
    assert tuple(item.template_id for item in suggestions) == TWO_SERVING_IDS
    assert tuple(item.recipe_ids for item in suggestions) == TWO_SERVING_RECIPES
    assert tuple(item.total_cents for item in suggestions) == TWO_SERVING_TOTALS
    assert {field.name for field in fields(MealTemplateSuggestion)} == {
        "template_id",
        "recipe_ids",
        "servings",
        "total_cents",
        "catalog_version",
        "notice",
    }
    for item in suggestions:
        assert item.servings == 2
        assert type(item.total_cents) is int
        assert item.catalog_version == CATALOG_VERSION
        assert item.notice == SAMPLE_ESTIMATE_NOTICE


@pytest.mark.parametrize(
    ("available_cents", "expected_ids"),
    [
        (3000, TWO_SERVING_IDS[:2] + TWO_SERVING_IDS[3:]),
        (4000, TWO_SERVING_IDS),
        (5000, TWO_SERVING_IDS),
        (0, ()),
    ],
)
def test_budget_caps_return_fitting_presets_in_stable_order(
    available_cents: int, expected_ids: tuple[str, ...]
) -> None:
    suggestions = suggest_templates(PERIOD, budget(available_cents), servings=2)

    assert tuple(item.template_id for item in suggestions) == expected_ids
    assert all(item.total_cents <= available_cents for item in suggestions)


@pytest.mark.parametrize("servings", [1, 8])
def test_servings_bounds_are_applied_to_every_suggestion(servings: int) -> None:
    suggestions = suggest_templates(PERIOD, budget(50_000), servings=servings)

    assert suggestions
    assert all(item.servings == servings for item in suggestions)
    assert all(type(item.total_cents) is int for item in suggestions)


def test_vegan_and_vegetarian_filter_animal_presets() -> None:
    vegan = suggest_templates(PERIOD, budget(10_000), diet="vegan")
    vegetarian = suggest_templates(PERIOD, budget(10_000), diet="vegetarian")
    plant_ids = TWO_SERVING_IDS[:2] + TWO_SERVING_IDS[3:]

    assert tuple(item.template_id for item in vegan) == plant_ids
    assert tuple(item.template_id for item in vegetarian) == plant_ids
    assert "chicken_bowl_tacos_burritos" not in plant_ids


def test_exclusion_filters_presets_and_keeps_precedence_over_pantry() -> None:
    excluded = suggest_templates(
        PERIOD,
        budget(10_000),
        pantry_ingredients=("salsa",),
        ingredient_exclusions=("salsa",),
    )
    remaining = tuple(item.template_id for item in excluded)

    assert "pasta_lentil_soup" in remaining
    assert "overnight_oats" in remaining
    assert "bean_lentil_oats" not in remaining
    assert "curry_stir_fry_baked_potato" not in remaining
    assert "chicken_bowl_tacos_burritos" not in remaining
    assert "bean_tacos_baked_potato" not in remaining


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("pantry_ingredients", "unknown pantry ingredient id"),
        ("ingredient_exclusions", "unknown exclusion ingredient id"),
    ],
)
def test_unknown_control_ids_fail_even_when_unused(field: str, message: str) -> None:
    unknown_id = "not_in_catalog"
    with pytest.raises(PlanningError, match=message) as error:
        suggest_templates(PERIOD, budget(), **{field: (unknown_id,)})
    assert str(error.value) == message
    assert unknown_id not in str(error.value)


def test_missing_prices_do_not_become_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oats = INGREDIENTS["oats"]
    monkeypatch.setitem(INGREDIENTS, "oats", replace(oats, price_cents=None))

    suggestions = suggest_templates(PERIOD, budget(10_000))
    remaining = tuple(item.template_id for item in suggestions)

    assert "overnight_oats" not in remaining
    assert "bean_lentil_oats" not in remaining
    assert "pasta_lentil_soup" in remaining


@pytest.mark.parametrize(
    "period",
    [date(2026, 9, 2), datetime(2026, 9, 1, tzinfo=UTC), "2026-09-01"],
)
def test_period_must_be_the_first_day_of_the_month(period: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        suggest_templates(period, budget())  # type: ignore[arg-type]


@pytest.mark.parametrize("available", [True, -1, 1.5, "100"])
def test_available_budget_requires_a_nonnegative_integer(available: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        suggest_templates(PERIOD, BudgetResult(available, 0, False, ()))  # type: ignore[arg-type]


def test_budget_must_be_a_budget_result() -> None:
    with pytest.raises(TypeError, match="BudgetResult"):
        suggest_templates(PERIOD, 4000)  # type: ignore[arg-type]


@pytest.mark.parametrize("diet", ["keto", "", "OMNIVORE"])
def test_diet_must_be_supported(diet: object) -> None:
    with pytest.raises(ValueError, match="diet"):
        suggest_templates(PERIOD, budget(), diet=diet)  # type: ignore[arg-type]


@pytest.mark.parametrize("servings", [True, False, 0, 9, -1, 1.5, "2"])
def test_servings_must_be_an_integer_from_one_to_eight(servings: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        suggest_templates(PERIOD, budget(), servings=servings)  # type: ignore[arg-type]


def test_shared_ingredient_package_rounding_matches_combined_plan() -> None:
    suggestions = suggest_templates(PERIOD, budget(10_000), servings=2)
    combined = next(
        item for item in suggestions if item.template_id == "bean_lentil_oats"
    )
    meals = [
        {"recipe_id": "bean_tacos", "servings": 2},
        {"recipe_id": "lentil_soup", "servings": 2},
        {"recipe_id": "overnight_oats", "servings": 2},
    ]
    together = plan_groceries(
        GroceryRequest.model_validate({"meals": meals, "budget_period": PERIOD}),
        budget(10_000),
    )
    separate_total = 0
    for meal in meals:
        single = plan_groceries(
            GroceryRequest.model_validate({"meals": [meal], "budget_period": PERIOD}),
            budget(10_000),
        )
        assert single.total_cents is not None
        separate_total += single.total_cents

    assert together.total_cents == combined.total_cents == 2898
    assert together.total_cents is not None
    assert together.total_cents < separate_total


def test_identical_input_is_a_cache_hit() -> None:
    first = suggest_templates(PERIOD, budget(4000), servings=2)
    after_miss = _suggest_templates_cached.cache_info()
    second = suggest_templates(PERIOD, budget(4000), servings=2)
    after_hit = _suggest_templates_cached.cache_info()
    reordered = suggest_templates(
        PERIOD,
        budget(4000),
        servings=2,
        pantry_ingredients=("onion", "rice"),
    )
    normalized = suggest_templates(
        PERIOD,
        budget(4000),
        servings=2,
        pantry_ingredients=("rice", "onion"),
    )

    assert first is second
    assert after_miss.misses == 1
    assert after_hit.hits == 1
    assert after_hit.misses == 1
    assert reordered is normalized


def test_budget_pantry_servings_and_version_miss_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = suggest_templates(PERIOD, budget(3000), servings=2)
    other_budget = suggest_templates(PERIOD, budget(5000), servings=2)
    other_pantry = suggest_templates(
        PERIOD, budget(3000), servings=2, pantry_ingredients=("olive_oil",)
    )
    other_servings = suggest_templates(PERIOD, budget(3000), servings=1)
    monkeypatch.setattr("app.domain.catalog.CATALOG_VERSION", "sample-prices-v-test")
    other_version = suggest_templates(PERIOD, budget(3000), servings=2)

    assert baseline is not other_budget
    assert baseline is not other_pantry
    assert baseline is not other_servings
    assert baseline is not other_version
    assert len(other_budget) > len(baseline)
    assert other_pantry[0].total_cents < baseline[0].total_cents
    assert other_servings[0].servings == 1
    assert _suggest_templates_cached.cache_info().misses == 5
    assert other_version
    assert all(item.catalog_version == "sample-prices-v-test" for item in other_version)


def test_returned_suggestions_cannot_poison_the_cache() -> None:
    first = suggest_templates(PERIOD, budget(5000), servings=2)
    original_ids = first[0].recipe_ids
    original_total = first[0].total_cents

    with pytest.raises(FrozenInstanceError):
        first[0].total_cents = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        first[0].recipe_ids[0] = "mutated"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        first[0].recipe_ids = ("mutated",)  # type: ignore[misc]
    with pytest.raises(AttributeError):
        first[0].__dict__["notice"] = "mutated"

    cached = suggest_templates(PERIOD, budget(5000), servings=2)
    assert cached is first
    assert cached[0].recipe_ids is original_ids
    assert cached[0].recipe_ids[0] != "mutated"
    assert cached[0].total_cents == original_total
    assert replace(first[0], total_cents=1) is not cached[0]
    assert cached[0].total_cents == original_total
