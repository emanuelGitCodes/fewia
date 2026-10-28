from typing import cast

from app.domain.catalog import RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.meal_tags import (
    CARNIVORE_NOTE,
    KETO_NOTE,
    MEAL_DIETS,
    MEAL_TAGS,
    SEARCH_TERMS,
    TAG_ORDER,
    normalize_term,
    resolve_ingredient,
    resolve_meal_term,
)

TOOL_NAME = "find_catalog_meals"
_DIETS = ("omnivore", "vegetarian", "vegan")
DISCOVERY_ERROR = (
    "I cannot find meals from those inputs. "
    "Name a catalog meal type, diet, and exact ingredients to exclude."
)
_SAFETY = (
    "High protein means 30 g or more protein per serving. "
    "Lower carb means 30 g or less carbohydrate per serving. "
    "Gluten-free ingredients describes the ingredients only. "
    "I cannot claim gluten-free, celiac, allergy, or cross-contact safety."
)


class CatalogToolError(ValueError):
    pass


def catalog_tool_spec() -> dict[str, object]:
    array = {
        "type": "array",
        "maxItems": 22,
        "items": {"type": "string", "minLength": 1, "maxLength": 64},
    }
    return {
        "toolSpec": {
            "name": TOOL_NAME,
            "description": (
                "Find up to three catalog meals. Intersect all terms, diet, and "
                "exact ingredient exclusions. Carry effective user constraints "
                "from the latest message and validated prior request. "
                "Do not infer restriction groups or hidden preferences. "
                "Ask before planning an alternative. Planning still requires "
                "plan_groceries validation. Terms: "
                f"{', '.join((*TAG_ORDER, *_DIETS, *SEARCH_TERMS))}."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "terms": {**array, "minItems": 1, "maxItems": 8},
                        "diet": {"type": "string", "enum": list(_DIETS)},
                        "ingredient_exclusions": array,
                    },
                    "required": ["terms", "diet", "ingredient_exclusions"],
                    "additionalProperties": False,
                }
            },
        }
    }


def _strings(value: object, limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise CatalogToolError("arguments are invalid")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not 1 <= len(item) <= 64:
            raise CatalogToolError("arguments are invalid")
        normalized = normalize_term(item)
        if not normalized:
            raise CatalogToolError("arguments are invalid")
        result.append(normalized)
    return result


def execute_catalog_search(arguments: object) -> dict[str, object]:
    if not isinstance(arguments, dict) or set(arguments) != {
        "terms",
        "diet",
        "ingredient_exclusions",
    }:
        raise CatalogToolError("arguments are invalid")
    terms = _strings(arguments["terms"], 8)
    if not terms:
        raise CatalogToolError("arguments are invalid")
    raw_diet = arguments["diet"]
    if not isinstance(raw_diet, str) or len(raw_diet) > 64:
        raise CatalogToolError("arguments are invalid")
    diet = normalize_term(raw_diet)
    if diet not in _DIETS:
        raise CatalogToolError("arguments are invalid")
    targets: set[str] = set()
    for term in terms:
        target = resolve_meal_term(term)
        if target is None:
            raise CatalogToolError("arguments are invalid")
        targets.add(target)
    exclusions: set[str] = set()
    for term in _strings(arguments["ingredient_exclusions"], 22):
        ingredient = resolve_ingredient(term)
        if ingredient is None:
            raise CatalogToolError("arguments are invalid")
        exclusions.add(ingredient)
    canonical_terms = sorted(targets)
    targets.add(diet)
    ids = [
        rid
        for rid in SUPPORTED_RECIPE_IDS
        if targets <= {"omnivore", *MEAL_DIETS[rid], *MEAL_TAGS[rid]}
        and not exclusions.intersection(item for item, _ in RECIPES[rid].ingredients)
    ][:3]
    return {
        "request": {
            "terms": canonical_terms,
            "diet": diet,
            "ingredient_exclusions": sorted(exclusions),
        },
        "recipe_ids": ids,
    }


def catalog_answer(payload: dict[str, object]) -> str:
    try:
        validated = execute_catalog_search(payload.get("request"))
    except CatalogToolError:
        return DISCOVERY_ERROR
    if payload != validated:
        return DISCOVERY_ERROR
    ids = cast(list[str], validated["recipe_ids"])
    request = cast(dict[str, object], validated["request"])
    terms = cast(list[str], request["terms"])
    notes = []
    if "lower_carb" in terms:
        notes.append(KETO_NOTE if ids else "No meal in this catalog is keto.")
    if "chicken" in terms:
        notes.append(CARNIVORE_NOTE if ids else "No meal is strictly carnivore.")
    names = []
    for rid in ids:
        name = rid.replace("_", " ")
        names.append(name[0].upper() + name[1:])
    lead = (
        f"Catalog choices: {', '.join(names)}. Which one should I plan?"
        if ids
        else (
            "No catalog meals match these constraints. "
            "Change the meal type or restriction."
        )
    )
    return " ".join([lead, *notes, _SAFETY])
