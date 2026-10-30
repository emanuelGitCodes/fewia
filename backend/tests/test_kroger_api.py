"""Tests for the Kroger store lookup and sign-in routes, using invented data."""

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import kroger_customer
from app.api import kroger as kroger_routes
from app.demo import DEMO_USER_ID
from app.deps import get_kroger_cipher, get_kroger_client, get_provider_settings
from app.kroger_customer import (
    COOKIE_PATH,
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    make_state,
    new_nonce,
    redact_access_log,
    state_matches,
    store_tokens,
)
from app.kroger_models import KrogerCustomerToken
from app.main import app
from app.plan_models import PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.providers import kroger
from app.providers.kroger import CustomerTokens, KrogerClient
from app.services.kroger_overlay import kroger_search_term

SENTINEL_ZIP = "97531"
BASE = "https://kroger.test"
URL = "/grocery/kroger/stores"


def _store() -> dict[str, object]:
    return {
        "locationId": "01234567",
        "name": "Invented Market",
        "chain": "INVENTED",
        "address": {
            "addressLine1": "1 Test Way",
            "city": "Testville",
            "state": "ZZ",
            "zipCode": "00000",
        },
    }


def _client(handler: httpx.MockTransport) -> KrogerClient:
    http = httpx.Client(transport=handler)
    return KrogerClient("invented-id", "invented-secret", base_url=BASE, client=http)


@pytest.fixture
def api() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.pop(get_kroger_client, None)


def _override(client: KrogerClient | None) -> None:
    app.dependency_overrides[get_kroger_client] = lambda: client


def test_returns_stores_without_store_zip(api: TestClient) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        return httpx.Response(200, json={"data": [_store()]})

    _override(_client(httpx.MockTransport(handler)))
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 200
    assert response.json() == {
        "stores": [
            {
                "location_id": "01234567",
                "name": "Invented Market",
                "address_line": "1 Test Way",
                "city": "Testville",
                "state": "ZZ",
            }
        ]
    }
    assert seen[-1].url.params["filter.zipCode.near"] == SENTINEL_ZIP


