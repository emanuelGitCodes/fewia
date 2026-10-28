from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.meal_tags import (
    CARNIVORE_NOTE,
    GLUTEN_INGREDIENT_IDS,
    HIGH_PROTEIN_G,
    KETO_NOTE,
    LOWER_CARB_G,
    MEAL_DIETS,
    MEAL_TAGS,
    SEARCH_TERMS,
    TAG_ORDER,
    _per_serving_grams,
)


def test_thresholds_and_gluten_ingredients() -> None:
    assert HIGH_PROTEIN_G == 30
    assert LOWER_CARB_G == 30
    assert GLUTEN_INGREDIENT_IDS == {"pasta", "soy_sauce", "oats", "oat_milk"}
    assert TAG_ORDER == (
        "chicken",
        "egg",
        "beans",
        "lentils",
        "chickpeas",
        "high_protein",
        "lower_carb",
        "gluten_free_ingredients",
    )


def test_meal_tags_follow_supported_recipe_order() -> None:
    assert list(MEAL_TAGS) == list(SUPPORTED_RECIPE_IDS)


def test_tag_counts_match_the_catalog() -> None:
    counts = dict.fromkeys(TAG_ORDER, 0)
    for tags in MEAL_TAGS.values():
        for tag in tags:
            counts[tag] += 1
    assert counts == {
        "chicken": 12,
        "egg": 10,
        "beans": 7,
        "lentils": 6,
        "chickpeas": 5,
        "high_protein": 10,
        "lower_carb": 8,
        "gluten_free_ingredients": 28,
    }


def test_tag_rules_and_order() -> None:
    for recipe_id, tags in MEAL_TAGS.items():
        assert list(tags) == sorted(set(tags), key=TAG_ORDER.index)
        ids = {ingredient_id for ingredient_id, _ in RECIPES[recipe_id].ingredients}
        protein_g, carbs_g = _per_serving_grams(recipe_id)
        assert ("chicken" in tags) == ("chicken_breast" in ids)
        assert ("egg" in tags) == ("eggs" in ids)
        assert ("beans" in tags) == ("black_beans" in ids)
        assert ("lentils" in tags) == ("lentils" in ids)
        assert ("chickpeas" in tags) == ("chickpeas" in ids)
        assert ("high_protein" in tags) == (protein_g >= HIGH_PROTEIN_G)
        assert ("lower_carb" in tags) == (carbs_g <= LOWER_CARB_G)
        assert ("gluten_free_ingredients" in tags) == (not ids & GLUTEN_INGREDIENT_IDS)


def test_meal_diets_follow_ingredient_flags() -> None:
    assert list(MEAL_DIETS) == list(SUPPORTED_RECIPE_IDS)
    for recipe_id, diets in MEAL_DIETS.items():
        items = [INGREDIENTS[i] for i, _ in RECIPES[recipe_id].ingredients]
        expected = []
        if all(item.vegan for item in items):
            expected.append("vegan")
        if all(item.vegetarian for item in items):
            expected.append("vegetarian")
        assert diets == tuple(expected)
    assert MEAL_DIETS["bean_tacos"] == ("vegan", "vegetarian")


def test_every_meal_has_a_diet_or_a_tag() -> None:
    for recipe_id in SUPPORTED_RECIPE_IDS:
        assert MEAL_DIETS[recipe_id] or MEAL_TAGS[recipe_id], recipe_id


def test_search_term_table() -> None:
    assert KETO_NOTE == (
        "No meal in this catalog is keto. "
        "These meals have 30 g of carbs or less per serving."
    )
    assert (
        CARNIVORE_NOTE == "No meal is strictly carnivore. These meals include chicken."
    )
    assert SEARCH_TERMS == {
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
    assert list(SEARCH_TERMS) == [
        "keto",
        "low carb",
        "lowcarb",
        "low-carb",
        "carnivore",
        "meat",
        "gf",
        "gluten free",
        "gluten-free",
        "celiac",
        "plant based",
        "plant-based",
        "veggie",
        "protein",
    ]
