"""Meal tags and search terms for the agent, the catalog export, and /prototype."""

import re
from datetime import date

from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.services.meal_nutrition import meal_nutrition

HIGH_PROTEIN_G = 30
LOWER_CARB_G = 30
PROTEIN_TAGS = (
    ("chicken", "chicken_breast"),
    ("egg", "eggs"),
    ("beans", "black_beans"),
    ("lentils", "lentils"),
    ("chickpeas", "chickpeas"),
)
# Oats and oat milk count as gluten ingredients.
GLUTEN_INGREDIENT_IDS = frozenset({"pasta", "soy_sauce", "oats", "oat_milk"})
TAG_ORDER = (
    "chicken",
    "egg",
    "beans",
    "lentils",
    "chickpeas",
    "high_protein",
    "lower_carb",
    "gluten_free_ingredients",
)
KETO_NOTE = (
    "No meal in this catalog is keto. "
    "These meals have 30 g of carbs or less per serving."
)
CARNIVORE_NOTE = "No meal is strictly carnivore. These meals include chicken."
# Term to target diet or tag, and an optional note.
SEARCH_TERMS: dict[str, tuple[str, str | None]] = {
    "keto": ("lower_carb", KETO_NOTE),
    "low carb": ("lower_carb", KETO_NOTE),
    "lowcarb": ("lower_carb", KETO_NOTE),
    "low-carb": ("lower_carb", KETO_NOTE),
    "carnivore": ("chicken", CARNIVORE_NOTE),
    "meat": ("chicken", CARNIVORE_NOTE),
    "gf": ("gluten_free_ingredients", None),
    "gluten free": ("gluten_free_ingredients", None),
    "gluten-free": ("gluten_free_ingredients", None),
    "celiac": ("gluten_free_ingredients", None),
    "plant based": ("vegan", None),
    "plant-based": ("vegan", None),
    "veggie": ("vegetarian", None),
    "protein": ("high_protein", None),
}


def normalize_term(value: str) -> str:
    return " ".join(value.lower().split())


def resolve_meal_term(value: str) -> str | None:
    term = normalize_term(value)
    if term in (*TAG_ORDER, "omnivore", "vegetarian", "vegan"):
        return term
    alias = SEARCH_TERMS.get(term)
    if alias is not None:
        return alias[0]
    spaced = " ".join(term.replace("_", " ").replace("-", " ").split())
    for canonical in (*TAG_ORDER, "omnivore", "vegetarian", "vegan"):
        if spaced == canonical.replace("_", " "):
            return canonical
    for key, (target, _note) in SEARCH_TERMS.items():
        if spaced == key.replace("-", " "):
            return target
    return None


_INGREDIENT_TAGS = frozenset({"chicken", "egg", "beans", "lentils", "chickpeas"})
# Diet labels the system cannot check; the same vocabulary as grounding.py.
_UNCHECKED_DIET = re.compile(
    r"\b(?:keto|paleo|halal|kosher|plant[- ]?based"
    r"|(?:dairy|lactose|nut|egg|soy|sugar)[- ]?free"
    r"|low[- ]?(?:sodium|fat)|high[- ]?fiber)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


def names_meal_type(text: str) -> bool:
    if _UNCHECKED_DIET.search(text) is not None:
        return True
    words = _WORD.findall(text.lower())
    pairs = (f"{a} {b}" for a, b in zip(words, words[1:], strict=False))
    for term in (*words, *pairs):
        target = resolve_meal_term(term)
        if target is None or target in ("omnivore",):
            continue
        # An ingredient word alone is not a meal type; an alias such as "meat" is.
        if target in _INGREDIENT_TAGS and term in (target, target.replace("_", " ")):
            continue
        return True
    return False


def resolve_ingredient(value: str) -> str | None:
    term = normalize_term(value)
    for ingredient in INGREDIENTS.values():
        if term in (ingredient.id, ingredient.name):
            return ingredient.id
    return None


def _per_serving_grams(recipe_id: str) -> tuple[float, float]:
    request = GroceryRequest(
        meals=[MealRequest(recipe_id=recipe_id, servings=1)],
        budget_period=date(2026, 1, 1),
    )
    plan = meal_nutrition(request)
    if len(plan.meals) != 1:
        raise ValueError(f"nutrition is unavailable for {recipe_id}")
    per = plan.meals[0].per_serving
    return round(per.protein_mg / 1000, 1), round(per.carbohydrate_mg / 1000, 1)


def _tags(recipe_id: str) -> tuple[str, ...]:
    ids = {ingredient_id for ingredient_id, _ in RECIPES[recipe_id].ingredients}
    protein_g, carbs_g = _per_serving_grams(recipe_id)
    tags = [tag for tag, ingredient_id in PROTEIN_TAGS if ingredient_id in ids]
    if protein_g >= HIGH_PROTEIN_G:
        tags.append("high_protein")
    if carbs_g <= LOWER_CARB_G:
        tags.append("lower_carb")
    if not ids & GLUTEN_INGREDIENT_IDS:
        tags.append("gluten_free_ingredients")
    return tuple(tags)


def _diets(recipe_id: str) -> tuple[str, ...]:
    items = [
        INGREDIENTS[ingredient_id]
        for ingredient_id, _ in RECIPES[recipe_id].ingredients
    ]
    diets: list[str] = []
    if all(item.vegan for item in items):
        diets.append("vegan")
    if all(item.vegetarian for item in items):
        diets.append("vegetarian")
    return tuple(diets)


MEAL_TAGS: dict[str, tuple[str, ...]] = {
    recipe_id: _tags(recipe_id) for recipe_id in SUPPORTED_RECIPE_IDS
}
# Vegan when every ingredient is vegan, vegetarian when every ingredient is vegetarian.
MEAL_DIETS: dict[str, tuple[str, ...]] = {
    recipe_id: _diets(recipe_id) for recipe_id in SUPPORTED_RECIPE_IDS
}
