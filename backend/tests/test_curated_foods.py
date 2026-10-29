import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.domain import curated_foods
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.curated_foods import (
    ALL_INGREDIENTS,
    ALL_NUTRITION,
    CURATED_FOODS_VERSION,
    CURATED_INGREDIENTS,
    CURATED_NUTRITION,
    CURATED_SYNONYMS,
)
from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import NUTRITION

_FILE = Path(curated_foods.__file__).with_name("curated_foods.json")
_PER_100G = ("energy_kcal", "protein_mg", "fat_mg", "carbohydrate_mg", "sodium_mg")
# id, name, synonyms, fdc_id, energy, protein, fat, carbs, sodium
_EXPECTED = (
    (
        "ground_beef_80",
        "ground beef (80% lean)",
        ["beef", "ground beef", "hamburger", "minced beef"],
        174036,
        (254, 17170, 20000, 0, 66),
    ),
    (
        "ground_beef_93",
        "lean ground beef (93% lean)",
        ["lean ground beef", "lean beef"],
        173110,
        (152, 20800, 7000, 0, 66),
    ),
    (
        "ground_pork",
        "ground pork",
        ["pork", "ground pork"],
        167902,
        (263, 16900, 21200, 0, 56),
    ),
    (
        "pork_loin",
        "pork loin",
        ["pork", "pork loin", "pork chop"],
        168314,
        (166, 21300, 8330, 0, 47),
    ),
    (
        "ground_turkey",
        "ground turkey",
        ["turkey", "ground turkey"],
        171505,
        (148, 19700, 7660, 0, 58),
    ),
    (
        "salmon",
        "salmon (Atlantic, farmed)",
        ["salmon"],
        175167,
        (208, 20400, 13400, 0, 59),
    ),
)


def _payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(_FILE.read_text(encoding="utf-8"))
    return payload


def test_file_has_the_version_and_exactly_the_six_rows() -> None:
    payload = _payload()
    assert set(payload) == {"version", "foods"}
    assert payload["version"] == "curated-foods-v1" == CURATED_FOODS_VERSION
    assert [food["id"] for food in payload["foods"]] == [row[0] for row in _EXPECTED]
    assert list(CURATED_INGREDIENTS) == [row[0] for row in _EXPECTED]


@pytest.mark.parametrize(("food_id", "name", "synonyms", "fdc_id", "macros"), _EXPECTED)
def test_each_row_matches_the_verified_usda_values(
    food_id: str,
    name: str,
    synonyms: list[str],
    fdc_id: int,
    macros: tuple[int, int, int, int, int],
) -> None:
    food = next(item for item in _payload()["foods"] if item["id"] == food_id)
    assert set(food) == {
        "id",
        "name",
        "synonyms",
        "fdc_id",
        "fdc_description",
        "per_100g",
        "vegetarian",
        "vegan",
        "package_grams",
    }
    assert food["name"] == name
    assert food["synonyms"] == synonyms
    assert food["fdc_id"] == fdc_id
    assert food["per_100g"] == dict(zip(_PER_100G, macros, strict=True))
    assert food["vegetarian"] is False and food["vegan"] is False
    assert food["package_grams"] == 454
    assert CURATED_NUTRITION[food_id] == NutritionFacts(fdc_id, *macros)
    assert CURATED_SYNONYMS[food_id] == tuple(synonyms)


def test_curated_ingredients_are_unpriced_grams_with_diet_flags() -> None:
    for food_id, ingredient in CURATED_INGREDIENTS.items():
        assert ingredient.id == food_id
        assert ingredient.unit == "g"
        assert ingredient.package_quantity == 454
        assert ingredient.price_cents is None
        assert ingredient.vegetarian is False and ingredient.vegan is False
        assert ingredient.is_pantry is False


def test_curated_ids_do_not_collide_with_the_catalog() -> None:
    assert not set(CURATED_INGREDIENTS) & set(INGREDIENTS)
    assert not set(CURATED_NUTRITION) & set(NUTRITION)


def test_all_maps_list_catalog_first_then_curated() -> None:
    assert list(ALL_INGREDIENTS) == [*INGREDIENTS, *CURATED_INGREDIENTS]
    assert list(ALL_NUTRITION) == [*NUTRITION, *CURATED_NUTRITION]
    for key, value in INGREDIENTS.items():
        assert ALL_INGREDIENTS[key] is value
    for key, facts in NUTRITION.items():
        assert ALL_NUTRITION[key] is facts


def test_catalog_maps_and_version_are_untouched() -> None:
    assert CATALOG_VERSION == "sample-prices-v2"
    assert "ground_beef_80" not in INGREDIENTS
    assert "ground_beef_80" not in NUTRITION


def test_synonyms_are_lowercase_and_pork_is_shared() -> None:
    for synonyms in CURATED_SYNONYMS.values():
        assert all(item == item.lower() and item for item in synonyms)
    sharing = [key for key, items in CURATED_SYNONYMS.items() if "pork" in items]
    assert sharing == ["ground_pork", "pork_loin"]


def _load_with(
    monkeypatch: pytest.MonkeyPatch, mutate: Callable[[dict[str, Any]], None]
) -> None:
    payload = copy.deepcopy(_payload())
    mutate(payload)
    text = json.dumps(payload)
    original = Path.read_text

    def read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "curated_foods.json":
            return text
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    curated_foods._load()


def test_loader_accepts_the_unchanged_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_with(monkeypatch, lambda payload: None)


def _duplicate_id(payload: dict[str, Any]) -> None:
    payload["foods"][1]["id"] = payload["foods"][0]["id"]


def _catalog_id(payload: dict[str, Any]) -> None:
    payload["foods"][0]["id"] = "rice"


def _negative(payload: dict[str, Any]) -> None:
    payload["foods"][0]["per_100g"]["fat_mg"] = -1


def _float(payload: dict[str, Any]) -> None:
    payload["foods"][0]["per_100g"]["energy_kcal"] = 254.0


def _bool_number(payload: dict[str, Any]) -> None:
    payload["foods"][0]["per_100g"]["sodium_mg"] = True


def _upper_synonym(payload: dict[str, Any]) -> None:
    payload["foods"][0]["synonyms"] = ["Beef"]


def _extra_key(payload: dict[str, Any]) -> None:
    payload["foods"][0]["price_cents"] = 100


def _missing_macro(payload: dict[str, Any]) -> None:
    del payload["foods"][0]["per_100g"]["sodium_mg"]


def _diet_text(payload: dict[str, Any]) -> None:
    payload["foods"][0]["vegan"] = "no"


def _zero_package(payload: dict[str, Any]) -> None:
    payload["foods"][0]["package_grams"] = 0


def _extra_top_level(payload: dict[str, Any]) -> None:
    payload["extra"] = 1


@pytest.mark.parametrize(
    "mutate",
    [
        _duplicate_id,
        _catalog_id,
        _negative,
        _float,
        _bool_number,
        _upper_synonym,
        _extra_key,
        _missing_macro,
        _diet_text,
        _zero_package,
        _extra_top_level,
    ],
)
def test_loader_rejects_invalid_files(
    monkeypatch: pytest.MonkeyPatch, mutate: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(ValueError, match="^curated foods are invalid: "):
        _load_with(monkeypatch, mutate)


def test_loader_rejects_an_unreadable_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("missing")

    monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(ValueError, match="could not load"):
        curated_foods._load()
