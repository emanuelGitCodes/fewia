from dataclasses import dataclass

from app.agent.plan_tools import _spec
from app.domain.catalog import INGREDIENTS
from app.domain.curated_foods import (
    ALL_INGREDIENTS,
    ALL_NUTRITION,
    CURATED_INGREDIENTS,
    CURATED_SYNONYMS,
    USDA_DEFAULTS,
)
from app.domain.meal_tags import normalize_term
from app.domain.usda_foods import USDA_FOODS, USDA_INGREDIENTS, UsdaIndex
from app.providers.usda_live import (
    UsdaLiveClient,
    UsdaUnavailable,
    get_usda_live_client,
)

INGREDIENT_TOOL = "get_ingredient_facts"
_MAX_CANDIDATES = 3
_USDA = UsdaIndex(USDA_FOODS, USDA_DEFAULTS)


class IngredientToolError(ValueError):
    """An invalid lookup with a static message and no raw input."""


def ingredient_tool_spec() -> dict[str, object]:
    return _spec(
        INGREDIENT_TOOL,
        "Look up one food or ingredient by name. Return its ingredient ID, "
        "source, USDA macros per 100 g, diet flags, and sample price in cents "
        "(null when it has none). An unknown or ambiguous name returns "
        "candidates. Use the ID in what_if_substitute and price_lines. "
        "Use it only for a question about one food on its own. To change a "
        "food in a meal, call what_if_substitute with with_food.",
        {"name": {"type": "string", "minLength": 1, "maxLength": 160}},
        ["name"],
    )


def _facts(ingredient_id: str) -> dict[str, object]:
    ingredient = ALL_INGREDIENTS[ingredient_id]
    nutrition = ALL_NUTRITION[ingredient_id]
    source = "usda"
    if ingredient_id in INGREDIENTS:
        source = "catalog"
    elif ingredient_id in CURATED_INGREDIENTS:
        source = "curated"
    return {
        "status": "found",
        "ingredient_id": ingredient_id,
        "name": ingredient.name,
        "source": source,
        "fdc_id": nutrition.fdc_id,
        "per_100g": {
            "energy_kcal": nutrition.energy_kcal,
            "protein_mg": nutrition.protein_mg,
            "carbohydrate_mg": nutrition.carbohydrate_mg,
            "fat_mg": nutrition.fat_mg,
        },
        "vegetarian": ingredient.vegetarian,
        "vegan": ingredient.vegan,
        "price_cents": ingredient.price_cents,
    }


def _exact(query: str, ids: list[str]) -> list[str]:
    return [item for item in ids if query in (item, ALL_INGREDIENTS[item].name.lower())]


def _resolve(query: str) -> list[str]:
    curated = list(CURATED_SYNONYMS)
    return (
        _exact(query, list(INGREDIENTS))
        or _exact(query, curated)
        or [item for item in curated if query in CURATED_SYNONYMS[item]]
        or ([query] if query in USDA_INGREDIENTS else [])
        or _USDA.lookup(query)
    )


def _related(query: str) -> list[str]:
    """Search catalog, curated, and default terms only, never the USDA rows."""
    related: list[str] = []
    for item in (*INGREDIENTS, *CURATED_INGREDIENTS):
        texts = (ALL_INGREDIENTS[item].name.lower(), *CURATED_SYNONYMS.get(item, ()))
        if any(query in text or text in query for text in texts):
            related.append(item)
    for term in USDA_DEFAULTS:
        found = _USDA.lookup(term)
        if found and (query in term or term in query) and found[0] not in related:
            related.append(found[0])
    return related[:_MAX_CANDIDATES]


@dataclass(frozen=True)
class FoodResolution:
    """status is found (one ID), ambiguous (matches), or unknown (related)."""

    status: str
    query: str
    ids: tuple[str, ...]


def resolve_food(name: object) -> FoodResolution:
    if type(name) is not str or not 1 <= len(name) <= 160:
        raise IngredientToolError("arguments are invalid")
    query = normalize_term(name)
    if not query:
        raise IngredientToolError("arguments are invalid")
    matches = _resolve(query)
    if len(matches) == 1:
        return FoodResolution("found", query, (matches[0],))
    if matches:
        return FoodResolution("ambiguous", query, tuple(matches[:_MAX_CANDIDATES]))
    return FoodResolution("unknown", query, tuple(_related(query)))


def execute_ingredient_facts(arguments: object) -> dict[str, object]:
    if type(arguments) is not dict or set(arguments) != {"name"}:
        raise IngredientToolError("arguments are invalid")
    resolution = resolve_food(arguments["name"])
    if resolution.status == "found":
        return _facts(resolution.ids[0])
    payload: dict[str, object] = {
        "status": resolution.status,
        "name": resolution.query,
        "candidates": [_facts(item) for item in resolution.ids],
    }
    if resolution.status == "unknown":
        live = _live_foods(resolution.query)
        if live:
            payload["status"] = "live"
            payload["live"] = live
    return payload


def _live_client() -> UsdaLiveClient | None:
    return get_usda_live_client()


def _live_foods(query: str) -> list[dict[str, object]]:
    client = _live_client()
    if client is None:
        return []
    try:
        foods = client.search(query)
    except (UsdaUnavailable, ValueError):
        return []
    return [
        {
            "fdc_id": food.fdc_id,
            "name": food.name,
            "brand": food.brand,
            "data_type": food.data_type,
            "per_100g": {
                "energy_kcal": food.facts.energy_kcal,
                "protein_mg": food.facts.protein_mg,
                "carbohydrate_mg": food.facts.carbohydrate_mg,
                "fat_mg": food.facts.fat_mg,
            },
        }
        for food in foods[:_MAX_CANDIDATES]
    ]
