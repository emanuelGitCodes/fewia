import json
from pathlib import Path

import pytest

from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.prototype_catalog_export import (
    build_catalog,
    main,
    recipe_name,
    render_catalog,
)

GENERATED = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "prototype"
    / "catalog.generated.json"
)
REGENERATE = (
    "cd backend && uv run python -m app.prototype_catalog_export "
    "--out ../frontend/src/prototype/catalog.generated.json"
)


def test_checked_in_json_matches_the_backend_catalog() -> None:
    assert GENERATED.read_text(encoding="utf-8") == render_catalog(), (
        f"catalog.generated.json drifted. Run: {REGENERATE}"
    )


def test_a_changed_price_is_detected_as_drift() -> None:
    drifted = build_catalog()
    drifted["ingredients"][0]["priceCents"] += 1
    text = json.dumps(drifted, indent=2, ensure_ascii=False) + "\n"
    assert text != GENERATED.read_text(encoding="utf-8")


def test_exports_forty_recipes_in_supported_order() -> None:
    recipes = build_catalog()["recipes"]
    assert len(recipes) == 40
    assert [recipe["id"] for recipe in recipes] == list(SUPPORTED_RECIPE_IDS)


def test_exports_ingredients_in_catalog_order_with_integer_cents() -> None:
    ingredients = build_catalog()["ingredients"]
    assert [item["id"] for item in ingredients] == list(INGREDIENTS)
    for item in ingredients:
        assert list(item) == [
            "id",
            "name",
            "unit",
            "packageQuantity",
            "priceCents",
            "isPantry",
        ]
        assert item["unit"] in ("g", "each")
        assert type(item["packageQuantity"]) is int
        assert item["packageQuantity"] > 0
        assert type(item["priceCents"]) is int
        assert type(item["isPantry"]) is bool
    pantry = {item["id"] for item in ingredients if item["isPantry"]}
    assert pantry == {"olive_oil", "cumin", "salt", "curry_powder"}


def test_vegan_recipes_list_both_diets() -> None:
    by_id = {recipe["id"]: recipe for recipe in build_catalog()["recipes"]}
    assert by_id["bean_tacos"]["diets"] == ["vegan", "vegetarian"]
    assert by_id["egg_fried_rice"]["diets"] == ["vegetarian"]
    assert by_id["chicken_potato_bake"]["diets"] == []


def test_recipe_names_follow_the_rule() -> None:
    assert recipe_name("bean_tacos") == "Bean tacos"
    for recipe in build_catalog()["recipes"]:
        spaced = recipe["id"].replace("_", " ")
        assert recipe["name"] == spaced[0].upper() + spaced[1:]
        assert recipe["name"][0].isupper()


def test_recipe_ingredients_and_nutrition_are_per_serving() -> None:
    by_id = {recipe["id"]: recipe for recipe in build_catalog()["recipes"]}
    tacos = by_id["bean_tacos"]
    assert tacos["ingredients"][0] == ["black_beans", 120]
    assert list(tacos["nutrition"]) == ["energyKcal", "proteinG", "carbsG", "fatG"]
    assert type(tacos["nutrition"]["energyKcal"]) is int
    for recipe in by_id.values():
        assert all(
            ingredient_id in INGREDIENTS for ingredient_id, _ in recipe["ingredients"]
        )
        assert all(
            type(quantity) is int and quantity > 0
            for _, quantity in recipe["ingredients"]
        )


TAG_ORDER = [
    "chicken",
    "egg",
    "beans",
    "lentils",
    "chickpeas",
    "high_protein",
    "lower_carb",
    "gluten_free_ingredients",
]


def test_recipe_keys_put_tags_after_diets() -> None:
    for recipe in build_catalog()["recipes"]:
        assert list(recipe) == [
            "id",
            "name",
            "diets",
            "tags",
            "ingredients",
            "nutrition",
        ]


def test_tag_counts_match_the_catalog() -> None:
    counts = dict.fromkeys(TAG_ORDER, 0)
    for recipe in build_catalog()["recipes"]:
        for tag in recipe["tags"]:
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
    for recipe in build_catalog()["recipes"]:
        tags = recipe["tags"]
        assert tags == sorted(set(tags), key=TAG_ORDER.index)
        ids = {ingredient_id for ingredient_id, _ in recipe["ingredients"]}
        assert ("chicken" in tags) == ("chicken_breast" in ids)
        assert ("egg" in tags) == ("eggs" in ids)
        assert ("beans" in tags) == ("black_beans" in ids)
        assert ("lentils" in tags) == ("lentils" in ids)
        assert ("chickpeas" in tags) == ("chickpeas" in ids)
        assert ("high_protein" in tags) == (recipe["nutrition"]["proteinG"] >= 30)
        assert ("lower_carb" in tags) == (recipe["nutrition"]["carbsG"] <= 30)
        gluten = ids & {"pasta", "soy_sauce", "oats", "oat_milk"}
        assert ("gluten_free_ingredients" in tags) == (not gluten)


def test_every_recipe_has_a_diet_or_tag_label() -> None:
    for recipe in build_catalog()["recipes"]:
        assert recipe["diets"] or recipe["tags"]


def test_main_prints_json_without_out(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert capsys.readouterr().out == render_catalog()


def test_main_writes_the_file_with_out(tmp_path: Path) -> None:
    target = tmp_path / "catalog.json"
    main(["--out", str(target)])
    assert target.read_text(encoding="utf-8") == render_catalog()
    assert render_catalog().endswith("}\n")
