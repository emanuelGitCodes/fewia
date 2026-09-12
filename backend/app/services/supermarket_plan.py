"""Strict stored grocery plan validation for supermarket estimates."""

import json

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
)

from app.domain.catalog import INGREDIENTS, RECIPES
from app.services.grocery_planner import PlanEstimate, ShoppingLine

_MEAL_LIMIT = 3
_SERVING_LIMIT = 8
_LINE_LIMIT = 22


class StoredPlanLine(BaseModel, extra="forbid"):
    ingredient_id: StrictStr
    name: StrictStr
    unit: StrictStr
    quantity: StrictInt
    packages: StrictInt
    cost_cents: StrictInt | None
    from_pantry: StrictBool


class StoredPlan(BaseModel, extra="forbid"):
    lines: list[StoredPlanLine] = Field(min_length=1, max_length=_LINE_LIMIT)
    total_cents: StrictInt | None
    accepted: StrictBool
    warnings: list[StrictStr]
    catalog_version: StrictStr
    notice: StrictStr


_PLAN_ADAPTER: TypeAdapter[StoredPlan] = TypeAdapter(StoredPlan)


def _max_quantity(ingredient_id: str) -> int:
    peak = max(
        (
            quantity
            for recipe in RECIPES.values()
            for item, quantity in recipe.ingredients
            if item == ingredient_id
        ),
        default=0,
    )
    return peak * _MEAL_LIMIT * _SERVING_LIMIT


def plan_from_result(raw: object) -> PlanEstimate:
    stored: StoredPlan | None = None
    try:
        payload = json.dumps(raw, allow_nan=False)
        stored = _PLAN_ADAPTER.validate_json(payload, strict=True)
    except (TypeError, ValueError, ValidationError):
        stored = None
    if stored is None:
        raise ValueError()
    seen: set[str] = set()
    lines: list[ShoppingLine] = []
    for item in stored.lines:
        ingredient = INGREDIENTS.get(item.ingredient_id)
        if ingredient is None or item.ingredient_id in seen:
            raise ValueError()
        if (
            item.unit != ingredient.unit
            or item.quantity < 1
            or item.quantity > _max_quantity(item.ingredient_id)
        ):
            raise ValueError()
        seen.add(item.ingredient_id)
        lines.append(
            ShoppingLine(
                ingredient.id,
                ingredient.name,
                ingredient.unit,
                item.quantity,
                item.packages,
                item.cost_cents,
                item.from_pantry,
            )
        )
    return PlanEstimate(
        tuple(lines),
        stored.total_cents,
        stored.accepted,
        tuple(stored.warnings),
        stored.catalog_version,
        stored.notice,
    )
