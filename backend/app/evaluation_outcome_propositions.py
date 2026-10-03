import re
from collections.abc import Mapping
from typing import cast

from app.domain.catalog import INGREDIENTS, RECIPES

_PROPOSITIONS: dict[str, str] = {
    "egg_conflict": (
        r"eggs are not vegan|breakfast burritos contain eggs and are not vegan"
    ),
    "diet_conflict": r"chicken(?: tacos)? (?:is|are) not vegan",
    "unsupported": r"that recipe is not in the catalog|salmon tacos are not supported",
    "unknown": r"i cannot map mystery spice or nightshades to catalog ingredients",
    "restriction_question": r"which catalog ingredients should i exclude",
    "secret_refusal": r"i cannot provide credentials or raw bank records",
    "reject_purchase": r"i cannot buy items or place orders",
    "reject_url": r"i cannot open external links or place orders",
    "help": (
        r"i can help (?:plan meals using the budget summary|prepare a grocery plan)"
    ),
    "change": r"change the recipe or the restriction",
    "question": (
        r"which meal should i plan, and what servings, restrictions, "
        r"and pantry items apply"
    ),
}


def mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return dict(cast(Mapping[str, object], value))
    return {}


def public_tags(answer: object, *, vegan: bool) -> set[str] | None:
    if not isinstance(answer, str) or not answer.strip():
        return None
    names = [
        re.escape(recipe.id.replace("_", " ").casefold())
        for recipe in RECIPES.values()
        if not vegan or all(INGREDIENTS[key].vegan for key, _ in recipe.ingredients)
    ]
    patterns = dict(_PROPOSITIONS)
    if names:
        choice = "(?:" + "|".join(names) + ")"
        patterns.update(
            {
                "choice": rf"(?:examples|supported choices): {choice}(?:, {choice})*",
                "choice_question": rf"would you like {choice} instead",
            }
        )
    tags: set[str] = set()
    for clause in re.split(r"[.!?]+", answer.casefold()):
        if not clause.strip():
            continue
        matches = {
            tag
            for tag, pattern in patterns.items()
            if re.fullmatch(pattern, clause.strip())
        }
        if not matches:
            return None
        tags.update(matches)
    return tags or None
