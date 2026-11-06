"""One API test across the Kroger path on a single synthetic transport.

Every product, store, UPC, and token here is invented.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.demo import DEMO_USER_ID
from app.deps import get_kroger_cipher, get_kroger_client, get_provider_settings
from app.kroger_cart import OUT_OF_STOCK
from app.kroger_customer import store_tokens
from app.kroger_models import KrogerCustomerToken
from app.main import app
from app.provider_settings import GroceryProviderSettings
from app.providers import kroger
from app.providers.kroger import CustomerTokens, KrogerClient
from app.services.kroger_overlay import kroger_search_term

CLIENT_ID = "PATH-CLIENT-ID"
CLIENT_SECRET = "PATH-CLIENT-SECRET"
APP_TOKEN = "PATH-APP-TOKEN"
ACCESS = "PATH-ACCESS-TOKEN"
REFRESH = "PATH-REFRESH-TOKEN"
LOCATION = "01234567"
SOLD_OUT_UPC = "0009998887776"
IN_STOCK_UPC = "0001112223334"
SALSA_UPC = "12345678"
ALL_SOLD_OUT_UPC = "87654321"
PANTRY = ["olive_oil", "cumin", "salt"]


def _product(upc: str, description: str, stock_level: str | None) -> object:
    item: dict[str, object] = {"size": "1 lb"}
    if stock_level is not None:
        item["inventory"] = {"stockLevel": stock_level}
    return {
        "productId": f"id-{upc}",
        "upc": upc,
        "description": description,
        "items": [item],
    }


CATALOG: dict[str | None, list[object]] = {
    kroger_search_term("chicken_breast"): [
        _product(SOLD_OUT_UPC, "Invented Sold Out Chicken", OUT_OF_STOCK),
        _product(IN_STOCK_UPC, "Invented Chicken", "HIGH"),
    ],
    kroger_search_term("salsa"): [_product(SALSA_UPC, "Invented Salsa", None)],
    kroger_search_term("tortillas"): [
        _product(ALL_SOLD_OUT_UPC, "Invented Sold Out Tortillas", OUT_OF_STOCK)
    ],
}


class Transport:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == kroger.CART_ADD_PATH:
            return httpx.Response(204)
        if path == kroger.TOKEN_PATH:
            return httpx.Response(
                200, json={"access_token": APP_TOKEN, "expires_in": 1800}
            )
        if path == kroger.LOCATIONS_PATH:
            store = {
                "locationId": LOCATION,
                "name": "Invented Market",
                "chain": "INVENTED",
                "address": {
                    "addressLine1": "1 Test Way",
                    "city": "Testville",
                    "state": "ZZ",
                    "zipCode": "00000",
                },
            }
            return httpx.Response(200, json={"data": [store]})
        if path == kroger.PRODUCTS_PATH:
            term = request.url.params["filter.term"]
            return httpx.Response(200, json={"data": CATALOG.get(term, [])})
        return httpx.Response(404)

    def cart_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == kroger.CART_ADD_PATH]


@pytest.fixture
def transport(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Transport]:
    seed_user(DEMO_USER_ID)
    monkeypatch.setattr(session, "commit", session.flush)
    mock = Transport()
    kroger_client = KrogerClient(
        CLIENT_ID,
        CLIENT_SECRET,
        base_url=kroger.HOSTS["certification"],
        client=httpx.Client(transport=httpx.MockTransport(mock)),
    )
    cipher = Fernet(Fernet.generate_key())
    settings = GroceryProviderSettings(
        kroger_redirect_uri="http://localhost:8010/grocery/kroger/callback",
        kroger_return_url="http://127.0.0.1:5173/prototype",
    )
    overrides = {
        get_kroger_client: lambda: kroger_client,
        get_kroger_cipher: lambda: cipher,
        get_provider_settings: lambda: settings,
    }
    app.dependency_overrides.update(overrides)
    store_tokens(session, DEMO_USER_ID, cipher, CustomerTokens(ACCESS, REFRESH, 1800))
    row = session.get(KrogerCustomerToken, DEMO_USER_ID)
    assert row is not None
    row.access_expires_at = datetime.now(UTC) + timedelta(seconds=1800)
    session.flush()
    try:
        yield mock
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


def test_plan_to_cart_path_on_one_transport(
    client: TestClient, transport: Transport
) -> None:
    responses: list[httpx.Response] = []

    saved = client.post(
        "/grocery/plans",
        json={
            "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
            "pantry_ingredient_ids": PANTRY,
            "plan_cap_cents": None,
        },
    )
    responses.append(saved)
    assert saved.status_code == 201
    revision_id = saved.json()["plan_revision_id"]

    found = client.post("/grocery/kroger/stores", json={"zip_code": "00000"})
    responses.append(found)
    assert found.status_code == 200
    location_id = found.json()["stores"][0]["location_id"]
    assert location_id == LOCATION

    previewed = client.post(
        "/grocery/kroger/cart/preview",
        json={"plan_revision_id": revision_id, "location_id": location_id},
    )
    responses.append(previewed)
    assert previewed.status_code == 200
    preview = previewed.json()
    assert transport.cart_requests() == []

    by_line = {item["ingredient_id"]: item for item in preview["items"]}
    assert by_line["chicken_breast"]["upc"] == IN_STOCK_UPC
    assert by_line["salsa"]["upc"] == SALSA_UPC
    unmatched = {line["ingredient_id"] for line in preview["unmatched"]}
    assert unmatched == {"onion", "tortillas"}
    preview_upcs = {item["upc"] for item in preview["items"]}
    assert SOLD_OUT_UPC not in preview_upcs
    assert ALL_SOLD_OUT_UPC not in preview_upcs

    lines = [{"upc": i["upc"], "quantity": i["quantity"]} for i in preview["items"]]
    added = client.post("/grocery/kroger/cart/add", json={"items": lines})
    responses.append(added)
    assert added.status_code == 204

    sent = transport.cart_requests()
    assert len(sent) == 1
    assert sent[0].headers["authorization"] == f"Bearer {ACCESS}"
    body = json.loads(sent[0].content)
    assert body == {"items": lines}
    assert [(i["upc"], i["quantity"]) for i in body["items"]] == [
        (i["upc"], i["quantity"]) for i in preview["items"]
    ]
    for upc in (SOLD_OUT_UPC, ALL_SOLD_OUT_UPC):
        assert upc not in sent[0].content.decode()

    secrets = [CLIENT_ID, CLIENT_SECRET, APP_TOKEN, ACCESS, REFRESH]
    for response in responses:
        for secret in secrets:
            assert secret not in response.text
            assert secret not in str(response.headers)
