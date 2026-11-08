"""Credential-free Kroger fixture mode: invented data over httpx.MockTransport.

The real KrogerClient builds requests and parses responses; only the transport
is replaced, so nothing here touches the network. Every store, product, UPC,
price, and token is invented. Kroger API terms forbid copying real responses.
"""

import base64
import hashlib
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography.fernet import Fernet

from app.providers.kroger import (
    CART_ADD_PATH,
    LOCATIONS_PATH,
    PRODUCTS_PATH,
    TOKEN_PATH,
    KrogerClient,
)

FIXTURE_PREFIX = "/grocery/kroger/fixture"
FIXTURE_CODE = "fewia-fixture-code"
FIXTURE_CLIENT_ID = "fewia-fixture-client"
FIXTURE_CLIENT_SECRET = "fewia-fixture-secret"
APP_TOKEN = "fewia-fixture-app-token"
ACCESS_TOKEN = "fewia-fixture-access-token"
REFRESH_TOKEN = "fewia-fixture-refresh-token"
NO_MATCH_TERMS = frozenset({"onion"})
_KEY_LABEL = b"fewia-kroger-fixture-token-key-v1"
_EXPIRES_IN = 1800
_NAMES = ("Market North", "Market East", "Market Central")
_ZIP_CODE = re.compile(r"[0-9]{5}")

Handler = Callable[[httpx.Request], httpx.Response]


def _digits(text: str, width: int) -> int:
    modulus: int = int("1" + "0" * width)
    value: int = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    return value % modulus


def _authorized(request: httpx.Request, scheme: str) -> bool:
    header: str = request.headers.get("authorization", "")
    return header.startswith(f"{scheme} ")


def _token(request: httpx.Request) -> httpx.Response:
    if not _authorized(request, "Basic"):
        return httpx.Response(401, json={"error": "invalid_client"})
    form = parse_qs(request.content.decode())
    grant = form.get("grant_type", [""])[0]
    if grant == "client_credentials":
        return httpx.Response(
            200, json={"access_token": APP_TOKEN, "expires_in": _EXPIRES_IN}
        )
    valid = (grant == "authorization_code" and form.get("code") == [FIXTURE_CODE]) or (
        grant == "refresh_token" and form.get("refresh_token") == [REFRESH_TOKEN]
    )
    if not valid:
        return httpx.Response(400, json={"error": "invalid_grant"})
    return httpx.Response(
        200,
        json={
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "expires_in": _EXPIRES_IN,
        },
    )


def _store(zip_code: str, number: int) -> dict[str, object]:
    return {
        "locationId": f"FX{zip_code}{number}",
        "name": f"FEWIA Fixture {_NAMES[number - 1]}",
        "chain": "FEWIA Fixture",
        "address": {
            "addressLine1": f"{number}00 Fixture Way",
            "city": "Fixtureville",
            "state": "ZZ",
            "zipCode": zip_code,
        },
    }


def _locations(request: httpx.Request) -> httpx.Response:
    if not _authorized(request, "Bearer"):
        return httpx.Response(401)
    params = request.url.params
    zip_code = params.get("filter.zipCode.near", "")
    if not _ZIP_CODE.fullmatch(zip_code):
        return httpx.Response(400)
    raw_limit = params.get("filter.limit", "5")
    limit = int(raw_limit) if raw_limit.isdecimal() else 5
    count = 2 + int(zip_code) % 2
    stores = [_store(zip_code, number) for number in range(1, count + 1)]
    return httpx.Response(200, json={"data": stores[:limit]})


def _product(term: str) -> dict[str, object]:
    upc = f"99{_digits(term, 11):011d}"
    regular = 199 + _digits(f"price:{term}", 3) % 600
    price: dict[str, float] = {"regular": regular / 100}
    if _digits(f"promo:{term}", 2) % 4 == 0:
        price["promo"] = (regular - 30) / 100
    return {
        "productId": f"fx{upc}",
        "upc": upc,
        "description": f"FEWIA Fixture {term.title()}",
        "brand": "FEWIA Fixture",
        "items": [
            {
                "size": "1 lb",
                "soldBy": "UNIT",
                "price": price,
                "inventory": {"stockLevel": "HIGH"},
            }
        ],
    }


def _products(request: httpx.Request) -> httpx.Response:
    if not _authorized(request, "Bearer"):
        return httpx.Response(401)
    term = request.url.params.get("filter.term", "").strip().lower()
    if not term:
        return httpx.Response(400)
    data = [] if term in NO_MATCH_TERMS else [_product(term)]
    return httpx.Response(200, json={"data": data})


def _cart_add(request: httpx.Request) -> httpx.Response:
    return httpx.Response(204 if _authorized(request, "Bearer") else 401)


_ROUTES: dict[tuple[str, str], Handler] = {
    ("POST", TOKEN_PATH): _token,
    ("GET", LOCATIONS_PATH): _locations,
    ("GET", PRODUCTS_PATH): _products,
    ("PUT", CART_ADD_PATH): _cart_add,
}


def fixture_handler(request: httpx.Request) -> httpx.Response:
    """Answer a Kroger request with invented data; any other path is a 404."""
    path = request.url.path
    if not path.startswith(f"{FIXTURE_PREFIX}/"):
        return httpx.Response(404)
    handler = _ROUTES.get((request.method, path.removeprefix(FIXTURE_PREFIX)))
    return handler(request) if handler is not None else httpx.Response(404)


def build_fixture_client(redirect_uri: str) -> KrogerClient:
    """Build the real KrogerClient over the fixture transport, with fake credentials."""
    origin = urlsplit(redirect_uri)
    return KrogerClient(
        FIXTURE_CLIENT_ID,
        FIXTURE_CLIENT_SECRET,
        base_url=f"{origin.scheme}://{origin.netloc}{FIXTURE_PREFIX}",
        client=httpx.Client(
            transport=httpx.MockTransport(fixture_handler),
            trust_env=False,
            follow_redirects=False,
        ),
        fixture=True,
    )


def build_fixture_cipher() -> Fernet:
    """Derive the token key at runtime from a fixed label; no key is stored."""
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_KEY_LABEL).digest()))
