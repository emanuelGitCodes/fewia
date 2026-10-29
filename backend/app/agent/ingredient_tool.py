from dataclasses import dataclass

from app.agent.plan_tools import _spec
from app.domain.catalog import INGREDIENTS
from app.domain.curated_foods import (
    ALL_INGREDIENTS,
    ALL_NUTRITION,
    CURATED_SYNONYMS,
)
from app.domain.meal_tags import normalize_term

INGREDIENT_TOOL = "get_ingredient_facts"
_MAX_CANDIDATES = 3


class IngredientToolError(ValueError):
    """An invalid lookup with a static message and no raw input."""


def ingredient_tool_spec() -> dict[str, object]:
    return _spec(
        INGREDIENT_TOOL,
        "Look up one food or ingredient by name. Return its ingredient ID, "
        "source, USDA macros per 100 g, diet flags, and sample price in cents "
        "(null when it has none). An unknown or ambiguous name returns "
        "candidates. Use the ID in what_if_substitute and price_lines.",
        {"name": {"type": "string", "minLength": 1, "maxLength": 64}},
        ["name"],
    )


def _facts(ingredient_id: str) -> dict[str, object]:
    ingredient = ALL_INGREDIENTS[ingredient_id]
    nutrition = ALL_NUTRITION[ingredient_id]
    return {
        "status": "found",
        "ingredient_id": ingredient_id,
        "name": ingredient.name,
        "source": "catalog" if ingredient_id in INGREDIENTS else "curated",
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
    )


def _related(query: str) -> list[str]:
    related: list[str] = []
    for item in ALL_INGREDIENTS:
        texts = (ALL_INGREDIENTS[item].name.lower(), *CURATED_SYNONYMS.get(item, ()))
        if any(query in text or text in query for text in texts):
            related.append(item)
    return related[:_MAX_CANDIDATES]


@dataclass(frozen=True)
class FoodResolution:
    """status is found (one ID), ambiguous (matches), or unknown (related)."""

    status: str
    query: str
    ids: tuple[str, ...]


def resolve_food(name: object) -> FoodResolution:
    if type(name) is not str or not 1 <= len(name) <= 64:
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
    return {
        "status": resolution.status,
        "name": resolution.query,
        "candidates": [_facts(item) for item in resolution.ids],
    }
