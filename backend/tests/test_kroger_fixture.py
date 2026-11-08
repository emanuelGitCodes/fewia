"""Tests for the credential-free Kroger fixture mode. All data is invented."""

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from conftest import UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.demo import DEMO_USER_ID
from app.deps import get_kroger_cipher, get_kroger_client, get_provider_settings
from app.kroger_customer import STATE_COOKIE
from app.kroger_models import KrogerCustomerToken
from app.main import app
from app.plan_models import PlanRevision
from app.provider_runtime import build_kroger, build_kroger_cipher, capabilities
from app.provider_settings import GroceryProviderSettings, ProviderConfigurationError
from app.providers import kroger as kroger_provider
from app.providers.kroger import KrogerClient
from app.providers.kroger_fixture import (
    FIXTURE_CODE,
    FIXTURE_PREFIX,
    build_fixture_client,
    fixture_handler,
)
from app.services.kroger_overlay import attach_kroger_quote, kroger_search_term

REDIRECT = "http://localhost:8010/grocery/kroger/callback"
AUTHORIZE = f"/grocery/kroger/fixture{kroger_provider.AUTHORIZE_PATH}"
RETURN_URL = "http://127.0.0.1:5173/prototype"
LOCATION_ID = re.compile(r"[0-9A-Za-z]{8}")
NOW = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)
    get_kroger_client.cache_clear()
    get_kroger_cipher.cache_clear()
    yield
    get_kroger_client.cache_clear()
    get_kroger_cipher.cache_clear()
    app.dependency_overrides.pop(get_provider_settings, None)


def _fixture_settings(**extra: object) -> GroceryProviderSettings:
    return GroceryProviderSettings.model_validate(
        {"kroger_mode": "fixture", "kroger_redirect_uri": REDIRECT, **extra}
    )


def _fixture_client() -> KrogerClient:
    client = build_kroger(_fixture_settings())
    assert client is not None
    return client


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real HTTP transport MUST NOT be built")

    monkeypatch.setattr(kroger_provider, "build_http_client", boom)
    monkeypatch.setattr(httpx.HTTPTransport, "__init__", boom)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)


# configuration


@pytest.mark.parametrize(
    "field", ["kroger_client_id_file", "kroger_secret_file", "kroger_token_key_file"]
)
def test_fixture_mode_with_a_kroger_file_fails_closed(
    tmp_path: Path, field: str
) -> None:
    settings = _fixture_settings(**{field: tmp_path / "absent"})
    with pytest.raises(ProviderConfigurationError):
        build_kroger(settings)
    with pytest.raises(ProviderConfigurationError):
        build_kroger_cipher(settings)


def test_live_mode_without_files_builds_nothing() -> None:
    settings = GroceryProviderSettings()
    assert settings.kroger_mode == "live"
    assert build_kroger(settings) is None
    assert build_kroger_cipher(settings) is None


def test_fixture_client_uses_fake_credentials_and_a_local_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_network(monkeypatch)
    client = _fixture_client()
    assert client.fixture is True
    assert client.source == "fixture"
    assert client.authorize_url(REDIRECT, "s").startswith(
        f"http://localhost:8010{FIXTURE_PREFIX}{kroger_provider.AUTHORIZE_PATH}?"
    )


def test_live_client_is_not_a_fixture() -> None:
    http = httpx.Client(transport=httpx.MockTransport(fixture_handler))
    client = KrogerClient(
        "id", "secret", base_url=kroger_provider.HOSTS["production"], client=http
    )
    assert client.fixture is False
    assert client.source == "live"


def test_fixture_cipher_key_is_stable_across_calls() -> None:
    settings = _fixture_settings()
    first = build_kroger_cipher(settings)
    second = build_kroger_cipher(settings)
    assert first is not None and second is not None
    assert second.decrypt(first.encrypt(b"invented")) == b"invented"


def test_capabilities_report_the_kroger_mode(tmp_path: Path) -> None:
    assert capabilities(GroceryProviderSettings())["kroger_mode"] == "off"
    assert capabilities(_fixture_settings())["kroger_mode"] == "fixture"
    one = GroceryProviderSettings(kroger_client_id_file=tmp_path / "id")
    assert capabilities(one)["kroger_mode"] == "off"
    both = GroceryProviderSettings(
        kroger_client_id_file=tmp_path / "id", kroger_secret_file=tmp_path / "secret"
    )
    assert capabilities(both)["kroger_mode"] == "live"


# transport


