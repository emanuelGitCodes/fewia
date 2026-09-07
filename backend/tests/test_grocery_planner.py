"""Tests for deterministic grocery planning."""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS, RECIPES, Ingredient, Recipe
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest
from app.services.grocery_planner import (
    PlanEstimate,
    PlanningError,
    ShoppingLine,
    plan_groceries,
)


def request(**overrides: object) -> GroceryRequest:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": date(2026, 9, 1),
    }
    values.update(overrides)
    return GroceryRequest.model_validate(values)


def budget(
    available_cents: int = 10_000, warnings: tuple[str, ...] = ()
) -> BudgetResult:
    return BudgetResult(available_cents, 50_000, False, warnings)


def test_aggregates_shared_ingredients_before_package_rounding() -> None:
    shared = Ingredient("shared", "shared ingredient", "g", 10, 100, True, True)
    custom_ingredients = {"shared": shared}
    custom_recipes = {
        "chicken_tacos": Recipe("chicken_tacos", (("shared", 4),)),
        "bean_tacos": Recipe("bean_tacos", (("shared", 4),)),
    }

    result = plan_groceries(
        request(
            meals=[
                {"recipe_id": "chicken_tacos", "servings": 1},
                {"recipe_id": "bean_tacos", "servings": 1},
            ]
        ),
        budget(),
        ingredients=custom_ingredients,
        recipes=custom_recipes,
    )

    assert result.lines == (
        ShoppingLine("shared", "shared ingredient", "g", 8, 1, 100, False),
    )
    assert result.total_cents == 100


def test_quantity_and_servings_are_preserved() -> None:
    result = plan_groceries(
        request(meals=[{"recipe_id": "chicken_tacos", "servings": 3}]), budget()
    )

    chicken = next(
        line for line in result.lines if line.ingredient_id == "chicken_breast"
    )
    assert chicken.quantity == 300
    assert chicken.packages == 1


def test_explicit_pantry_is_output_and_implicit_pantry_is_purchased() -> None:
    result = plan_groceries(request(pantry_ingredients=["chicken_breast"]), budget())

    chicken = next(
        line for line in result.lines if line.ingredient_id == "chicken_breast"
    )
    oil = next(line for line in result.lines if line.ingredient_id == "olive_oil")
    assert chicken.from_pantry is True
    assert (chicken.packages, chicken.cost_cents) == (0, 0)
    assert oil.from_pantry is False
    assert oil.packages == 1


def test_diet_and_exclusions_apply_before_pantry_removal() -> None:
    with pytest.raises(PlanningError, match="chicken_breast"):
        plan_groceries(
            request(pantry_ingredients=["chicken_breast"], diet="vegan"), budget()
        )
    with pytest.raises(PlanningError, match="salsa"):
        plan_groceries(
            request(pantry_ingredients=["salsa"], ingredient_exclusions=["salsa"]),
            budget(),
        )


@pytest.mark.parametrize("field", ["pantry_ingredients", "ingredient_exclusions"])
def test_unknown_control_ids_fail_even_when_unused(field: str) -> None:
    with pytest.raises(PlanningError, match="unknown"):
        plan_groceries(request(**{field: ["not_in_catalog"]}), budget())


def test_missing_recipe_and_ingredient_fail() -> None:
    with pytest.raises(PlanningError, match="recipe"):
        plan_groceries(request(), budget(), recipes={})
    bad_recipe = Recipe("chicken_tacos", (("not_in_catalog", 1),))
    with pytest.raises(PlanningError, match="ingredient"):
        plan_groceries(request(), budget(), recipes={"chicken_tacos": bad_recipe})


def test_missing_purchase_price_makes_estimate_incomplete() -> None:
    missing = Ingredient("missing", "missing", "g", 100, None, True, True)
    recipe = Recipe("chicken_tacos", (("missing", 50),))

    result = plan_groceries(
        request(),
        budget(),
        ingredients={"missing": missing},
        recipes={"chicken_tacos": recipe},
    )

    assert result.lines[0].cost_cents is None
    assert result.total_cents is None
    assert result.accepted is False
    assert any("missing" in warning for warning in result.warnings)


def test_missing_price_on_pantry_item_does_not_block_complete_estimate() -> None:
    missing = Ingredient("missing", "missing", "g", 100, None, True, True)
    recipe = Recipe("chicken_tacos", (("missing", 50),))

    result = plan_groceries(
        request(pantry_ingredients=["missing"]),
        budget(),
        ingredients={"missing": missing},
        recipes={"chicken_tacos": recipe},
    )

    assert result.total_cents == 0
    assert result.accepted is True
    assert not any("missing" in warning for warning in result.warnings)


def test_zero_budget_keeps_items_and_rejects_estimate() -> None:
    result = plan_groceries(request(), budget(0))

    assert result.lines
    assert result.accepted is False
    assert result.total_cents is not None
    assert any("budget" in warning for warning in result.warnings)


def test_stale_budget_cap_can_accept_and_preserves_warning() -> None:
    stale_budget = BudgetResult(10_000, 400, True, (STALE_SPENDING_WARNING,))

    result = plan_groceries(request(), stale_budget)

    assert result.accepted is True
    assert result.warnings[0] == STALE_SPENDING_WARNING


def test_output_is_stable_and_inputs_are_not_mutated() -> None:
    custom_ingredients = dict(INGREDIENTS)
    custom_recipes = dict(RECIPES)
    grocery_request = request(
        meals=[
            {"recipe_id": "bean_tacos", "servings": 1},
            {"recipe_id": "chicken_tacos", "servings": 1},
        ]
    )
    request_before = grocery_request.model_dump()
    ingredients_before = dict(custom_ingredients)
    recipes_before = dict(custom_recipes)
    first = plan_groceries(
        grocery_request,
        budget(),
        ingredients=custom_ingredients,
        recipes=custom_recipes,
    )
    second = plan_groceries(
        grocery_request,
        budget(),
        ingredients=custom_ingredients,
        recipes=custom_recipes,
    )

    assert first == second
    assert grocery_request.model_dump() == request_before
    assert custom_ingredients == ingredients_before
    assert custom_recipes == recipes_before


def test_estimate_records_are_immutable_and_versioned() -> None:
    result = plan_groceries(request(), budget())

    assert isinstance(result, PlanEstimate)
    assert result.catalog_version == CATALOG_VERSION
    assert result.notice == SAMPLE_ESTIMATE_NOTICE
    with pytest.raises(FrozenInstanceError):
        result.accepted = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.lines[0].quantity = 1  # type: ignore[misc]


@pytest.mark.parametrize("available", [True, -1, 1.5, "100"])
def test_available_budget_requires_a_nonnegative_integer(available: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        plan_groceries(request(), BudgetResult(available, 0, False, ()))  # type: ignore[arg-type]
