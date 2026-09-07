"""Prepare an Instacart development shopping-list payload from a plan."""

import hashlib
import json
from typing import TypeGuard, cast

from app.domain.catalog import INGREDIENTS
from app.services.grocery_planner import PlanEstimate, ShoppingLine

_PAYLOAD_KEYS = frozenset({"expires_in", "line_items", "link_type", "title"})
_LINE_KEYS = frozenset({"line_item_measurements", "name"})
_MEASUREMENT_KEYS = frozenset({"quantity", "unit"})
_UNITS = frozenset({"each", "g"})
_CATALOG_UNITS: dict[str, str] = {
    ingredient.name: ingredient.unit for ingredient in INGREDIENTS.values()
}
_INVALID_LINE = "shopping line is invalid"
_INVALID_PAYLOAD = "payload is not a prepared shopping payload"


class NoShoppingItems(ValueError):
    def __init__(self) -> None:
        super().__init__("shopping list has no items")


def _is_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _validate_payload_shape(payload: dict[str, object]) -> None:
    if set(payload) != _PAYLOAD_KEYS or payload["title"] != "FEWIA grocery plan":
        raise ValueError(_INVALID_PAYLOAD)
    if payload["link_type"] != "shopping_list":
        raise ValueError(_INVALID_PAYLOAD)
    expires_in = payload["expires_in"]
    if not _is_int(expires_in) or expires_in != 7:
        raise ValueError(_INVALID_PAYLOAD)
    line_items = payload["line_items"]
    if not isinstance(line_items, list) or not line_items:
        raise ValueError(_INVALID_PAYLOAD)
    if len(line_items) > len(INGREDIENTS):
        raise ValueError(_INVALID_PAYLOAD)
    seen: set[str] = set()
    for item in line_items:
        if not isinstance(item, dict) or set(item) != _LINE_KEYS:
            raise ValueError(_INVALID_PAYLOAD)
        line = cast(dict[str, object], item)
        name = line["name"]
        measurements = line["line_item_measurements"]
        if type(name) is not str or name not in _CATALOG_UNITS or name in seen:
            raise ValueError(_INVALID_PAYLOAD)
        seen.add(name)
        if not isinstance(measurements, list) or len(measurements) != 1:
            raise ValueError(_INVALID_PAYLOAD)
        value = measurements[0]
        if not isinstance(value, dict) or set(value) != _MEASUREMENT_KEYS:
            raise ValueError(_INVALID_PAYLOAD)
        measurement = cast(dict[str, object], value)
        quantity = measurement["quantity"]
        unit = measurement["unit"]
        if not _is_int(quantity) or quantity <= 0:
            raise ValueError(_INVALID_PAYLOAD)
        if type(unit) is not str or unit not in _UNITS:
            raise ValueError(_INVALID_PAYLOAD)
        if unit != _CATALOG_UNITS[name]:
            raise ValueError(_INVALID_PAYLOAD)


def _validate_line(line: ShoppingLine, seen: set[str]) -> int:
    if not isinstance(line, ShoppingLine) or type(line.ingredient_id) is not str:
        raise ValueError(_INVALID_LINE)
    ingredient_id = line.ingredient_id
    if not ingredient_id:
        raise ValueError(_INVALID_LINE)
    if ingredient_id in seen:
        raise ValueError("ingredient id is duplicated")
    seen.add(ingredient_id)
    ingredient = INGREDIENTS.get(ingredient_id)
    if ingredient is None:
        raise ValueError("ingredient id is unknown")
    if line.name != ingredient.name or line.unit != ingredient.unit:
        raise ValueError("ingredient name or unit does not match the catalog")
    if type(line.from_pantry) is not bool:
        raise ValueError(_INVALID_LINE)
    if not _is_int(line.quantity) or line.quantity <= 0:
        raise ValueError(_INVALID_LINE)
    if not _is_int(line.packages) or not _is_int(line.cost_cents):
        raise ValueError(_INVALID_LINE)
    if line.from_pantry and (line.packages != 0 or line.cost_cents != 0):
        raise ValueError(_INVALID_LINE)
    if not line.from_pantry and (line.packages <= 0 or line.cost_cents < 0):
        raise ValueError(_INVALID_LINE)
    return line.cost_cents


def build_shopping_payload(plan: PlanEstimate) -> dict[str, object]:
    if not isinstance(plan, PlanEstimate):
        raise TypeError("plan MUST be a PlanEstimate")
    if plan.accepted is not True:
        raise ValueError("plan MUST be accepted")
    total = plan.total_cents
    if not _is_int(total) or total < 0:
        raise ValueError("plan total is invalid")
    seen: set[str] = set()
    cost_sum = 0
    purchases: list[ShoppingLine] = []
    for line in plan.lines:
        cost_sum += _validate_line(line, seen)
        if not line.from_pantry:
            purchases.append(line)
    if cost_sum != total:
        raise ValueError("plan total does not match line costs")
    if not purchases:
        raise NoShoppingItems()
    return {
        "title": "FEWIA grocery plan",
        "link_type": "shopping_list",
        "expires_in": 7,
        "line_items": [
            {
                "name": INGREDIENTS[item.ingredient_id].name,
                "line_item_measurements": [
                    {
                        "quantity": item.quantity,
                        "unit": INGREDIENTS[item.ingredient_id].unit,
                    }
                ],
            }
            for item in sorted(purchases, key=lambda item: item.ingredient_id)
        ],
    }


def shopping_payload_hash(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict):
        raise TypeError("payload MUST be a JSON object")
    _validate_payload_shape(payload)
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()
