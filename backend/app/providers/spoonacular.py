"""Spoonacular ingredient estimatedCost adapter."""

import json
import math
import time
from collections.abc import Callable

import httpx

BASE_URL = "https://api.spoonacular.com"
INFORMATION_PATH = "/food/ingredients/{id}/information"
CACHE_SECONDS = 3600
_TIMEOUT = httpx.Timeout(20.0, connect=3.0, read=20.0, write=20.0, pool=3.0)


class SpoonacularUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("Spoonacular estimate is unavailable")


def _require_api_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("api_key MUST be a nonblank string")
    return value


def _information_url(ingredient_id: int) -> str:
    return f"{BASE_URL}{INFORMATION_PATH.format(id=ingredient_id)}"


def _parse_estimated_cents(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    cost = payload.get("estimatedCost")
    if not isinstance(cost, dict):
        return None
    if cost.get("unit") != "US Cents":
        return None
    value = cost.get("value")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value):
        return None
    cents = int(round(value))
    if cents < 0:
        return None
    return cents


class SpoonacularEstimateProvider:
    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._api_key = _require_api_key(api_key)
        self._clock = time.monotonic if clock is None else clock
        self._cache: dict[tuple[int, int, str], tuple[float, int | None]] = {}
        if client is None:
            self._client = httpx.Client(
                base_url=BASE_URL,
                timeout=_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
                transport=httpx.HTTPTransport(retries=0, trust_env=False),
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        key = (ingredient_id, amount, unit)
        cached = self._cache.get(key)
        if cached is not None:
            stored_at, value = cached
            if self._clock() - stored_at < CACHE_SECONDS:
                return value
        response: httpx.Response | None = None
        try:
            response = self._client.get(
                _information_url(ingredient_id),
                params={"apiKey": self._api_key, "amount": amount, "unit": unit},
                follow_redirects=False,
                timeout=_TIMEOUT,
            )
        except (httpx.RequestError, httpx.InvalidURL, TypeError, ValueError):
            pass
        if response is None:
            raise SpoonacularUnavailable()
        if response.status_code != 200:
            raise SpoonacularUnavailable()
        try:
            payload: object = json.loads(response.content)
        except Exception:
            raise SpoonacularUnavailable() from None
        cents = _parse_estimated_cents(payload)
        self._cache[key] = (self._clock(), cents)
        return cents
