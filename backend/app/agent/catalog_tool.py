import re
from datetime import date
from functools import cache
from typing import cast

from app.agent.estimate import priced_estimate
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.domain.meal_tags import (
    CARNIVORE_NOTE,
    KETO_NOTE,
    MEAL_DIETS,
    MEAL_TAGS,
    TAG_ORDER,
    normalize_term,
    resolve_ingredient,
    resolve_meal_term,
)
from app.services.meal_nutrition import meal_nutrition

TOOL_NAME = "search_meals"
_DIETS = ("omnivore", "vegetarian", "vegan")
_UI_ONLY_TERMS = ("meat", "carnivore")
_STOPWORDS = frozenset(
    "a an the and or with for of to me some something meal meals dinner lunch "
    "breakfast recipe recipes idea ideas please want need i my".split()
)
_NEGATIONS = frozenset({"without", "no"})
_ARTICLES = frozenset({"a", "an", "the", "some"})
_KEYS = {"query", "diet", "exclude", "min_protein_g", "max_cents_per_serving", "limit"}
DISCOVERY_ERROR = (
    "I cannot find meals from those inputs. "
    "Name a catalog meal type, diet, and exact ingredients to exclude."
)
_GLUTEN_FREE = "Gluten-free ingredients describes the ingredients only."
_CAVEATS = {
    "high_protein": "High protein means 30 g or more protein per serving.",
    "lower_carb": "Lower carb means 30 g or less carbohydrate per serving.",
    "gluten_free_ingredients": _GLUTEN_FREE,
}
_CANNOT_CLAIM = "I cannot claim gluten-free, celiac, allergy, or cross-contact safety."
_SAFETY = " ".join([*_CAVEATS.values(), _CANNOT_CLAIM])
_FACET_DIETS = ("vegetarian", "vegan")
_NO_MATCH = (
    "No catalog meal matches that search. Try a meal type, an ingredient, or a diet."
)
_UNKNOWN_EXCLUSION = (
    "I could not match an ingredient to exclude, so I did not search. "
    "Name the ingredient another way."
)
_BAD = "arguments are invalid"


class CatalogToolError(ValueError):
    pass


def _number(low: int, high: int) -> dict[str, object]:
    return {"type": "integer", "minimum": low, "maximum": high}


def catalog_tool_spec() -> dict[str, object]:
    return {
        "toolSpec": {
            "name": TOOL_NAME,
            "description": (
                "Search catalog meals by free text, such as a meal, ingredient, "
                "or tag. Returns up to three recipe IDs and the words that "
                "matched nothing. max_cents_per_serving is the sample grocery "
                "cost for one serving, in whole packages. "
                "Put exclusions in exclude, not query. "
                "Not for a meal the user names or has in the plan. "
                "Ask before planning an alternative; plan_groceries validates."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 120},
                        "diet": {"type": "string", "enum": list(_DIETS)},
                        "exclude": {
                            "type": "array",
                            "maxItems": 22,
                            "items": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 64,
                            },
                        },
                        "min_protein_g": _number(0, 200),
                        "max_cents_per_serving": _number(1, 10000),
                        "limit": _number(1, 3),
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                }
            },
        }
    }


def _stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


@cache
def _meal_words(recipe_id: str) -> frozenset[str]:
    names = [recipe_id]
    names.extend(INGREDIENTS[item].name for item, _ in RECIPES[recipe_id].ingredients)
    return frozenset(
        _stem(word) for name in names for word in re.findall(r"[a-z]+", name.lower())
    )


def _parse(query: str) -> tuple[list[str], list[str]]:
    words: list[str] = []
    negated: list[str] = []
    after_not = False
    for word in re.findall(r"[a-z]+", query):
        if word in _NEGATIONS:
            after_not = True
        elif word in _STOPWORDS:
            after_not = after_not and word in _ARTICLES
        elif after_not:
            negated.append(word)
            after_not = False
        else:
            words.append(word)
    return _units(words), list(dict.fromkeys(negated))


def _units(words: list[str]) -> list[str]:
    units: list[str] = []
    i = 0
    while i < len(words):
        pair = words[i : i + 2]
        phrase = " ".join(pair)
        if len(pair) == 2 and _target(phrase) is not None:
            units.append(phrase)
            i += 2
        else:
            units.append(words[i])
            i += 1
    return list(dict.fromkeys(units))


def _target(unit: str) -> str | None:
    if set(unit.split()) & set(_UI_ONLY_TERMS):
        return None
    return resolve_meal_term(unit)


def _matches(unit: str, recipe_id: str) -> bool:
    if " " not in unit and _stem(unit) in _meal_words(recipe_id):
        return True
    target = _target(unit)
    return target is not None and (
        target == "omnivore"
        or target in MEAL_TAGS[recipe_id]
        or target in MEAL_DIETS[recipe_id]
    )


def _facet(unit: str) -> str | None:
    target = _target(unit)
    return target if target in (*TAG_ORDER, *_FACET_DIETS) else None


def _has_facet(facet: str, recipe_id: str) -> bool:
    return facet in MEAL_TAGS[recipe_id] or facet in MEAL_DIETS[recipe_id]


def _has_word(word: str, recipe_id: str) -> bool:
    return _stem(word) in _meal_words(recipe_id)


@cache
def _protein_mg(recipe_id: str) -> int:
    request = GroceryRequest(
        meals=[MealRequest(recipe_id=recipe_id, servings=1)],
        budget_period=date(2026, 1, 1),
    )
    plan = meal_nutrition(request)
    if len(plan.meals) != 1:
        raise ValueError(f"nutrition is unavailable for {recipe_id}")
    return plan.meals[0].per_serving.protein_mg


