import json
from typing import Any, cast

import pytest

from app.agent.ingredient_tool import (
    INGREDIENT_TOOL,
    IngredientToolError,
    execute_ingredient_facts,
    ingredient_tool_spec,
)
from app.domain.catalog import INGREDIENTS
from app.domain.curated_foods import CURATED_INGREDIENTS, CURATED_NUTRITION
from app.domain.nutrition_catalog import NUTRITION

_SECRET = "do-not-echo-raw-input"
_FOUND_KEYS = {
    "status",
    "ingredient_id",
    "name",
    "source",
    "fdc_id",
    "per_100g",
    "vegetarian",
    "vegan",
    "price_cents",
}
_MACRO_KEYS = {"energy_kcal", "protein_mg", "fat_mg", "carbohydrate_mg"}


def lookup(name: object) -> dict[str, Any]:
    return cast(dict[str, Any], execute_ingredient_facts({"name": name}))


def test_spec_declares_a_bounded_name() -> None:
    spec = cast(dict[str, Any], ingredient_tool_spec()["toolSpec"])
    schema = spec["inputSchema"]["json"]
    assert spec["name"] == INGREDIENT_TOOL == "get_ingredient_facts"
    assert schema["required"] == ["name"]
    assert schema["additionalProperties"] is False
    assert schema["properties"] == {
        "name": {"type": "string", "minLength": 1, "maxLength": 64}
    }


def test_beef_resolves_to_curated_ground_beef_80() -> None:
    result = lookup("Beef")
    assert set(result) == _FOUND_KEYS
    assert result["status"] == "found"
    assert result["ingredient_id"] == "ground_beef_80"
    assert result["name"] == "ground beef (80% lean)"
    assert result["source"] == "curated"
    assert result["fdc_id"] == 174036
    assert result["per_100g"] == {
        "energy_kcal": 254,
        "protein_mg": 17170,
        "fat_mg": 20000,
        "carbohydrate_mg": 0,
    }
    assert result["vegetarian"] is False and result["vegan"] is False
    assert result["price_cents"] is None
    json.dumps(result)


def test_black_beans_resolves_to_the_catalog_by_name_and_id() -> None:
    by_name = lookup("black beans")
    assert by_name["status"] == "found"
    assert by_name["ingredient_id"] == "black_beans"
    assert by_name["source"] == "catalog"
    assert by_name["fdc_id"] == NUTRITION["black_beans"].fdc_id
    assert by_name["price_cents"] == INGREDIENTS["black_beans"].price_cents
    assert by_name["vegan"] is True
    assert lookup("black_beans") == by_name


def test_per_100g_comes_from_the_nutrition_tables() -> None:
    for ingredient_id in INGREDIENTS:
        result = lookup(ingredient_id)
        facts = NUTRITION[ingredient_id]
        assert result["per_100g"] == {
            "energy_kcal": facts.energy_kcal,
            "protein_mg": facts.protein_mg,
            "fat_mg": facts.fat_mg,
            "carbohydrate_mg": facts.carbohydrate_mg,
        }
        assert set(result["per_100g"]) == _MACRO_KEYS
    for food_id, facts in CURATED_NUTRITION.items():
        assert lookup(food_id)["fdc_id"] == facts.fdc_id


@pytest.mark.parametrize("raw", ["beef", "  BEEF  ", "Ground   Beef", "hamburger"])
def test_names_are_normalized_and_synonyms_resolve(raw: str) -> None:
    assert lookup(raw)["ingredient_id"] == "ground_beef_80"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("minced beef", "ground_beef_80"),
        ("lean beef", "ground_beef_93"),
        ("lean ground beef", "ground_beef_93"),
        ("turkey", "ground_turkey"),
        ("salmon", "salmon"),
        ("pork chop", "pork_loin"),
        ("pork loin", "pork_loin"),
        ("ground pork", "ground_pork"),
    ],
)
def test_each_curated_synonym_resolves_to_one_food(raw: str, expected: str) -> None:
    result = lookup(raw)
    assert result["status"] == "found"
    assert result["ingredient_id"] == expected


def test_curated_ids_and_names_resolve_exactly() -> None:
    for food_id, ingredient in CURATED_INGREDIENTS.items():
        assert lookup(food_id)["ingredient_id"] == food_id
        assert lookup(ingredient.name.upper())["ingredient_id"] == food_id


def test_pork_is_ambiguous_between_both_pork_foods() -> None:
    result = lookup("pork")
    assert result["status"] == "ambiguous"
    assert result["name"] == "pork"
    candidates = result["candidates"]
    ids = [item["ingredient_id"] for item in candidates]
    assert ids == ["ground_pork", "pork_loin"]
    for item in candidates:
        assert set(item) == _FOUND_KEYS
        assert item["status"] == "found"
        assert item["source"] == "curated"


def test_unknown_name_returns_status_and_no_error() -> None:
    result = lookup("tofu")
    assert result == {"status": "unknown", "name": "tofu", "candidates": []}


def test_unknown_name_lists_up_to_three_related_foods() -> None:
    result = lookup("beef stew")
    assert result["status"] == "unknown"
    assert result["name"] == "beef stew"
    ids = [item["ingredient_id"] for item in result["candidates"]]
    assert ids[0] == "ground_beef_80"
    assert 1 <= len(ids) <= 3
    assert all(item["status"] == "found" for item in result["candidates"])
    contained = lookup("white rice bowl")
    assert contained["status"] == "unknown"
    assert [item["ingredient_id"] for item in contained["candidates"]] == ["rice"]
    wide = lookup("e")
    assert wide["status"] == "unknown"
    assert len(wide["candidates"]) == 3


def test_catalog_match_wins_over_a_curated_synonym() -> None:
    result = lookup("salt")
    assert result["source"] == "catalog"
    assert result["ingredient_id"] == "salt"


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        "beef",
        {},
        {"name": ""},
        {"name": "a" * 65},
        {"name": None},
        {"name": 5},
        {"name": True},
        {"name": ["beef"]},
        {"name": "beef", "extra": _SECRET},
        {"name": " " * 3},
        {"nom": "beef"},
    ],
)
def test_invalid_arguments_raise_a_static_error(arguments: object) -> None:
    with pytest.raises(IngredientToolError) as caught:
        execute_ingredient_facts(arguments)
    assert str(caught.value) == "arguments are invalid"
    assert _SECRET not in str(caught.value)


def test_name_length_edges_are_accepted() -> None:
    assert lookup("a")["status"] == "unknown"
    assert lookup("a" * 64)["status"] == "unknown"


def test_secret_name_is_not_an_error() -> None:
    result = lookup(_SECRET)
    assert result["status"] == "unknown"


def test_lookup_does_not_mutate_the_tables() -> None:
    before = (dict(INGREDIENTS), dict(CURATED_INGREDIENTS), dict(NUTRITION))
    lookup("pork")
    lookup("tofu")
    assert (dict(INGREDIENTS), dict(CURATED_INGREDIENTS), dict(NUTRITION)) == before


def test_error_is_value_error() -> None:
    assert issubclass(IngredientToolError, ValueError)
