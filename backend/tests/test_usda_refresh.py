"""Tests for the USDA FoodData Central refresh command."""

from pathlib import Path

import httpx
import pytest

from app.domain.nutrition import NutritionFacts
from app.usda_refresh import compare, fetch_facts, main

FAKE_API_KEY = "FAKE_USDA_FDC_KEY_VALUE"
FDC_ID = 171077
ABRIDGED_PAYLOAD = {
    "foodNutrients": [
        {"nutrientNumber": "208", "value": 120.4},
        {"nutrientNumber": "203", "value": 22.5},
        {"nutrientNumber": "204", "value": 2.62},
        {"nutrientNumber": "205", "value": 0},
        {"nutrientNumber": "307", "value": 0.045},
    ]
}


def test_fetch_facts_parses_abridged_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=ABRIDGED_PAYLOAD)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        facts = fetch_facts(FDC_ID, client, FAKE_API_KEY)
    finally:
        client.close()
    assert facts == NutritionFacts(
        fdc_id=FDC_ID,
        energy_kcal=120,
        protein_mg=22500,
        fat_mg=2620,
        carbohydrate_mg=0,
        sodium_mg=45,
    )


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
