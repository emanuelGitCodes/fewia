"""Live USDA FoodData Central search for foods outside the bundled data."""

import functools
import json
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.domain.nutrition import NutritionFacts
from app.domain.usda_foods import display_name
from app.providers.http_client import build_http_client
from app.usda_refresh import _load_api_key

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
DATA_TYPES = "Foundation,SR Legacy,Branded"
PAGE_SIZE = 5
TIMEOUT = httpx.Timeout(5.0, connect=3.0, read=5.0)
COOLDOWN_SECONDS = 600
HOURLY_LIMIT = 900
MAX_TEXT = 160
_ENERGY_NUMBERS = ("208", "957", "958")
_MACRO_NUMBERS = ("203", "204", "205", "307")


class UsdaUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("USDA FoodData Central is unavailable")


@dataclass(frozen=True)
class LiveFood:
    fdc_id: int
    name: str
    brand: str | None
    data_type: str
    facts: NutritionFacts


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    kept = "".join(
        ch for ch in value if unicodedata.category(ch) not in ("Cc", "Cf", "Zl", "Zp")
    )
    return kept.strip()[:MAX_TEXT].strip() or None


def _facts(fdc_id: int, nutrients: object) -> NutritionFacts | None:
    if not isinstance(nutrients, list):
        return None
    values: dict[str, int] = {}
    for item in nutrients:
        if not isinstance(item, dict):
            continue
        number = item.get("nutrientNumber")
        if number not in _ENERGY_NUMBERS and number not in _MACRO_NUMBERS:
            continue
        amount = item.get("value")
        if isinstance(amount, bool) or not isinstance(amount, int | float):
            return None
        unit = str(item.get("unitName", "")).lower()
        try:
            parsed = float(amount) * (1000 if unit == "g" else 1)
        except OverflowError:
            return None
        if unit not in ("g", "mg", "kcal") or not 0 <= parsed < 1e12:
            return None
        values[str(number)] = round(parsed)
    energy = next((values[n] for n in _ENERGY_NUMBERS if n in values), None)
    if energy is None or not all(n in values for n in _MACRO_NUMBERS):
        return None
    return NutritionFacts(
        fdc_id, energy, values["203"], values["204"], values["205"], values["307"]
    )


def _parse_food(entry: object) -> LiveFood | None:
    if not isinstance(entry, dict):
        return None
    fdc_id = entry.get("fdcId")
    description = _clean(entry.get("description"))
    data_type = _clean(entry.get("dataType"))
    if type(fdc_id) is not int or fdc_id <= 0 or description is None:
        return None
    if data_type is None:
        return None
    facts = _facts(fdc_id, entry.get("foodNutrients"))
    if facts is None:
        return None
    try:
        name = _clean(display_name(description))
    except ValueError:
        return None
    if name is None:
        return None
    return LiveFood(fdc_id, name, _clean(entry.get("brandOwner")), data_type, facts)


class UsdaLiveClient:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key MUST be nonblank")
        self._api_key = api_key
        self._clock = clock
        self._owns_client = client is None
        self._client = (
            build_http_client("https://api.nal.usda.gov") if client is None else client
        )
        self._lock = threading.Lock()
        self._cooldown_until: float | None = None
        self._window: int | None = None
        self._count = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _spend(self) -> None:
        with self._lock:
            now = self._clock()
            if self._cooldown_until is not None and now < self._cooldown_until:
                raise UsdaUnavailable()
            window = int(now // 3600)
            if window != self._window:
                self._window, self._count = window, 0
            if self._count >= HOURLY_LIMIT:
                raise UsdaUnavailable()
            self._count += 1

    def search(self, query: str) -> list[LiveFood]:
        if (
            not isinstance(query, str)
            or not 1 <= len(query) <= 160
            or not query.isprintable()
        ):
            raise ValueError("query MUST be 1 to 160 printable characters")
        self._spend()
        response: httpx.Response | None = None
        try:
            response = self._client.get(
                SEARCH_URL,
                params={
                    "query": query,
                    "dataType": DATA_TYPES,
                    "pageSize": str(PAGE_SIZE),
                },
                headers={"Accept": "application/json", "X-Api-Key": self._api_key},
                follow_redirects=False,
                timeout=TIMEOUT,
            )
        except (httpx.RequestError, httpx.InvalidURL, TypeError, ValueError):
            pass
        if response is None:
            raise UsdaUnavailable()
        if response.status_code == 429:
            with self._lock:
                self._cooldown_until = self._clock() + COOLDOWN_SECONDS
        if response.status_code != 200:
            raise UsdaUnavailable()
        payload: object = None
        failed = False
        try:
            payload = json.loads(response.content)
        except Exception:  # noqa: BLE001
            failed = True
        if failed or not isinstance(payload, dict):
            raise UsdaUnavailable()
        foods = payload.get("foods")
        if not isinstance(foods, list):
            raise UsdaUnavailable()
        parsed = (_parse_food(entry) for entry in foods)
        return [food for food in parsed if food is not None]


_lock = threading.Lock()


@functools.cache
def _build_client() -> UsdaLiveClient | None:
    key = _load_api_key()
    return None if key is None else UsdaLiveClient(key.get_secret_value())


def get_usda_live_client() -> UsdaLiveClient | None:
    """Return one process-wide USDA client, or None without a readable key."""
    with _lock:
        return _build_client()


get_usda_live_client.cache_clear = _build_client.cache_clear  # type: ignore[attr-defined]
