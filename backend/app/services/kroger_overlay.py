"""Attach one live Kroger quote to a chat reply at read time. Nothing is stored."""

from collections.abc import Callable
from datetime import UTC, datetime

from app.domain.curated_foods import ALL_INGREDIENTS, USDA_DEFAULTS
from app.providers.kroger import KrogerClient, KrogerUnavailable

MAX_TERM = 64
_TERMS = {
    "ground_beef_80": "ground beef 80% lean",
    "ground_beef_93": "ground beef 93% lean",
}


def kroger_search_term(ingredient_id: str) -> str | None:
    ingredient = ALL_INGREDIENTS.get(ingredient_id)
    if ingredient is None:
        return None
    term = _TERMS.get(ingredient_id)
    if term is None and ingredient_id.startswith("usda_"):
        names = [
            name
            for name, fdc_id in USDA_DEFAULTS.items()
            if f"usda_{fdc_id}" == ingredient_id
        ]
        if names:
            term = min(names, key=lambda name: (len(name), name))
    if term is None:
        term = ingredient.name.split(" (")[0].strip()
    if not 1 <= len(term) <= MAX_TERM or not term.isprintable():
        return None
    return term


def _target_id(result: dict[str, object]) -> str | None:
    trace = result.get("tool_trace")
    if not isinstance(trace, list):
        return None
    target: str | None = None
    for entry in trace:
        if not isinstance(entry, dict) or entry.get("outcome") != "success":
            continue
        inputs = entry.get("inputs")
        if not isinstance(inputs, dict):
            continue
        tool, status = entry.get("tool"), inputs.get("status")
        key = None
        if tool == "what_if_substitute" and status == "swapped":
            key = "with_ingredient_id"
        elif tool == "get_ingredient_facts" and status == "found":
            key = "ingredient_id"
        value = inputs.get(key) if key is not None else None
        if isinstance(value, str):
            target = value
    return target


def attach_kroger_quote(
    result: dict[str, object],
    client: KrogerClient,
    location_id: str,
    now: Callable[[], datetime],
) -> dict[str, object]:
    ingredient_id = _target_id(result)
    ingredient = ALL_INGREDIENTS.get(ingredient_id) if ingredient_id else None
    if ingredient_id is None or ingredient is None:
        return result
    if ingredient.price_cents is not None:
        return result
    term = kroger_search_term(ingredient_id)
    if term is None:
        return result
    attached = dict(result)
    try:
        search = client.search_products(term, location_id, limit=5)
    except (KrogerUnavailable, ValueError):
        attached["kroger_degraded"] = True
        return attached
    product = next((p for p in search.products if p.regular_cents is not None), None)
    if product is None:
        attached["kroger_quote"] = None
        return attached
    stamp = now().astimezone(UTC).replace(microsecond=0, tzinfo=None)
    attached["kroger_quote"] = {
        "kind": "store_live",
        "ingredient_id": ingredient_id,
        "product_label": product.description,
        "brand": product.brand,
        "size": product.size,
        "regular_cents": product.regular_cents,
        "promo_cents": product.promo_cents,
        "stock_level": product.stock_level,
        "location_id": location_id,
        "retrieved_at": f"{stamp.isoformat()}Z",
    }
    return attached