def test_transport_rejects_unknown_paths_and_methods() -> None:
    http = httpx.Client(transport=httpx.MockTransport(fixture_handler))
    base = f"https://fixture.test{FIXTURE_PREFIX}"
    headers = {"Authorization": "Bearer invented"}
    for method, url in (
        ("GET", f"{base}/v1/unknown"),
        ("GET", f"{base}/v1/cart"),
        ("GET", f"{base}/v1/connect/oauth2/token"),
        ("POST", f"{base}/v1/products"),
        ("GET", "https://fixture.test/v1/products"),
        ("GET", f"https://fixture.test{FIXTURE_PREFIX}x/v1/products"),
    ):
        assert http.request(method, url, headers=headers).status_code == 404
    assert http.get(f"{base}/v1/products").status_code == 401


def test_fixture_mode_builds_no_real_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_network(monkeypatch)
    stores = _fixture_client().find_stores("12345")
    assert 2 <= len(stores) <= 3


@pytest.mark.parametrize("zip_code", ["00000", "12345", "12346", "99999"])
def test_any_zip_returns_two_or_three_invented_stores(zip_code: str) -> None:
    stores = _fixture_client().find_stores(zip_code, limit=5)
    assert len(stores) in (2, 3)
    for store in stores:
        assert LOCATION_ID.fullmatch(store.location_id)
        assert store.name.startswith("FEWIA Fixture")
        assert store.chain.startswith("FEWIA Fixture")
        assert store.zip_code == zip_code
    assert len({store.location_id for store in stores}) == len(stores)


def test_store_limit_is_honored() -> None:
    assert len(_fixture_client().find_stores("12345", limit=1)) == 1


@pytest.mark.parametrize(
    "term", ["chicken breast", "corn tortillas", "salsa", "ground beef 80% lean"]
)
def test_most_terms_return_one_invented_product(term: str) -> None:
    client = _fixture_client()
    location = client.find_stores("12345")[0].location_id
    products = client.search_products(term, location).products
    assert len(products) == 1
    product = products[0]
    assert product.description.startswith("FEWIA Fixture")
    assert (product.brand or "").startswith("FEWIA Fixture")
    assert product.upc is not None and re.fullmatch(r"[0-9]{8,14}", product.upc)
    assert product.regular_cents is not None and product.regular_cents > 0
    assert client.search_products(term, location).products == products


def test_the_onion_term_has_no_match() -> None:
    client = _fixture_client()
    location = client.find_stores("12345")[0].location_id
    assert kroger_search_term("onion") == "onion"
    assert client.search_products("onion", location).products == []


def test_customer_token_exchange_and_refresh() -> None:
    client = _fixture_client()
    tokens = client.exchange_code(FIXTURE_CODE, REDIRECT)
    assert client.refresh_customer(tokens.refresh_token).access_token
    with pytest.raises(kroger_provider.KrogerUnavailable):
        client.exchange_code("another-code", REDIRECT)
    with pytest.raises(kroger_provider.KrogerAuthRejected):
        client.refresh_customer("another-token")
    client.add_to_cart(tokens.access_token, [kroger_provider.CartItem("12345678", 1)])


def test_quote_kind_names_the_fixture() -> None:
    result: dict[str, object] = {
        "tool_trace": [
            {
                "tool": "what_if_substitute",
                "outcome": "success",
                "inputs": {"status": "swapped", "with_ingredient_id": "ground_beef_80"},
            }
        ]
    }
    client = _fixture_client()
    location = client.find_stores("12345")[0].location_id
    quote = attach_kroger_quote(result, client, location, lambda: NOW)["kroger_quote"]
    assert isinstance(quote, dict)
    assert quote["kind"] == "store_fixture"
    assert str(quote["product_label"]).startswith("FEWIA Fixture")


# route


def _override_settings(settings: GroceryProviderSettings) -> None:
    app.dependency_overrides[get_provider_settings] = lambda: settings


