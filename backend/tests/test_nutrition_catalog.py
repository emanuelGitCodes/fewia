import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from app.domain.catalog import INGREDIENTS
from app.domain.nutrition import USDA_NUTRITION_NOTICE as DOMAIN_NOTICE
from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import (
    NUTRITION,
    NUTRITION_BASIS_G,
    USDA_NUTRITION_NOTICE,
)

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "usda_macros.json"
_SR_DOWNLOAD_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/"
    "FoodData_Central_sr_legacy_food_csv_2018-04.zip"
)
_IDENTITY_CASES = (
    ("eggs", 171287, "Egg, whole, raw, fresh", 173424),
    ("tortillas", 175036, "Tortillas, ready-to-bake or -fry, corn", 169740),
    (
        "black_beans",
        173735,
        "Beans, black, mature seeds, cooked, boiled, without salt",
        175194,
    ),
    (
        "rice",
        168877,
        "Rice, white, long-grain, regular, raw, enriched",
        168878,
    ),
    (
        "oat_milk",
        2257046,
        "Oat milk, unsweetened, plain, refrigerated",
        2515379,
    ),
)


def _load_usda_macros() -> Mapping[str, object]:
    raw: object = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if type(raw) is not dict:
        raise TypeError("usda_macros.json MUST be an object")
    return cast(Mapping[str, object], raw)


def _ingredient_rows(
    payload: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]]:
    raw = payload["ingredients"]
    if type(raw) is not dict:
        raise TypeError("ingredients MUST be an object")
    rows: dict[str, Mapping[str, object]] = {}
    for key, row in raw.items():
        if type(key) is not str or type(row) is not dict:
            raise TypeError("each ingredient row MUST be an object")
        rows[key] = cast(Mapping[str, object], row)
    return rows


def _as_int(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is float:
        return int(Decimal(str(value)))
    raise TypeError("energy and sodium MUST be JSON numbers")


def _grams_to_mg(value: object) -> int:
    if type(value) is not int and type(value) is not float:
        raise TypeError("macro grams MUST be a JSON number")
    return int(Decimal(str(value)) * 1000)


def _facts_from_row(row: Mapping[str, object]) -> NutritionFacts:
    return NutritionFacts(
        fdc_id=_as_int(row["fdc_id"]),
        energy_kcal=_as_int(row["energy_kcal"]),
        protein_mg=_grams_to_mg(row["protein_g"]),
        fat_mg=_grams_to_mg(row["fat_g"]),
        carbohydrate_mg=_grams_to_mg(row["carbohydrate_g"]),
        sodium_mg=_as_int(row["sodium_mg"]),
    )


def test_nutrition_keys_match_ingredients() -> None:
    assert set(NUTRITION) == set(INGREDIENTS)


def test_nutrition_basis_is_100_g() -> None:
    payload = _load_usda_macros()
    assert NUTRITION_BASIS_G == 100
    assert payload["basis_g"] == NUTRITION_BASIS_G


def test_notice_matches_domain_constant() -> None:
    assert USDA_NUTRITION_NOTICE == DOMAIN_NOTICE


def test_fixture_covers_catalog_and_records_source() -> None:
    payload = _load_usda_macros()
    rows = _ingredient_rows(payload)
    assert payload["retrieved_date"] == "2026-09-12"
    assert payload["sr_download_url"] == _SR_DOWNLOAD_URL
    assert set(rows) == set(NUTRITION)
    assert len(rows) == 22


def test_catalog_matches_usda_macros_fixture() -> None:
    rows = _ingredient_rows(_load_usda_macros())
    for ingredient_id, facts in NUTRITION.items():
        row = rows[ingredient_id]
        assert facts == _facts_from_row(row)
        description = row["description"]
        source_url = row["source_url"]
        assert type(description) is str and description
        assert type(source_url) is str
        assert f"/{facts.fdc_id}/" in source_url


def test_energy_nutrient_ids_match_source_dataset() -> None:
    rows = _ingredient_rows(_load_usda_macros())
    for ingredient_id, row in rows.items():
        if ingredient_id == "oat_milk":
            assert row["energy_nutrient_id"] == 2047
            assert (
                row["source_type"]
                == "FoodData Central API format=full (full precision)"
            )
            continue
        assert row["energy_nutrient_id"] == 1008
        assert row["source_type"] == "SR Legacy CSV download (full precision)"


@pytest.mark.parametrize(
    ("ingredient_id", "fdc_id", "description", "wrong_fdc_id"),
    _IDENTITY_CASES,
)
def test_catalog_uses_verified_ingredient_identities(
    ingredient_id: str,
    fdc_id: int,
    description: str,
    wrong_fdc_id: int,
) -> None:
    row = _ingredient_rows(_load_usda_macros())[ingredient_id]
    facts = NUTRITION[ingredient_id]
    assert facts.fdc_id == fdc_id
    assert row["fdc_id"] == fdc_id
    assert row["description"] == description
    assert facts.fdc_id != wrong_fdc_id
    assert row["fdc_id"] != wrong_fdc_id


def test_salt_sodium_mg() -> None:
    assert NUTRITION["salt"].sodium_mg == 38758


def test_olive_oil_fat_mg() -> None:
    assert NUTRITION["olive_oil"].fat_mg == 100000
