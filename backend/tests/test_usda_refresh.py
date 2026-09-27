"""Tests for the USDA FoodData Central refresh command."""

import json
from pathlib import Path

import httpx
import pytest

from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import NUTRITION
from app.usda_refresh import compare, fetch_facts, main

FAKE_API_KEY = "FAKE_USDA_FDC_KEY_VALUE"
FDC_ID = 171077
REAL_FDC_ID = 173735
REAL_FULL = Path(__file__).parent / "fixtures" / "usda_173735_full.json"
FULL_PAYLOAD = {
    "foodNutrients": [
        {"nutrient": {"number": "208", "unitName": "kcal"}, "amount": 120.4},
        {"nutrient": {"number": "203", "unitName": "g"}, "amount": 22.5},
        {"nutrient": {"number": "204", "unitName": "g"}, "amount": 2.62},
        {"nutrient": {"number": "205", "unitName": "g"}, "amount": 0},
        {"nutrient": {"number": "307", "unitName": "mg"}, "amount": 45},
    ]
}
PARSED_FULL = NutritionFacts(
    fdc_id=FDC_ID,
    energy_kcal=120,
    protein_mg=22500,
    fat_mg=2620,
    carbohydrate_mg=0,
    sodium_mg=45,
)


def _fetch_payload(payload: object, fdc_id: int = FDC_ID) -> NutritionFacts | None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        return fetch_facts(fdc_id, client, FAKE_API_KEY)
    finally:
        client.close()


def test_fetch_facts_parses_abridged_payload() -> None:
    assert _fetch_payload(FULL_PAYLOAD) == PARSED_FULL


def test_fetch_facts_parses_energy_nutrient_957() -> None:
    payload = {
        "foodNutrients": [
            {"nutrient": {"number": "957", "unitName": "kcal"}, "amount": 120.4},
            {"nutrient": {"number": "203", "unitName": "g"}, "amount": 22.5},
            {"nutrient": {"number": "204", "unitName": "g"}, "amount": 2.62},
            {"nutrient": {"number": "205", "unitName": "g"}, "amount": 0},
            {"nutrient": {"number": "307", "unitName": "mg"}, "amount": 45},
        ]
    }
    facts = _fetch_payload(payload)
    assert facts is not None
    assert facts.energy_kcal == 120
    assert facts == PARSED_FULL


def test_fetch_facts_returns_none_when_protein_missing() -> None:
    payload = {
        "foodNutrients": [
            {"nutrient": {"number": "208", "unitName": "kcal"}, "amount": 120.4},
            {"nutrient": {"number": "204", "unitName": "g"}, "amount": 2.62},
            {"nutrient": {"number": "205", "unitName": "g"}, "amount": 0},
            {"nutrient": {"number": "307", "unitName": "mg"}, "amount": 45},
        ]
    }
    assert _fetch_payload(payload) is None


def test_fetch_facts_returns_none_when_nutrient_value_overflows_float() -> None:
    payload = {
        "foodNutrients": [
            {"nutrient": {"number": "208", "unitName": "kcal"}, "amount": 10**400},
            {"nutrient": {"number": "203", "unitName": "g"}, "amount": 22.5},
            {"nutrient": {"number": "204", "unitName": "g"}, "amount": 2.62},
            {"nutrient": {"number": "205", "unitName": "g"}, "amount": 0},
            {"nutrient": {"number": "307", "unitName": "mg"}, "amount": 45},
        ]
    }
    assert _fetch_payload(payload) is None


def test_fetch_facts_returns_none_when_scaled_amount_is_not_finite() -> None:
    payload = {
        "foodNutrients": [
            {"nutrient": {"number": "208", "unitName": "kcal"}, "amount": 120.4},
            {"nutrient": {"number": "203", "unitName": "g"}, "amount": 1e308},
            {"nutrient": {"number": "204", "unitName": "g"}, "amount": 2.62},
            {"nutrient": {"number": "205", "unitName": "g"}, "amount": 0},
            {"nutrient": {"number": "307", "unitName": "mg"}, "amount": 45},
        ]
    }
    assert _fetch_payload(payload) is None


def test_fetch_facts_returns_none_when_tracked_unit_is_unexpected() -> None:
    payload = {
        "foodNutrients": [
            {"nutrient": {"number": "208", "unitName": "kJ"}, "amount": 120.4},
            {"nutrient": {"number": "203", "unitName": "g"}, "amount": 22.5},
            {"nutrient": {"number": "204", "unitName": "g"}, "amount": 2.62},
            {"nutrient": {"number": "205", "unitName": "g"}, "amount": 0},
            {"nutrient": {"number": "307", "unitName": "mg"}, "amount": 45},
        ]
    }
    assert _fetch_payload(payload) is None


def test_fetch_facts_parses_real_usda_173735_full() -> None:
    payload = json.loads(REAL_FULL.read_text(encoding="utf-8"))
    facts = _fetch_payload(payload, fdc_id=REAL_FDC_ID)
    assert facts == NutritionFacts(
        fdc_id=173735,
        energy_kcal=132,
        protein_mg=8860,
        fat_mg=540,
        carbohydrate_mg=23710,
        sodium_mg=1,
    )
    stored = {"black_beans": NUTRITION["black_beans"]}
    fetched: dict[str, NutritionFacts | None] = {"black_beans": facts}
    assert compare(stored, fetched) == []


def test_compare_reports_diff_unavailable_and_skips_match() -> None:
    stored = {
        "changed": NutritionFacts(1, 10, 20, 30, 40, 50),
        "missing": NutritionFacts(2, 1, 2, 3, 4, 5),
        "matched": NutritionFacts(3, 9, 8, 7, 6, 5),
    }
    fetched: dict[str, NutritionFacts | None] = {
        "changed": NutritionFacts(1, 10, 99, 30, 40, 50),
        "missing": None,
        "matched": NutritionFacts(3, 9, 8, 7, 6, 5),
    }
    lines = compare(stored, fetched)
    assert lines == [
        "changed: protein_mg stored=20 usda=99",
        "missing: unavailable",
    ]
    assert all("matched" not in line for line in lines)


def test_compare_reports_unavailable_when_fetched_key_absent() -> None:
    stored = {"absent": NutritionFacts(1, 10, 20, 30, 40, 50)}
    fetched: dict[str, NutritionFacts | None] = {}
    assert compare(stored, fetched) == ["absent: unavailable"]


def test_main_exits_2_when_key_file_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.key"
    monkeypatch.setenv("FEWIA_USDA_FDC_KEY_FILE", str(missing))
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2
    output = capsys.readouterr()
    text = f"{output.out}{output.err}"
    assert "FEWIA_USDA_FDC_KEY_FILE" in text
    assert FAKE_API_KEY not in text


def test_main_exits_2_when_key_file_is_whitespace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    blank = tmp_path / "blank.key"
    blank.write_text("   \n", encoding="utf-8")
    monkeypatch.setenv("FEWIA_USDA_FDC_KEY_FILE", str(blank))
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2
    output = capsys.readouterr()
    text = f"{output.out}{output.err}"
    assert "FEWIA_USDA_FDC_KEY_FILE" in text
    assert FAKE_API_KEY not in text