def test_authorize_route_is_404_in_live_mode(client: TestClient) -> None:
    _override_settings(GroceryProviderSettings(kroger_redirect_uri=REDIRECT))
    response = client.get(AUTHORIZE, params={"state": "abc"}, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers


def test_authorize_route_redirects_to_the_configured_uri_with_state(
    client: TestClient,
) -> None:
    _override_settings(_fixture_settings())
    state = "gAAAA-b_c=="
    response = client.get(AUTHORIZE, params={"state": state}, follow_redirects=False)
    assert response.status_code == 302
    target = urlsplit(response.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == REDIRECT
    assert parse_qs(target.query) == {"code": [FIXTURE_CODE], "state": [state]}


def test_authorize_route_ignores_a_query_redirect_uri(client: TestClient) -> None:
    _override_settings(_fixture_settings())
    response = client.get(
        AUTHORIZE,
        params={
            "state": "abc",
            "redirect_uri": "https://evil.test/steal",
            "code": "attacker-code",
        },
        follow_redirects=False,
    )
    target = urlsplit(response.headers["location"])
    assert (target.scheme, target.netloc) == ("http", "localhost:8010")
    assert "evil" not in response.headers["location"]
    assert parse_qs(target.query) == {"code": [FIXTURE_CODE], "state": ["abc"]}


@pytest.mark.parametrize("params", [{}, {"state": ""}, {"state": "x" * 513}])
def test_authorize_route_rejects_a_missing_or_oversized_state(
    client: TestClient, params: dict[str, str]
) -> None:
    _override_settings(_fixture_settings())
    response = client.get(AUTHORIZE, params=params, follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers


# full flow through the API


@pytest.fixture
def flow(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("FEWIA_KROGER_MODE", "fixture")
    monkeypatch.setenv("FEWIA_KROGER_RETURN_URL", RETURN_URL)
    _forbid_network(monkeypatch)
    seed_user(DEMO_USER_ID)
    monkeypatch.setattr(session, "commit", session.flush)
    return client


def _sign_in(flow: TestClient) -> httpx.Response:
    connect = flow.get(
        "/grocery/kroger/connect",
        headers={"host": "localhost:8010"},
        follow_redirects=False,
    )
    assert connect.status_code == 302
    nonce = connect.headers["set-cookie"].split(";", 1)[0].partition("=")[2]
    flow.cookies.clear()
    authorize = urlsplit(connect.headers["location"])
    assert authorize.path == AUTHORIZE
    approved = flow.get(f"{authorize.path}?{authorize.query}", follow_redirects=False)
    assert approved.status_code == 302
    callback = urlsplit(approved.headers["location"])
    return flow.get(
        f"{callback.path}?{callback.query}",
        headers={"cookie": f"{STATE_COOKIE}={nonce}"},
        follow_redirects=False,
    )


def _plan(session: Session) -> str:
    revision_id = uuid4()
    snapshot: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
        "pantry_ingredient_ids": ["olive_oil", "cumin", "salt"],
        "plan_cap_cents": None,
    }
    session.add(PlanRevision(id=revision_id, user_id=DEMO_USER_ID, snapshot=snapshot))
    session.flush()
    return str(revision_id)


def test_full_fixture_flow(flow: TestClient, session: Session) -> None:
    assert flow.get("/grocery/providers").json()["kroger_mode"] == "fixture"

    found = flow.post("/grocery/kroger/stores", json={"zip_code": "12345"})
    assert found.status_code == 200
    assert found.json()["source"] == "fixture"
    stores = found.json()["stores"]
    assert len(stores) in (2, 3)
    assert all(s["name"].startswith("FEWIA Fixture") for s in stores)
    location = stores[0]["location_id"]

    assert flow.get("/grocery/kroger/connection").json() == {"connected": False}
    done = _sign_in(flow)
    assert done.status_code == 302
    assert done.headers["location"] == f"{RETURN_URL}?kroger=connected"
    assert flow.get("/grocery/kroger/connection").json() == {"connected": True}

    preview = flow.post(
        "/grocery/kroger/cart/preview",
        json={"plan_revision_id": _plan(session), "location_id": location},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["source"] == "fixture"
    assert [line["ingredient_id"] for line in body["unmatched"]] == ["onion"]
    assert len(body["items"]) == 3
    assert all(i["description"].startswith("FEWIA Fixture") for i in body["items"])

    lines = [{"upc": i["upc"], "quantity": i["quantity"]} for i in body["items"]]
    added = flow.post("/grocery/kroger/cart/add", json={"items": lines})
    assert added.status_code == 204
    assert added.content == b""

    row = session.get(KrogerCustomerToken, DEMO_USER_ID)
    assert row is not None
    row.access_expires_at = datetime.now(UTC) - timedelta(seconds=5)
    session.flush()
    refreshed = flow.post("/grocery/kroger/cart/add", json={"items": lines})
    assert refreshed.status_code == 204
    assert flow.get("/grocery/kroger/connection").json() == {"connected": True}


def test_cart_add_without_sign_in_is_409(flow: TestClient) -> None:
    response = flow.post(
        "/grocery/kroger/cart/add", json={"items": [{"upc": "12345678", "quantity": 1}]}
    )
    assert response.status_code == 409


def test_fixture_mode_with_a_credential_file_reports_not_configured(
    flow: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FEWIA_KROGER_SECRET_FILE", str(tmp_path / "absent"))
    response = flow.post("/grocery/kroger/stores", json={"zip_code": "12345"})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Kroger is not configured"


def test_build_fixture_client_follows_the_redirect_origin() -> None:
    client = build_fixture_client("https://demo.test:8443/grocery/kroger/callback")
    assert client.authorize_url("x", "s").startswith(
        f"https://demo.test:8443{FIXTURE_PREFIX}/"
    )