def _locations_calls(
    api: TestClient, responses: list[list[dict[str, object]]]
) -> tuple[httpx.Response, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        calls.append(request)
        return httpx.Response(200, json={"data": responses[len(calls) - 1]})

    _override(_client(httpx.MockTransport(handler)))
    return api.post(URL, json={"zip_code": SENTINEL_ZIP}), calls


def test_wider_search_runs_once_when_first_is_empty(api: TestClient) -> None:
    store = _store()
    store["name"] = "INVENTED - - Far Spoke"
    store["chain"] = "INVENTED"
    response, calls = _locations_calls(api, [[], [store]])
    assert response.status_code == 200
    assert response.json()["stores"][0]["name"] == "Far Spoke"
    assert len(calls) == 2
    assert "filter.radiusInMiles" not in calls[0].url.params
    assert calls[1].url.params["filter.radiusInMiles"] == "50"


def test_no_wider_search_when_first_has_stores(api: TestClient) -> None:
    response, calls = _locations_calls(api, [[_store()]])
    assert response.status_code == 200
    assert len(calls) == 1


def test_at_most_two_calls_when_both_empty(api: TestClient) -> None:
    response, calls = _locations_calls(api, [[], []])
    assert response.status_code == 200
    assert response.json() == {"stores": []}
    assert len(calls) == 2


def test_not_configured(api: TestClient) -> None:
    _override(None)
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Kroger is not configured"


def _assert_no_sentinel(caplog: pytest.LogCaptureFixture, text: str) -> None:
    assert SENTINEL_ZIP not in text
    for record in caplog.records:
        assert SENTINEL_ZIP not in record.getMessage()
        assert SENTINEL_ZIP not in str(record.args)
    assert SENTINEL_ZIP not in caplog.text


def _token_then(status: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        return httpx.Response(status)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("status", [500, 429])
def test_unavailable_hides_zip(
    api: TestClient, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    caplog.set_level(logging.DEBUG)
    _override(_client(_token_then(status)))
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Kroger is unavailable"
    _assert_no_sentinel(caplog, response.text)


def test_token_failure_hides_zip(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _override(_client(httpx.MockTransport(lambda r: httpx.Response(500))))
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 503
    _assert_no_sentinel(caplog, response.text)


@pytest.mark.parametrize("bad", ["97531x", "9753", "975311", "9753a", "", "97 31"])
def test_bad_zip_is_422_without_echo(
    api: TestClient, caplog: pytest.LogCaptureFixture, bad: str
) -> None:
    caplog.set_level(logging.DEBUG)
    _override(_client(httpx.MockTransport(lambda r: httpx.Response(500))))
    response = api.post(URL, json={"zip_code": bad})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "zip_code MUST be exactly 5 digits"
    assert bad not in response.text if bad else True
    _assert_no_sentinel(caplog, response.text)


def test_bad_zip_is_422_even_when_not_configured(api: TestClient) -> None:
    _override(None)
    response = api.post(URL, json={"zip_code": "9753"})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "zip_code MUST be exactly 5 digits"


def test_invalid_body_detail_is_empty(api: TestClient) -> None:
    _override(None)
    for body in ({"zip_code": 97531}, {"zip_code": SENTINEL_ZIP, "extra": 1}, {}):
        response = api.post(URL, json=body)
        assert response.status_code == 422
        assert response.json()["error"]["detail"] == []
        assert SENTINEL_ZIP not in response.text


def test_get_is_405_and_query_zip_unused(api: TestClient) -> None:
    _override(None)
    assert api.get(URL, params={"zip_code": SENTINEL_ZIP}).status_code == 405
    response = api.post(URL, params={"zip_code": SENTINEL_ZIP}, json={})
    assert response.status_code == 422


CONNECT = "/grocery/kroger/connect"
CALLBACK = "/grocery/kroger/callback"
CONNECTION = "/grocery/kroger/connection"
REDIRECT = "http://localhost:8010/grocery/kroger/callback"
REDIRECT_HOST = "localhost:8010"
RETURN_URL = "http://127.0.0.1:5173/prototype"
CLIENT_ID = "SENTINEL-CLIENT-ID"
CLIENT_SECRET = "SENTINEL-CLIENT-SECRET"
CODE = "SENTINEL-AUTH-CODE"
ACCESS = "SENTINEL-ACCESS-TOKEN"
REFRESH = "SENTINEL-REFRESH-TOKEN"


@dataclass
class Rig:
    api: TestClient
    session: Session
    key: bytes
    cipher: Fernet
    token_status: int = 200
    expires_in: int = 1800
    token_calls: list[httpx.Request] = field(default_factory=list)
    token_body: dict[str, object] | None = None
    cart_status: int = 204
    cart_error: Exception | None = None
    cart_calls: list[httpx.Request] = field(default_factory=list)
    products: dict[str, list[object]] = field(default_factory=dict)
    products_status: int = 200

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/cart/add":
            self.cart_calls.append(request)
            if self.cart_error is not None:
                raise self.cart_error
            return httpx.Response(self.cart_status)
        if request.url.path == "/v1/products":
            term = request.url.params["filter.term"]
            if self.products_status != 200:
                return httpx.Response(self.products_status)
            return httpx.Response(200, json={"data": self.products.get(term, [])})
        self.token_calls.append(request)
        if self.token_status != 200:
            return httpx.Response(self.token_status)
        body = self.token_body or {
            "access_token": ACCESS,
            "refresh_token": REFRESH,
            "expires_in": self.expires_in,
        }
        return httpx.Response(200, json=body)


@pytest.fixture
def rig(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Rig]:
    seed_user(DEMO_USER_ID)
    monkeypatch.setattr(session, "commit", session.flush)
    key = Fernet.generate_key()
    rig = Rig(client, session, key, Fernet(key))
    http = httpx.Client(transport=httpx.MockTransport(rig.handle))
    kroger_client = KrogerClient(
        CLIENT_ID,
        CLIENT_SECRET,
        base_url=kroger.HOSTS["certification"],
        client=http,
    )
    settings = GroceryProviderSettings(
        kroger_redirect_uri=REDIRECT, kroger_return_url=RETURN_URL
    )
    overrides = {
        get_kroger_client: lambda: kroger_client,
        get_kroger_cipher: lambda: rig.cipher,
        get_provider_settings: lambda: settings,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield rig
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


def _connect(rig: Rig, host: str = REDIRECT_HOST) -> httpx.Response:
    return rig.api.get(CONNECT, headers={"host": host}, follow_redirects=False)


def _cookie_nonce(response: httpx.Response) -> str:
    name, _, value = response.headers["set-cookie"].split(";", 1)[0].partition("=")
    assert name == STATE_COOKIE
    return value


def _begin(rig: Rig) -> tuple[str, str]:
    """Run /connect and return the cookie nonce and the state sent to Kroger."""
    response = _connect(rig)
    assert response.status_code == 302
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    return _cookie_nonce(response), state


def _callback(rig: Rig, nonce: str | None, **params: str) -> httpx.Response:
    headers = {} if nonce is None else {"cookie": f"{STATE_COOKIE}={nonce}"}
    return rig.api.get(CALLBACK, params=params, headers=headers, follow_redirects=False)


def _row_count(rig: Rig) -> int:
    count = rig.session.scalar(select(func.count()).select_from(KrogerCustomerToken))
    assert count is not None
    return count


@pytest.mark.parametrize("missing", [get_kroger_client, get_kroger_cipher])
def test_connect_is_503_when_not_configured(rig: Rig, missing: object) -> None:
    app.dependency_overrides[missing] = lambda: None
    response = _connect(rig)
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Kroger is not configured"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "host", ["testserver", "127.0.0.1:8010", "localhost:9999", "localhost"]
)
def test_connect_from_another_host_goes_to_the_redirect_origin(
    rig: Rig, host: str
) -> None:
    response = _connect(rig, host)
    assert response.status_code == 302
    origin = f"http://{REDIRECT_HOST}"
    assert response.headers["location"] == f"{origin}{COOKIE_PATH}/connect"
    assert "set-cookie" not in response.headers


def test_connect_sets_the_state_cookie_and_redirects_to_kroger(rig: Rig) -> None:
    response = _connect(rig)
    assert response.status_code == 302
    attributes = [a.strip().lower() for a in response.headers["set-cookie"].split(";")]
    for expected in ("httponly", "samesite=lax", f"path={COOKIE_PATH}", "max-age=600"):
        assert expected in attributes
    assert "secure" not in attributes
    nonce = _cookie_nonce(response)
    target = urlsplit(response.headers["location"])
    assert (target.scheme, target.netloc, target.path) == (
        "https",
        "api-ce.kroger.com",
        "/v1/connect/oauth2/authorize",
    )
    query = parse_qs(target.query)
    state = query.pop("state")[0]
    assert query == {
        "scope": ["cart.basic:write profile.compact"],
        "response_type": ["code"],
        "client_id": [CLIENT_ID],
        "redirect_uri": [REDIRECT],
    }
    assert nonce not in state
    assert state_matches(rig.cipher, state, nonce) is True


def test_callback_round_trip_stores_encrypted_tokens(rig: Rig) -> None:
    nonce, state = _begin(rig)
    response = _callback(rig, nonce, code=CODE, state=state)
    assert response.status_code == 302
    assert response.headers["location"] == f"{RETURN_URL}?kroger=connected"
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(STATE_COOKIE)
    assert "max-age=0" in cookie
    assert "path=/grocery/kroger" in cookie
    assert _row_count(rig) == 1
    row = rig.session.get(KrogerCustomerToken, DEMO_USER_ID)
    assert row is not None
    assert ACCESS.encode() not in row.access_token
    assert REFRESH.encode() not in row.refresh_token
    assert rig.cipher.decrypt(row.access_token).decode() == ACCESS
    assert rig.cipher.decrypt(row.refresh_token).decode() == REFRESH
    assert len(rig.token_calls) == 1
    assert parse_qs(rig.token_calls[0].content.decode()) == {
        "grant_type": ["authorization_code"],
        "code": [CODE],
        "redirect_uri": [REDIRECT],
    }


def _assert_failed(rig: Rig, response: httpx.Response, *, exchanges: int) -> None:
    assert response.status_code == 302
    assert response.headers["location"] == f"{RETURN_URL}?kroger=error"
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert _row_count(rig) == 0
    assert len(rig.token_calls) == exchanges


def test_replayed_callback_without_the_cookie_fails(rig: Rig) -> None:
    nonce, state = _begin(rig)
    first = _callback(rig, nonce, code=CODE, state=state)
    assert first.headers["location"] == f"{RETURN_URL}?kroger=connected"
    rig.api.cookies.clear()
    replay = _callback(rig, None, code=CODE, state=state)
    assert replay.status_code == 302
    assert replay.headers["location"] == f"{RETURN_URL}?kroger=error"
    assert _row_count(rig) == 1
    row = rig.session.get(KrogerCustomerToken, DEMO_USER_ID)
    assert row is not None
    assert rig.cipher.decrypt(row.access_token).decode() == ACCESS
    assert rig.cipher.decrypt(row.refresh_token).decode() == REFRESH
    assert len(rig.token_calls) == 1


@pytest.mark.parametrize("missing", [get_kroger_client, get_kroger_cipher])
def test_callback_is_an_error_when_not_configured(rig: Rig, missing: object) -> None:
    nonce, state = _begin(rig)
    app.dependency_overrides[missing] = lambda: None
    _assert_failed(rig, _callback(rig, nonce, code=CODE, state=state), exchanges=0)


def test_callback_fails_when_the_token_expiry_is_absurd(rig: Rig) -> None:
    nonce, state = _begin(rig)
    rig.expires_in = 10**12
    _assert_failed(rig, _callback(rig, nonce, code=CODE, state=state), exchanges=1)


def test_callback_fails_when_the_database_write_fails(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("invented failure")

    monkeypatch.setattr(kroger_routes, "store_tokens", broken)
    nonce, state = _begin(rig)
    _assert_failed(rig, _callback(rig, nonce, code=CODE, state=state), exchanges=1)
    assert rig.api.get(CONNECTION).json() == {"connected": False}


def test_connect_marks_the_state_cookie_secure_for_an_https_redirect(rig: Rig) -> None:
    settings = GroceryProviderSettings(
        kroger_redirect_uri="https://localhost:8443/grocery/kroger/callback",
        kroger_return_url=RETURN_URL,
    )
    app.dependency_overrides[get_provider_settings] = lambda: settings
    response = _connect(rig, "localhost:8443")
    assert response.status_code == 302
    attributes = [a.strip().lower() for a in response.headers["set-cookie"].split(";")]
    assert "secure" in attributes


def test_callback_with_a_mismatched_cookie_fails(rig: Rig) -> None:
    _, state = _begin(rig)
    response = _callback(rig, new_nonce(), code=CODE, state=state)
    _assert_failed(rig, response, exchanges=0)


def test_callback_with_a_state_for_another_key_fails(rig: Rig) -> None:
    nonce = new_nonce()
    state = make_state(Fernet(Fernet.generate_key()), nonce)
    _assert_failed(rig, _callback(rig, nonce, code=CODE, state=state), exchanges=0)


def test_callback_with_an_expired_state_fails(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    nonce, state = _begin(rig)
    later = time.time() + STATE_TTL_SECONDS + 5
    monkeypatch.setattr(kroger_customer, "_now", lambda: later)
    _assert_failed(rig, _callback(rig, nonce, code=CODE, state=state), exchanges=0)


def test_callback_with_an_error_parameter_fails(rig: Rig) -> None:
    nonce, state = _begin(rig)
    response = _callback(rig, nonce, code=CODE, state=state, error="access_denied")
    _assert_failed(rig, response, exchanges=0)
    assert "access_denied" not in response.headers["location"]


@pytest.mark.parametrize("omit", ["code", "state"])
def test_callback_missing_a_parameter_fails(rig: Rig, omit: str) -> None:
    nonce, state = _begin(rig)
    params = {"code": CODE, "state": state}
    del params[omit]
    _assert_failed(rig, _callback(rig, nonce, **params), exchanges=0)


def test_callback_fails_when_kroger_is_unavailable_on_exchange(rig: Rig) -> None:
    nonce, state = _begin(rig)
    rig.token_status = 500
    _assert_failed(rig, _callback(rig, nonce, code=CODE, state=state), exchanges=1)


def test_connection_before_and_after_sign_in(rig: Rig) -> None:
    assert rig.api.get(CONNECTION).json() == {"connected": False}
    nonce, state = _begin(rig)
    _callback(rig, nonce, code=CODE, state=state)
    assert rig.api.get(CONNECTION).json() == {"connected": True}


def test_connection_stays_false_after_a_failed_sign_in(rig: Rig) -> None:
    nonce, state = _begin(rig)
    rig.token_status = 429
    _callback(rig, nonce, code=CODE, state=state)
    assert rig.api.get(CONNECTION).json() == {"connected": False}


def test_sign_in_never_logs_or_echoes_secrets(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    second_code = "SENTINEL-SECOND-CODE"
    nonce, state = _begin(rig)
    connected = _callback(rig, nonce, code=CODE, state=state)
    rig.token_status = 500
    second_nonce, second_state = _begin(rig)
    failed = _callback(rig, second_nonce, code=second_code, state=second_state)
    assert connected.headers["location"].endswith("kroger=connected")
    assert failed.headers["location"].endswith("kroger=error")
    redact_access_log()
    caplog.set_level(logging.INFO, logger="uvicorn.access")
    for response in (connected, failed):
        target = response.request.url.raw_path.decode()
        assert "code=" in target
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", target, "1.1", 302
        )
    access = [r for r in caplog.records if r.name == "uvicorn.access"]
    assert len(access) == 2
    assert all(CALLBACK in r.getMessage() for r in access)
    assert caplog.records
    haystack = [
        caplog.text,
        connected.text,
        failed.text,
        connected.headers["location"],
        failed.headers["location"],
        *(record.getMessage() for record in caplog.records),
        *(str(record.args) for record in caplog.records),
    ]
    secrets = [
        CODE,
        second_code,
        state,
        second_state,
        nonce,
        second_nonce,
        ACCESS,
        REFRESH,
        CLIENT_ID,
        CLIENT_SECRET,
        rig.key.decode(),
    ]
    for secret in secrets:
        assert all(secret not in text for text in haystack)


PREVIEW = "/grocery/kroger/cart/preview"
CART_ADD = "/grocery/kroger/cart/add"
NEW_ACCESS = "SENTINEL-NEW-ACCESS-TOKEN"
NEW_REFRESH = "SENTINEL-NEW-REFRESH-TOKEN"
UPC_A = "0001112223334"
UPC_B = "12345678"
PANTRY = ["olive_oil", "cumin", "salt"]
SOME_ID = "00000000-0000-0000-0000-000000000001"
LINES = [{"upc": UPC_A, "quantity": 2}, {"upc": UPC_B, "quantity": 1}]


def _sign_in(rig: Rig, *, expires_in: int = 1800) -> KrogerCustomerToken:
    tokens = CustomerTokens(ACCESS, REFRESH, 1800)
    store_tokens(rig.session, DEMO_USER_ID, rig.cipher, tokens)
    row = rig.session.get(KrogerCustomerToken, DEMO_USER_ID)
    assert row is not None
    row.access_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    rig.session.flush()
    return row


def _stored(rig: Rig) -> tuple[str, str]:
    row = rig.session.get(KrogerCustomerToken, DEMO_USER_ID)
    assert row is not None
    return (
        rig.cipher.decrypt(row.access_token).decode(),
        rig.cipher.decrypt(row.refresh_token).decode(),
    )


def _plan(rig: Rig, user_id: int = DEMO_USER_ID) -> UUID:
    revision_id = uuid4()
    snapshot: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
        "pantry_ingredient_ids": PANTRY,
        "plan_cap_cents": None,
    }
    rig.session.add(PlanRevision(id=revision_id, user_id=user_id, snapshot=snapshot))
    rig.session.flush()
    return revision_id


def _product(upc: str, description: str) -> object:
    return {
        "productId": f"id-{upc}",
        "upc": upc,
        "description": description,
        "items": [{"size": "1 lb"}],
    }


def _add(rig: Rig, items: object = LINES) -> httpx.Response:
    return rig.api.post(CART_ADD, json={"items": items})


def _message(response: httpx.Response) -> str:
    message: str = response.json()["error"]["message"]
    return message


def test_disconnect_deletes_the_tokens_and_is_always_204(rig: Rig) -> None:
    assert rig.api.delete(CONNECTION).status_code == 204
    _sign_in(rig)
    response = rig.api.delete(CONNECTION)
    assert response.status_code == 204
    assert response.content == b""
    assert _row_count(rig) == 0
    assert rig.api.get(CONNECTION).json() == {"connected": False}
    assert rig.api.delete(CONNECTION).status_code == 204
    assert rig.token_calls == [] and rig.cart_calls == []


def test_preview_returns_matched_and_unmatched_lines_in_order(rig: Rig) -> None:
    revision_id = _plan(rig)
    rig.products[kroger_search_term("chicken_breast")] = [
        _product("1234567", "Too short"),
        _product(UPC_A, "Invented Chicken"),
    ]
    rig.products[kroger_search_term("salsa")] = [_product(UPC_B, "Invented Salsa")]
    response = rig.api.post(
        PREVIEW, json={"plan_revision_id": str(revision_id), "location_id": "01234567"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "ingredient_id": "chicken_breast",
                "name": "chicken breast",
                "upc": UPC_A,
                "description": "Invented Chicken",
                "size": "1 lb",
                "quantity": 1,
            },
            {
                "ingredient_id": "salsa",
                "name": "salsa",
                "upc": UPC_B,
                "description": "Invented Salsa",
                "size": "1 lb",
                "quantity": 1,
            },
        ],
        "unmatched": [
            {"ingredient_id": "onion", "name": "onion"},
            {"ingredient_id": "tortillas", "name": "corn tortillas"},
        ],
    }


def test_preview_writes_nothing(rig: Rig) -> None:
    revision_id = _plan(rig)
    rig.products[kroger_search_term("onion")] = [_product(UPC_A, "Invented Onion")]
    before = rig.session.scalar(select(func.count()).select_from(PlanRevision))
    response = rig.api.post(
        PREVIEW, json={"plan_revision_id": str(revision_id), "location_id": "01234567"}
    )
    assert response.status_code == 200
    assert rig.session.scalar(select(func.count()).select_from(PlanRevision)) == before
    assert _row_count(rig) == 0
    assert not rig.session.new and not rig.session.dirty


def test_preview_is_503_without_a_partial_result_when_kroger_fails(rig: Rig) -> None:
    revision_id = _plan(rig)
    rig.products_status = 500
    response = rig.api.post(
        PREVIEW, json={"plan_revision_id": str(revision_id), "location_id": "01234567"}
    )
    assert response.status_code == 503
    assert _message(response) == "Kroger is unavailable"
    assert "items" not in response.text


def test_preview_is_404_for_an_unknown_or_foreign_revision(
    rig: Rig, seed_user: UserSeeder
) -> None:
    seed_user(2)
    foreign = _plan(rig, user_id=2)
    for revision_id in (uuid4(), foreign):
        response = rig.api.post(
            PREVIEW,
            json={"plan_revision_id": str(revision_id), "location_id": "01234567"},
        )
        assert response.status_code == 404
    assert rig.token_calls == []


def test_preview_is_503_when_not_configured(rig: Rig) -> None:
    app.dependency_overrides[get_kroger_client] = lambda: None
    response = rig.api.post(
        PREVIEW, json={"plan_revision_id": str(_plan(rig)), "location_id": "01234567"}
    )
    assert response.status_code == 503
    assert _message(response) == "Kroger is not configured"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"plan_revision_id": SOME_ID},
        {"location_id": "01234567"},
        {"plan_revision_id": "not-a-uuid", "location_id": "01234567"},
        {"plan_revision_id": SOME_ID, "location_id": "0123456"},
        {"plan_revision_id": SOME_ID, "location_id": "012345678"},
        {"plan_revision_id": SOME_ID, "location_id": "0123456!"},
        {"plan_revision_id": SOME_ID, "location_id": "01234567\n"},
        {"plan_revision_id": SOME_ID, "location_id": 12345678},
        {"plan_revision_id": SOME_ID, "location_id": "01234567", "extra": 1},
    ],
)
def test_preview_rejects_a_bad_body(rig: Rig, body: dict[str, object]) -> None:
    response = rig.api.post(PREVIEW, json=body)
    assert response.status_code == 422
    assert rig.token_calls == []


def test_cart_add_sends_the_exact_body_with_a_fresh_token(rig: Rig) -> None:
    _sign_in(rig)
    response = _add(rig)
    assert response.status_code == 204
    assert response.content == b""
    assert rig.token_calls == []
    assert len(rig.cart_calls) == 1
    request = rig.cart_calls[0]
    assert request.method == "PUT"
    assert request.headers["authorization"] == f"Bearer {ACCESS}"
    assert json.loads(request.content) == {"items": LINES}


def test_cart_add_refreshes_an_expired_token_first(rig: Rig) -> None:
    _sign_in(rig, expires_in=-5)
    rig.token_body = {
        "access_token": NEW_ACCESS,
        "refresh_token": NEW_REFRESH,
        "expires_in": 1800,
    }
    assert _add(rig).status_code == 204
    assert len(rig.token_calls) == 1
    assert parse_qs(rig.token_calls[0].content.decode()) == {
        "grant_type": ["refresh_token"],
        "refresh_token": [REFRESH],
    }
    assert rig.cart_calls[0].headers["authorization"] == f"Bearer {NEW_ACCESS}"
    assert _stored(rig) == (NEW_ACCESS, NEW_REFRESH)


def test_cart_add_is_409_when_not_connected(rig: Rig) -> None:
    response = _add(rig)
    assert response.status_code == 409
    assert _message(response) == "Kroger account is not connected"
    assert rig.token_calls == [] and rig.cart_calls == []


def test_cart_add_is_503_when_the_refresh_fails_and_keeps_the_row(rig: Rig) -> None:
    _sign_in(rig, expires_in=-5)
    rig.token_status = 500
    response = _add(rig)
    assert response.status_code == 503
    assert _message(response) == "Kroger is unavailable"
    assert rig.cart_calls == []
    assert _stored(rig) == (ACCESS, REFRESH)


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_cart_add_is_503_when_kroger_rejects_the_add(rig: Rig, status: int) -> None:
    _sign_in(rig)
    rig.cart_status = status
    response = _add(rig)
    assert response.status_code == 503
    assert _message(response) == "Kroger is unavailable"
    assert len(rig.cart_calls) == 1


def test_cart_add_is_503_when_the_connection_fails_before_sending(rig: Rig) -> None:
    _sign_in(rig)
    rig.cart_error = httpx.ConnectError("refused")
    assert _add(rig).status_code == 503


def test_cart_add_is_504_when_kroger_does_not_confirm(rig: Rig) -> None:
    _sign_in(rig)
    rig.cart_error = httpx.ReadTimeout("slow")
    response = _add(rig)
    assert response.status_code == 504
    assert _message(response) == "Kroger did not confirm the cart add"
    assert len(rig.cart_calls) == 1


@pytest.mark.parametrize("missing", [get_kroger_client, get_kroger_cipher])
def test_cart_add_is_503_when_not_configured(rig: Rig, missing: object) -> None:
    _sign_in(rig)
    app.dependency_overrides[missing] = lambda: None
    response = _add(rig)
    assert response.status_code == 503
    assert _message(response) == "Kroger is not configured"
    assert rig.cart_calls == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"items": []},
        {"items": [{"upc": f"{n:08d}", "quantity": 1} for n in range(31)]},
        {"items": [{"upc": UPC_A, "quantity": 0}]},
        {"items": [{"upc": UPC_A, "quantity": 11}]},
        {"items": [{"upc": UPC_A, "quantity": "2"}]},
        {"items": [{"upc": UPC_A, "quantity": True}]},
        {"items": [{"upc": UPC_A}]},
        {"items": [{"upc": "1234567", "quantity": 1}]},
        {"items": [{"upc": "123456789012345", "quantity": 1}]},
        {"items": [{"upc": "1234567a", "quantity": 1}]},
        {"items": [{"upc": "12345678\n", "quantity": 1}]},
        {"items": [{"upc": 12345678, "quantity": 1}]},
        {"items": [{"upc": UPC_A, "quantity": 1}, {"upc": UPC_A, "quantity": 2}]},
        {"items": [{"upc": UPC_A, "quantity": 1, "extra": 1}]},
        {"items": [{"upc": UPC_A, "quantity": 1}], "extra": 1},
    ],
)
def test_cart_add_rejects_a_bad_body(rig: Rig, body: dict[str, object]) -> None:
    _sign_in(rig)
    response = rig.api.post(CART_ADD, json=body)
    assert response.status_code == 422
    assert rig.cart_calls == []


