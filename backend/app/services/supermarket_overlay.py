"""Sum Spoonacular ingredient estimates. The overlay MUST NOT change planner totals."""

from collections.abc import Mapping
from typing import Protocol

from app.domain.spoonacular_catalog import SPOONACULAR_IDS
from app.domain.supermarket_estimate import (
    SPOONACULAR_COST_NOTICE,
    SupermarketEstimate,
)
from app.providers.spoonacular import SpoonacularUnavailable
from app.services.grocery_planner import PlanEstimate

_UNIT_MAP: dict[str, str] = {"g": "g", "each": "piece"}


class IngredientCostEstimator(Protocol):
    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None: ...


def _incomplete() -> SupermarketEstimate:
    return SupermarketEstimate(None, SPOONACULAR_COST_NOTICE)


def _spoonacular_id(raw: object) -> int | None:
    if type(raw) is not int or raw <= 0:
        return None
    return raw


def estimate_supermarket_cost(
    plan: PlanEstimate,
    estimator: IngredientCostEstimator,
    ids: Mapping[str, int] = SPOONACULAR_IDS,
) -> SupermarketEstimate:
    total_cents = 0
    has_purchase = False
    for line in plan.lines:
        if line.from_pantry:
            continue
        has_purchase = True
        mapped_unit = _UNIT_MAP.get(line.unit)
        if mapped_unit is None:
            return _incomplete()
        spoonacular_id = _spoonacular_id(ids.get(line.ingredient_id))
        if spoonacular_id is None:
            return _incomplete()
        try:
            cents = estimator.estimate_ingredient_cents(
                spoonacular_id, line.quantity, mapped_unit
            )
        except SpoonacularUnavailable:
            return _incomplete()
        if cents is None:
            return _incomplete()
        total_cents += cents
    if not has_purchase:
        return SupermarketEstimate(0, SPOONACULAR_COST_NOTICE)
    return SupermarketEstimate(total_cents, SPOONACULAR_COST_NOTICE)
