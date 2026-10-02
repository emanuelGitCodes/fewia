"""Deterministic reusable meal template suggestions from the sample catalog."""

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import cast, get_args

from app.domain import catalog
from app.domain.budget import BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, Diet, GroceryRequest
from app.services.grocery_planner import (
    ExclusionConflict,
    PlanningError,
    plan_groceries,
)

TEMPLATE_PRESETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bean_lentil_oats", ("bean_tacos", "lentil_soup", "overnight_oats")),
    (
        "curry_stir_fry_baked_potato",
        ("chickpea_curry", "vegetable_stir_fry", "baked_potatoes_with_beans"),
    ),
    (
        "chicken_bowl_tacos_burritos",
        ("chicken_and_rice_bowls", "chicken_tacos", "breakfast_burritos"),
    ),
    ("pasta_lentil_soup", ("vegetable_pasta", "lentil_soup")),
    ("bean_tacos_baked_potato", ("bean_tacos", "baked_potatoes_with_beans")),
    ("overnight_oats", ("overnight_oats",)),
)


@dataclass(frozen=True, slots=True)
class MealTemplateSuggestion:
    template_id: str
    recipe_ids: tuple[str, ...]
    servings: int
    total_cents: int
    catalog_version: str
    notice: str


def _normalize_control_ids(ids: object, field_name: str) -> tuple[str, ...]:
    if type(ids) is not tuple:
        raise TypeError(f"{field_name} must be a tuple")
    unique: set[str] = set()
    for ingredient_id in cast(tuple[object, ...], ids):
        if type(ingredient_id) is not str:
            raise TypeError(f"{field_name} ids must be strings")
        if ingredient_id not in catalog.INGREDIENTS:
            raise PlanningError(f"unknown {field_name} ingredient id")
        unique.add(ingredient_id)
    return tuple(sorted(unique))


@lru_cache(maxsize=128)
def _suggest_templates_cached(
    _catalog_version: str,
    period: date,
    servings: int,
    diet: Diet,
    pantry: tuple[str, ...],
    exclusions: tuple[str, ...],
    available_cents: int,
) -> tuple[MealTemplateSuggestion, ...]:
    planner_budget = BudgetResult(available_cents, 0, False, ())
    suggestions: list[MealTemplateSuggestion] = []
    for template_id, recipe_ids in TEMPLATE_PRESETS:
        request = GroceryRequest.model_validate(
            {
                "meals": [
                    {"recipe_id": rid, "servings": servings} for rid in recipe_ids
                ],
                "budget_period": period,
                "pantry_ingredients": list(pantry),
                "ingredient_exclusions": list(exclusions),
                "diet": diet,
            }
        )
        try:
            estimate = plan_groceries(request, planner_budget)
        except ExclusionConflict:
            continue
        except PlanningError as error:
            if str(error).startswith("ingredient conflicts with diet:"):
                continue
            raise
        total_cents = estimate.total_cents
        if not estimate.accepted or type(total_cents) is not int:
            continue
        suggestions.append(
            MealTemplateSuggestion(
                template_id,
                tuple(recipe_ids),
                servings,
                total_cents,
                _catalog_version,
                SAMPLE_ESTIMATE_NOTICE,
            )
        )
    return tuple(suggestions)


def suggest_templates(
    period: date,
    budget: BudgetResult,
    *,
    servings: int = 2,
    diet: Diet = "omnivore",
    pantry_ingredients: tuple[str, ...] = (),
    ingredient_exclusions: tuple[str, ...] = (),
) -> tuple[MealTemplateSuggestion, ...]:
    if type(period) is not date:
        raise TypeError("period must be a date")
    if period.day != 1:
        raise ValueError("period must be the first day of its month")
    if type(servings) is not int:
        raise TypeError("servings must be an integer")
    if servings < 1 or servings > 8:
        raise ValueError("servings must be between 1 and 8")
    if diet not in get_args(Diet):
        raise ValueError("diet is not supported")
    if not isinstance(budget, BudgetResult):
        raise TypeError("budget must be a BudgetResult")
    if type(budget.available_cents) is not int:
        raise TypeError("budget.available_cents must be an integer")
    if budget.available_cents < 0:
        raise ValueError("budget.available_cents must be non-negative")
    return _suggest_templates_cached(
        catalog.CATALOG_VERSION,
        period,
        servings,
        diet,
        _normalize_control_ids(pantry_ingredients, "pantry"),
        _normalize_control_ids(ingredient_exclusions, "exclusion"),
        budget.available_cents,
    )
