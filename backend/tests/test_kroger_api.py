"""Tests for POST /grocery/kroger/stores, using invented data."""

import logging
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.deps import get_kroger_client
from app.main import app
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
