"""Sum Spoonacular ingredient estimates. The overlay MUST NOT change planner totals."""

from collections.abc import Mapping
from typing import Protocol

from app.domain.spoonacular_catalog import SPOONACULAR_IDS
from app.domain.supermarket_estimate import (
    SPOONACULAR_COST_NOTICE,
    SupermarketEstimate,
    SupermarketLine,
)
from app.providers.spoonacular import SpoonacularUnavailable
from app.services.grocery_planner import PlanEstimate, ShoppingLine

_UNIT_MAP: dict[str, str] = {"g": "g", "each": "piece"}


class IngredientCostEstimator(Protocol):
    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None: ...


def _spoonacular_id(raw: object) -> int | None:
    if type(raw) is not int or raw <= 0:
        return None
    return raw


def _line_cents(
    line: ShoppingLine,
    estimator: IngredientCostEstimator,
    ids: Mapping[str, int],
) -> int | None:
    mapped_unit = _UNIT_MAP.get(line.unit)
    if mapped_unit is None:
        return None
    spoonacular_id = _spoonacular_id(ids.get(line.ingredient_id))
    if spoonacular_id is None:
        return None
    return estimator.estimate_ingredient_cents(
        spoonacular_id, line.quantity, mapped_unit
    )


def estimate_supermarket_cost(
    plan: PlanEstimate,
    estimator: IngredientCostEstimator,
    ids: Mapping[str, int] = SPOONACULAR_IDS,
) -> SupermarketEstimate:
    overlay_lines: list[SupermarketLine] = []
    stopped = False
    total_cents: int | None = 0
    for line in plan.lines:
        if line.from_pantry:
            continue
        cents: int | None = None
        if not stopped:
            try:
                cents = _line_cents(line, estimator, ids)
            except SpoonacularUnavailable:
                stopped = True
        if cents is None:
            total_cents = None
        elif total_cents is not None:
            total_cents += cents
        overlay_lines.append(SupermarketLine(line.ingredient_id, cents))
    if not overlay_lines:
        return SupermarketEstimate(0, SPOONACULAR_COST_NOTICE)
    return SupermarketEstimate(
        total_cents, SPOONACULAR_COST_NOTICE, tuple(overlay_lines)
    )


def _shopping_line(raw: object) -> ShoppingLine | None:
    if not isinstance(raw, dict):
        return None
    ingredient_id = raw.get("ingredient_id")
    unit = raw.get("unit")
    quantity = raw.get("quantity")
    from_pantry = raw.get("from_pantry")
    if (
        type(ingredient_id) is not str
        or type(unit) is not str
        or type(quantity) is not int
        or type(from_pantry) is not bool
    ):
        return None
    return ShoppingLine(
        ingredient_id,
        ingredient_id,
        unit,
        quantity,
        0,
        0,
        from_pantry,
    )


def _plan_from_result(result: dict[str, object]) -> PlanEstimate | None:
    plan = result.get("plan")
    if not isinstance(plan, dict):
        return None
    raw_lines = plan.get("lines")
    if not isinstance(raw_lines, list):
        return None
    lines: list[ShoppingLine] = []
    for raw in raw_lines:
        line = _shopping_line(raw)
        if line is None:
            return None
        lines.append(line)
    return PlanEstimate(tuple(lines), 0, True, (), "", "")


def attach_supermarket_estimate(
    result: dict[str, object],
    estimator: IngredientCostEstimator,
) -> dict[str, object]:
    attached = dict(result)
    plan = _plan_from_result(result)
    if plan is None:
        return attached
    overlay = estimate_supermarket_cost(plan, estimator)
    attached["supermarket_estimate"] = {
        "total_cents": overlay.total_cents,
        "notice": overlay.notice,
        "lines": [
            {"ingredient_id": line.ingredient_id, "cents": line.cents}
            for line in overlay.lines
        ],
    }
    return attached
