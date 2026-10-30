"""Kroger Locations and Products client with an in-memory app token."""

import argparse
import json
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.provider_settings import (
    ProviderConfigurationError,
    load_kroger_credentials,
    load_provider_settings,
)
from app.providers.http_client import build_http_client

HOSTS = {
    "certification": "https://api-ce.kroger.com",
    "production": "https://api.kroger.com",
}
TOKEN_PATH = "/v1/connect/oauth2/token"
LOCATIONS_PATH = "/v1/locations"
PRODUCTS_PATH = "/v1/products"
TIMEOUT = httpx.Timeout(5.0, connect=3.0, read=5.0)
TOKEN_MARGIN_SECONDS = 60
COOLDOWN_SECONDS = 600
DAILY_LIMITS = {"products": 10_000, "locations": 1_600}
MAX_TEXT = 160
MAX_DOLLARS = 100_000
_LOCATION_ID = re.compile(r"[0-9A-Za-z]{8}")
_ZIP_CODE = re.compile(r"[0-9]{5}")


class KrogerUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("Kroger is unavailable")


@dataclass(frozen=True)
class KrogerStore:
    location_id: str
    name: str
    chain: str
    address_line: str
    city: str
    state: str
    zip_code: str


@dataclass(frozen=True)
class KrogerProduct:
    product_id: str
    upc: str | None
    description: str
    brand: str | None
    size: str | None
    sold_by: str | None
    regular_cents: int | None
    promo_cents: int | None
    stock_level: str | None


@dataclass(frozen=True)
class KrogerSearch:
    products: list[KrogerProduct]
    cache_control: str | None


def kroger_base_url(environment: str) -> str:
    return HOSTS[environment]


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    kept = "".join(
        ch for ch in value if unicodedata.category(ch) not in ("Cc", "Cf", "Zl", "Zp")
    )
    return kept.strip()[:MAX_TEXT].strip() or None


