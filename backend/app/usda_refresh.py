"""Compare stored USDA nutrition facts to FoodData Central records."""

import json
import os
from collections.abc import Mapping
from pathlib import Path

import httpx
from pydantic import SecretStr

from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import NUTRITION
from app.provider_settings import ProviderConfigurationError, read_secret_file

FOOD_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
KEY_FILE_ENV = "FEWIA_USDA_FDC_KEY_FILE"
_KEY_FILE_ERROR = "FEWIA_USDA_FDC_KEY_FILE is unset, missing, or blank."
_TIMEOUT = httpx.Timeout(20.0, connect=3.0, read=20.0, write=20.0, pool=3.0)
_ENERGY_NUMBERS = ("208", "957", "958")
_MACRO_SCALE = {"203": 1000, "204": 1000, "205": 1000, "307": 1000}
_FIELDS = ("energy_kcal", "protein_mg", "fat_mg", "carbohydrate_mg", "sodium_mg")


def _load_api_key() -> SecretStr | None:
    raw_path = os.environ.get(KEY_FILE_ENV)
    if raw_path is None or not raw_path.strip():
        return None
    try:
        return read_secret_file(Path(raw_path.strip()))
    except ProviderConfigurationError:
        return None


def _parse_facts(fdc_id: int, payload: object) -> NutritionFacts | None:
    if not isinstance(payload, dict):
        return None
    nutrients = payload.get("foodNutrients")
    if not isinstance(nutrients, list):
        return None
    values: dict[str, int] = {}
    for item in nutrients:
        if not isinstance(item, dict):
            return None
        raw: object = item.get("nutrientNumber")
        nested = item.get("nutrient")
        if raw is None and isinstance(nested, dict):
            raw = nested.get("number")
        if isinstance(raw, bool):
            continue
        number = str(raw) if isinstance(raw, int) else raw
        if not isinstance(number, str):
            continue
        scale = 1 if number in _ENERGY_NUMBERS else _MACRO_SCALE.get(number)
        if scale is None:
            continue
        amount = item.get("value")
        if isinstance(amount, bool) or not isinstance(amount, int | float):
            return None
        try:
            parsed = float(amount)
        except OverflowError:
            return None
        if parsed != parsed or abs(parsed) == float("inf"):
            return None
        values[number] = int(round(parsed * scale))
        if values[number] < 0:
            return None
    energy = next((values[n] for n in _ENERGY_NUMBERS if n in values), None)
    if energy is None or not all(n in values for n in _MACRO_SCALE):
        return None
    try:
        return NutritionFacts(
            fdc_id,
            energy,
            values["203"],
            values["204"],
            values["205"],
            values["307"],
        )
    except ValueError:
        return None


def fetch_facts(
    fdc_id: int, client: httpx.Client, api_key: str
) -> NutritionFacts | None:
    try:
        response = client.get(
            FOOD_URL.format(fdc_id=fdc_id),
            params={"api_key": api_key, "format": "abridged"},
            follow_redirects=False,
            timeout=_TIMEOUT,
        )
    except (httpx.RequestError, httpx.InvalidURL, TypeError, ValueError):
        return None
    if response.status_code != 200:
        return None
    try:
        return _parse_facts(fdc_id, json.loads(response.content))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


def compare(
    stored: Mapping[str, NutritionFacts],
    fetched: Mapping[str, NutritionFacts | None],
) -> list[str]:
    lines: list[str] = []
    for ingredient_id, facts in stored.items():
        remote = fetched.get(ingredient_id)
        if remote is None:
            lines.append(f"{ingredient_id}: unavailable")
            continue
        for field in _FIELDS:
            stored_n = getattr(facts, field)
            usda_n = getattr(remote, field)
            if stored_n != usda_n:
                lines.append(
                    f"{ingredient_id}: {field} stored={stored_n} usda={usda_n}"
                )
    return lines


def main() -> None:
    secret = _load_api_key()
    if secret is None:
        print(_KEY_FILE_ERROR)
        raise SystemExit(2)
    with httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        transport=httpx.HTTPTransport(retries=0, trust_env=False),
    ) as client:
        fetched = {
            item_id: fetch_facts(facts.fdc_id, client, secret.get_secret_value())
            for item_id, facts in NUTRITION.items()
        }
        lines = compare(NUTRITION, fetched)
        for line in lines:
            print(line)
    raise SystemExit(0 if not lines else 1)


if __name__ == "__main__":
    main()