def test_cart_add_accepts_30_items_and_the_quantity_bounds(rig: Rig) -> None:
    _sign_in(rig)
    items = [{"upc": f"{n:08d}", "quantity": 1 + n % 10} for n in range(30)]
    assert _add(rig, items).status_code == 204
    assert json.loads(rig.cart_calls[0].content) == {"items": items}


def test_cart_flow_never_logs_or_echoes_secrets(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _sign_in(rig, expires_in=-5)
    rig.token_body = {
        "access_token": NEW_ACCESS,
        "refresh_token": NEW_REFRESH,
        "expires_in": 1800,
    }
    responses = [_add(rig)]
    rig.cart_status = 500
    responses.append(_add(rig))
    rig.cart_status = 204
    rig.cart_error = httpx.ReadTimeout(f"{NEW_ACCESS} {CLIENT_SECRET}")
    responses.append(_add(rig))
    rig.cart_error = None
    _sign_in(rig, expires_in=-5)
    rig.token_status = 500
    responses.append(_add(rig))
    assert [r.status_code for r in responses] == [204, 503, 504, 503]
    haystack = [
        caplog.text,
        *(r.text for r in responses),
        *(str(r.headers) for r in responses),
        *(record.getMessage() for record in caplog.records),
        *(str(record.args) for record in caplog.records),
    ]
    secrets = [
        ACCESS,
        REFRESH,
        NEW_ACCESS,
        NEW_REFRESH,
        CLIENT_ID,
        CLIENT_SECRET,
        rig.key.decode(),
    ]
    for secret in secrets:
        assert all(secret not in text for text in haystack)
