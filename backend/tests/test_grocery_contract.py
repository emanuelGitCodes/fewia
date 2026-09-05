"""Tests for the grocery request contract."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.grocery import (
    SAMPLE_ESTIMATE_NOTICE,
    GroceryRequest,
    MealRequest,
)


def request(**overrides: object) -> GroceryRequest:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 4}],
        "budget_period": date(2026, 9, 1),
    }
    values.update(overrides)
    return GroceryRequest.model_validate(values)


def test_request_accepts_supported_bounds_and_defaults() -> None:
    result = request(
        meals=[
            {"recipe_id": "chicken_tacos", "servings": 1},
            {"recipe_id": "overnight_oats", "servings": 8},
        ],
        plan_cap_cents=0,
        diet="vegan",
        pantry_ingredients=["salt"],
        ingredient_exclusions=["peanuts"],
    )

    assert [meal.recipe_id for meal in result.meals] == [
        "chicken_tacos",
        "overnight_oats",
    ]
    assert result.plan_cap_cents == 0
    assert result.diet == "vegan"


@pytest.mark.parametrize("count", [0, 4])
def test_request_limits_meal_count(count: int) -> None:
    meals = [{"recipe_id": "bean_tacos", "servings": 2}] * count

    with pytest.raises(ValidationError):
        request(meals=meals)


@pytest.mark.parametrize("value", [-1, True, 12.5, "100"])
def test_plan_cap_requires_a_nonnegative_strict_integer(value: object) -> None:
    with pytest.raises(ValidationError):
        request(plan_cap_cents=value)


def test_request_rejects_an_unsupported_recipe_id() -> None:
    with pytest.raises(ValidationError):
        request(meals=[{"recipe_id": "fish_and_chips", "servings": 2}])


@pytest.mark.parametrize("value", [0, 9, 2.0, "2", True])
def test_servings_requires_a_strict_integer_between_one_and_eight(
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        request(meals=[{"recipe_id": "bean_tacos", "servings": value}])


def test_request_requires_a_budget_period() -> None:
    with pytest.raises(ValidationError):
        GroceryRequest.model_validate(
            {"meals": [{"recipe_id": "bean_tacos", "servings": 2}]}
        )


def test_request_requires_the_budget_period_to_start_a_month() -> None:
    with pytest.raises(ValidationError):
        request(budget_period=date(2026, 9, 2))


def test_request_rejects_a_client_user_id_and_other_extras() -> None:
    with pytest.raises(ValidationError):
        request(user_id=7)


def test_request_rejects_an_extra_nested_meal_field() -> None:
    with pytest.raises(ValidationError):
        request(meals=[{"recipe_id": "bean_tacos", "servings": 2, "user_id": 7}])


def test_request_rejects_an_unsupported_diet() -> None:
    with pytest.raises(ValidationError):
        request(diet="pescatarian")


def test_meal_request_rejects_non_strict_servings() -> None:
    with pytest.raises(ValidationError):
        MealRequest(recipe_id="bean_tacos", servings=True)


def test_estimate_notice_is_exact() -> None:
    expected = (
        "Estimated from the demo price catalog. Instacart prices, availability, "
        "taxes, delivery fees, and tips are not verified."
    )

    assert SAMPLE_ESTIMATE_NOTICE == expected
