"""Match a saved plan's grocery lines to Kroger products. Nothing is stored."""

import re

from pydantic import BaseModel

from app.domain.catalog import RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS
from app.domain.plan_revision import PlanSnapshot
from app.providers.kroger import KrogerClient, KrogerProduct
from app.services.kroger_overlay import kroger_search_term

MAX_LINES = 30
MAX_QUANTITY = 10
_UPC = re.compile(r"[0-9]{8,14}")


class PreviewItem(BaseModel):
    ingredient_id: str
    name: str
    upc: str
    description: str
    size: str | None
    quantity: int


class UnmatchedLine(BaseModel):
    ingredient_id: str
    name: str


class CartPreview(BaseModel):
    items: list[PreviewItem]
    unmatched: list[UnmatchedLine]


def grocery_ingredient_ids(snapshot: PlanSnapshot) -> list[str]:
    """Return the plan's distinct ingredients, pantry excluded, in id order."""
    needed = {
        ingredient_id
        for meal in snapshot.meals
        for ingredient_id, _ in RECIPES[meal.recipe_id].ingredients
    }
    return sorted(needed - set(snapshot.pantry_ingredient_ids))[:MAX_LINES]


def build_preview(
    snapshot: PlanSnapshot, client: KrogerClient, location_id: str
) -> CartPreview:
    """Search Kroger once per line. KrogerUnavailable propagates with no partial.

    Lines that match the same UPC merge into the first line's item.
    """
    items: list[PreviewItem] = []
    by_upc: dict[str, PreviewItem] = {}
    unmatched: list[UnmatchedLine] = []
    for ingredient_id in grocery_ingredient_ids(snapshot):
        name = ALL_INGREDIENTS[ingredient_id].name
        term = kroger_search_term(ingredient_id)
        found: list[KrogerProduct] = []
        if term is not None:
            found = client.search_products(term, location_id, limit=5).products
        product = next((p for p in found if p.upc and _UPC.fullmatch(p.upc)), None)
        if product is None or product.upc is None:
            unmatched.append(UnmatchedLine(ingredient_id=ingredient_id, name=name))
            continue
        merged = by_upc.get(product.upc)
        if merged is not None:
            merged.quantity = min(merged.quantity + 1, MAX_QUANTITY)
            continue
        item = PreviewItem(
            ingredient_id=ingredient_id,
            name=name,
            upc=product.upc,
            description=product.description,
            size=product.size,
            quantity=1,
        )
        by_upc[product.upc] = item
        items.append(item)
    return CartPreview(items=items, unmatched=unmatched)
