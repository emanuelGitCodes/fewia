"""Tests for the Kroger store lookup and sign-in routes, using invented data."""

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import UserSeeder
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import kroger_customer
from app.demo import DEMO_USER_ID
from app.deps import get_kroger_cipher, get_kroger_client, get_provider_settings
from app.kroger_customer import (
    COOKIE_PATH,
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    make_state,
    new_nonce,
    state_matches,
)
from app.kroger_models import KrogerCustomerToken
from app.main import app
from app.provider_settings import GroceryProviderSettings
from app.providers import kroger
from app.providers.kroger import KrogerClient

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
    token_calls: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.token_calls.append(request)
        if self.token_status != 200:
            return httpx.Response(self.token_status)
        body = {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 1800}
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


def test_callback_without_a_cookie_fails(rig: Rig) -> None:
    _, state = _begin(rig)
    _assert_failed(rig, _callback(rig, None, code=CODE, state=state), exchanges=0)


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
