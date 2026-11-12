"""Match a saved plan's grocery lines to Kroger products. Nothing is stored.

Searches run on one thread pool that all requests share.
"""

import re
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait

from pydantic import BaseModel

from app.domain.catalog import RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS
from app.domain.plan_revision import PlanSnapshot
from app.providers.kroger import KrogerClient, KrogerProduct, Source
from app.services.kroger_overlay import kroger_search_term

MAX_LINES = 30
MAX_QUANTITY = 10
OUT_OF_STOCK = "TEMPORARILY_OUT_OF_STOCK"
PREVIEW_WORKERS = 3
_UPC = re.compile(r"[0-9]{8,14}")
_POOL = ThreadPoolExecutor(
    max_workers=PREVIEW_WORKERS, thread_name_prefix="kroger-preview"
)


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
    source: Source


def grocery_ingredient_ids(snapshot: PlanSnapshot) -> list[str]:
    """Return the plan's distinct ingredients, pantry excluded, in id order."""
    needed = {
        ingredient_id
        for meal in snapshot.meals
        for ingredient_id, _ in RECIPES[meal.recipe_id].ingredients
    }
    return sorted(needed - set(snapshot.pantry_ingredient_ids))[:MAX_LINES]


def _search_all(
    client: KrogerClient, location_id: str, terms: list[str]
) -> dict[str, list[KrogerProduct]]:
    """Search each distinct term on the shared pool, submitted in the given order.

    On a failure, cancel the searches that have not started and wait for the
    running ones. Raise the failure of the earliest term.
    """
    futures = {
        term: _POOL.submit(client.search_products, term, location_id, limit=5)
        for term in terms
    }
    try:
        wait(futures.values(), return_when=FIRST_EXCEPTION)
    finally:
        for future in futures.values():
            future.cancel()
        wait(futures.values())
    for future in futures.values():
        if not future.cancelled():
            error = future.exception()
            if error is not None:
                raise error
    return {term: future.result().products for term, future in futures.items()}


def build_preview(
    snapshot: PlanSnapshot, client: KrogerClient, location_id: str
) -> CartPreview:
    """Search Kroger once per distinct term, on a shared thread pool.

    A search failure propagates with no partial result. Lines that match the
    same UPC merge into the first line's item.
    """
    ingredient_ids = grocery_ingredient_ids(snapshot)
    line_terms = {i: kroger_search_term(i) for i in ingredient_ids}
    distinct = list(dict.fromkeys(t for t in line_terms.values() if t is not None))
    results = _search_all(client, location_id, distinct)
    items: list[PreviewItem] = []
    by_upc: dict[str, PreviewItem] = {}
    unmatched: list[UnmatchedLine] = []
    for ingredient_id in ingredient_ids:
        name = ALL_INGREDIENTS[ingredient_id].name
        term = line_terms[ingredient_id]
        found = results[term] if term is not None else []
        product = next(
            (
                p
                for p in found
                if p.upc and _UPC.fullmatch(p.upc) and p.stock_level != OUT_OF_STOCK
            ),
            None,
        )
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
    return CartPreview(items=items, unmatched=unmatched, source=client.source)