def _cents(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        dollars = Decimal(str(value))
        if not dollars.is_finite() or dollars <= 0 or dollars > MAX_DOLLARS:
            return None
        cents = int((dollars * 100).quantize(Decimal(1), ROUND_HALF_UP))
    except (ArithmeticError, ValueError):
        return None
    return cents if cents > 0 else None


def _parse_store(entry: object) -> KrogerStore | None:
    if not isinstance(entry, dict):
        return None
    address = entry.get("address")
    if not isinstance(address, dict):
        return None
    raw_id = entry.get("locationId")
    if not isinstance(raw_id, str) or not _LOCATION_ID.fullmatch(raw_id):
        return None
    name = _clean(entry.get("name"))
    chain = _clean(entry.get("chain"))
    line = _clean(address.get("addressLine1"))
    city = _clean(address.get("city"))
    state = _clean(address.get("state"))
    zip_code = _clean(address.get("zipCode"))
    if (
        name is None
        or chain is None
        or line is None
        or city is None
        or state is None
        or zip_code is None
    ):
        return None
    return KrogerStore(raw_id, name, chain, line, city, state, zip_code)


def _parse_product(entry: object) -> KrogerProduct | None:
    if not isinstance(entry, dict):
        return None
    items = entry.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    item = items[0]
    product_id = _clean(entry.get("productId"))
    description = _clean(entry.get("description"))
    if product_id is None or description is None:
        return None
    price = item.get("price")
    inventory = item.get("inventory")
    price = price if isinstance(price, dict) else {}
    inventory = inventory if isinstance(inventory, dict) else {}
    return KrogerProduct(
        product_id=product_id,
        upc=_clean(entry.get("upc")),
        description=description,
        brand=_clean(entry.get("brand")),
        size=_clean(item.get("size")),
        sold_by=_clean(item.get("soldBy")),
        regular_cents=_cents(price.get("regular")),
        promo_cents=_cents(price.get("promo")),
        stock_level=_clean(inventory.get("stockLevel")),
    )


def _data_list(payload: object) -> list[object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise KrogerUnavailable()
    return list(payload["data"])


def _require_location_id(location_id: str) -> None:
    if not isinstance(location_id, str) or not _LOCATION_ID.fullmatch(location_id):
        raise ValueError("location_id MUST be 8 letters or digits")


def _require_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("limit MUST be an integer from 1 to 50")


class KrogerClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("credentials MUST be nonblank")
        self._auth = (client_id, client_secret)
        self._base_url = base_url.rstrip("/")
        self._clock = clock
        self._today = today
        self._owns_client = client is None
        self._client = build_http_client(self._base_url) if client is None else client
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._cooldown_until: float | None = None
        self._budget_day: date | None = None
        self._counts: dict[str, int] = {}
        self.cache_control: dict[str, str | None] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _check_cooldown(self) -> None:
        if self._cooldown_until is not None and self._clock() < self._cooldown_until:
            raise KrogerUnavailable()

    def _spend(self, kind: str) -> None:
        with self._lock:
            day = self._today()
            if day != self._budget_day:
                self._budget_day = day
                self._counts = {}
            if self._counts.get(kind, 0) >= DAILY_LIMITS[kind]:
                raise KrogerUnavailable()
            self._counts[kind] = self._counts.get(kind, 0) + 1

    def _send(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        *,
        auth: tuple[str, str] | None = None,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        locked: bool = False,
    ) -> httpx.Response:
        self._check_cooldown()
        response: httpx.Response | None = None
        try:
            response = self._client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                auth=auth,
                data=data,
                params=params,
                follow_redirects=False,
                timeout=TIMEOUT,
            )
        except (httpx.RequestError, httpx.InvalidURL, TypeError, ValueError):
            pass
        if response is None:
            raise KrogerUnavailable()
        with nullcontext() if locked else self._lock:
            if response.status_code == 401:
                self._token = None
            if response.status_code == 429:
                self._cooldown_until = self._clock() + COOLDOWN_SECONDS
        if response.status_code != 200:
            raise KrogerUnavailable()
        return response

    @staticmethod
    def _json(response: httpx.Response) -> object:
        payload: object = None
        failed = False
        try:
            payload = json.loads(response.content)
        except Exception:  # noqa: BLE001
            failed = True
        if failed:
            raise KrogerUnavailable()
        return payload

    def _app_token(self) -> str:
        with self._lock:
            if self._token is not None and self._clock() < self._token_expires_at:
                return self._token
            self._token = None
            response = self._send(
                "POST",
                TOKEN_PATH,
                {"Accept": "application/json"},
                auth=self._auth,
                data={"grant_type": "client_credentials", "scope": "product.compact"},
                locked=True,
            )
            payload = self._json(response)
            if not isinstance(payload, dict):
                raise KrogerUnavailable()
            token = payload.get("access_token")
            expires_in = payload.get("expires_in")
            if not isinstance(token, str) or not token.strip():
                raise KrogerUnavailable()
            if isinstance(expires_in, bool) or not isinstance(expires_in, int):
                raise KrogerUnavailable()
            if expires_in <= TOKEN_MARGIN_SECONDS:
                raise KrogerUnavailable()
            self.cache_control["token"] = response.headers.get("cache-control")
            self._token = token
            self._token_expires_at = self._clock() + expires_in - TOKEN_MARGIN_SECONDS
            return token

    def _get(self, kind: str, path: str, params: dict[str, str]) -> httpx.Response:
        self._check_cooldown()
        token = self._app_token()
        self._spend(kind)
        response = self._send(
            "GET",
            path,
            {"Accept": "application/json", "Authorization": f"Bearer {token}"},
            params=params,
        )
        self.cache_control[kind] = response.headers.get("cache-control")
        return response

    def find_stores(self, zip_code: str, limit: int = 5) -> list[KrogerStore]:
        if not isinstance(zip_code, str) or not _ZIP_CODE.fullmatch(zip_code):
            raise ValueError("zip_code MUST be exactly 5 digits")
        _require_limit(limit)
        payload = self._fetch(
            "locations",
            LOCATIONS_PATH,
            {"filter.zipCode.near": zip_code, "filter.limit": str(limit)},
        )
        stores = (_parse_store(entry) for entry in _data_list(payload))
        return [store for store in stores if store is not None]

    def search_products(
        self, term: str, location_id: str, limit: int = 5
    ) -> KrogerSearch:
        if (
            not isinstance(term, str)
            or not 1 <= len(term) <= 64
            or not term.isprintable()
        ):
            raise ValueError("term MUST be 1 to 64 printable characters")
        _require_location_id(location_id)
        _require_limit(limit)
        payload = self._fetch(
            "products",
            PRODUCTS_PATH,
            {
                "filter.term": term,
                "filter.locationId": location_id,
                "filter.limit": str(limit),
            },
        )
        products = (_parse_product(entry) for entry in _data_list(payload))
        return KrogerSearch(
            products=[p for p in products if p is not None],
            cache_control=self.cache_control.get("products"),
        )

    def _fetch(self, kind: str, path: str, params: dict[str, str]) -> object:
        return self._json(self._get(kind, path, params))


def _show(value: object) -> str:
    return "none" if value is None else str(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.providers.kroger")
    parser.add_argument("--zip", required=True, dest="zip_code")
    parser.add_argument("--term", required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_provider_settings()
        client_id, secret = load_kroger_credentials(settings)
    except ProviderConfigurationError:
        print("Kroger is not configured")
        return 2
    client = KrogerClient(
        client_id.get_secret_value(),
        secret.get_secret_value(),
        base_url=kroger_base_url(settings.kroger_environment),
    )
    try:
        stores = client.find_stores(args.zip_code)
        if stores:
            search = client.search_products(args.term, stores[0].location_id)
            for p in search.products:
                print(
                    "\t".join(
                        (
                            stores[0].name,
                            p.description,
                            _show(p.size),
                            _show(p.regular_cents),
                            _show(p.promo_cents),
                            _show(p.stock_level),
                        )
                    )
                )
        else:
            print("no stores found")
            client.cache_control.setdefault("products", "not requested")
    except ValueError:
        print("Invalid ZIP code or search term")
        return 2
    except KrogerUnavailable:
        print("Kroger is unavailable")
        return 2
    finally:
        client.close()
    for kind in ("locations", "products", "token"):
        print(f"cache-control {kind}: {_show(client.cache_control.get(kind))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