def _protein_g(recipe_id: str) -> int:
    return (_protein_mg(recipe_id) + 500) // 1000


@cache
def _serving_cents(recipe_id: str) -> int | None:
    budget = BudgetResult(10**9, 0, False, ())
    total = priced_estimate([(recipe_id, 1)], [], budget)["total_cents"]
    return total if isinstance(total, int) else None


def _int(value: object, low: int, high: int, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or not low <= value <= high:
        raise CatalogToolError(_BAD)
    return value


def _names(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 22:
        raise CatalogToolError(_BAD)
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not 1 <= len(item) <= 64:
            raise CatalogToolError(_BAD)
        if not normalize_term(item):
            raise CatalogToolError(_BAD)
        names.append(normalize_term(item))
    return names


def execute_catalog_search(arguments: object) -> dict[str, object]:
    if not isinstance(arguments, dict) or not {"query"} <= set(arguments) <= _KEYS:
        raise CatalogToolError(_BAD)
    raw_query = arguments["query"]
    raw_diet = arguments.get("diet", "omnivore")
    if not isinstance(raw_query, str) or not 1 <= len(raw_query) <= 120:
        raise CatalogToolError(_BAD)
    if not isinstance(raw_diet, str) or len(raw_diet) > 64:
        raise CatalogToolError(_BAD)
    query, diet = normalize_term(raw_query), normalize_term(raw_diet)
    min_protein = _int(arguments.get("min_protein_g"), 0, 200, True)
    max_cents = _int(arguments.get("max_cents_per_serving"), 1, 10000, True)
    limit = _int(arguments.get("limit", 3), 1, 3)
    names = _names(arguments.get("exclude", []))
    if not query or diet not in _DIETS or limit is None:
        raise CatalogToolError(_BAD)
    resolved = {name: resolve_ingredient(name) for name in names}
    unresolved = sorted(name for name, found in resolved.items() if found is None)
    excluded = {found for found in resolved.values() if found is not None}
    units, negated = _parse(query)
    unmatched = [
        u for u in units if not any(_matches(u, r) for r in SUPPORTED_RECIPE_IDS)
    ]
    unmatched = list(dict.fromkeys([*unmatched, *negated]))
    query_facets = {f for u in units if (f := _facet(u)) is not None}
    facets = query_facets | ({diet} - {"omnivore"})
    applied = [f for f in (*TAG_ORDER, *_FACET_DIETS) if f in facets]
    words = [
        u
        for u in units
        if _facet(u) is None and any(_has_word(u, r) for r in SUPPORTED_RECIPE_IDS)
    ]
    searchable = bool(facets or words)
    eligible: list[str] = []
    for rid in () if unresolved or not searchable else SUPPORTED_RECIPE_IDS:
        if not all(_has_facet(f, rid) for f in applied):
            continue
        if excluded.intersection(item for item, _ in RECIPES[rid].ingredients):
            continue
        if min_protein is not None and _protein_g(rid) < min_protein:
            continue
        if max_cents is not None:
            cents = _serving_cents(rid)
            if cents is None or cents > max_cents:
                continue
        eligible.append(rid)
    found_ids = [r for r in eligible if all(_has_word(w, r) for w in words)]
    dropped: list[str] = []
    if not found_ids and facets and eligible:
        found_ids, dropped = eligible, words
    if min_protein is not None:
        found_ids = sorted(found_ids, key=lambda r: -_protein_g(r))
    ids = found_ids[:limit]
    status = "unknown_exclusion" if unresolved else "ok" if ids else "no_match"
    return {
        "status": status,
        "request": {
            "query": query,
            "diet": diet,
            "exclude": sorted(excluded),
            "min_protein_g": min_protein,
            "max_cents_per_serving": max_cents,
            "limit": limit,
        },
        "recipe_ids": ids,
        "applied": applied,
        "dropped": dropped,
        "unmatched": unmatched,
        "unresolved_exclusions": unresolved,
    }


def catalog_answer(payload: dict[str, object]) -> str:
    request = payload.get("request")
    unresolved = payload.get("unresolved_exclusions")
    if (
        payload.get("status") == "unknown_exclusion"
        and isinstance(request, dict)
        and isinstance(request.get("exclude"), list)
        and isinstance(unresolved, list)
    ):
        request = {**request, "exclude": [*request["exclude"], *unresolved]}
    try:
        validated = execute_catalog_search(request)
    except CatalogToolError:
        return DISCOVERY_ERROR
    if payload != validated:
        return DISCOVERY_ERROR
    if validated["status"] == "unknown_exclusion":
        return _UNKNOWN_EXCLUSION
    if validated["status"] == "no_match":
        return _NO_MATCH
    request = cast(dict[str, object], validated["request"])
    chosen = cast(list[str], validated["recipe_ids"])
    applied = cast(list[str], validated["applied"])
    dropped = cast(list[str], validated["dropped"])
    notes = []
    if "lower_carb" in applied and all("lower_carb" in MEAL_TAGS[r] for r in chosen):
        notes.append(KETO_NOTE)
    if "chicken" in applied and all("chicken" in MEAL_TAGS[r] for r in chosen):
        notes.append(CARNIVORE_NOTE)
    if dropped:
        notes.append(f"No meal with those types also matched: {', '.join(dropped)}.")
    names = []
    for rid in chosen:
        name = rid.replace("_", " ")
        names.append(name[0].upper() + name[1:])
    lead = f"Catalog choices: {', '.join(names)}. Which one should I plan?"
    caveats = [_CAVEATS[f] for f in applied if f in _CAVEATS]
    return " ".join([lead, *notes, *caveats, _CANNOT_CLAIM])
