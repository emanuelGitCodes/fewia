"""Test the Instacart development products_link adapter."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.providers.instacart import (
    PRODUCTS_LINK_URL,
    InstacartDevelopmentProvider,
    InstacartRejected,
    InstacartUncertain,
    validate_link_url,
)

API_KEY = "TEST_API_KEY_MARKER"
SUCCESS_URL = "https://www.instacart.com/store/lists/demo?retailer_key=abc"
SUCCESS_BODY = json.dumps({"products_link_url": SUCCESS_URL}).encode()
PAYLOAD: dict[str, object] = {
    "line_item_measurements": [{"name": "beans", "quantity": 2}],
    "postal_code": "10001",
    "marker": "PAYLOAD_SECRET_MARKER",
}
LEAK_MARKERS = (
    API_KEY,
    "PAYLOAD_SECRET_MARKER",
    "SECRET_TRANSPORT_MARKER",
    "SECRET_ERROR_BODY",
    "SECRET_REDIRECT_MARKER",
)
UNSAFE_URLS: tuple[object, ...] = (
    None,
    1,
    [],
    {},
    "",
    "   ",
    "https://example.com/products_link",
    "https://example.com/store/lists/demo",
    "http://www.instacart.com/store/lists/demo",
    "https://www.instacart.com.evil.com/list",
    "https://www.instacart.com./list",
    "https://instacart.com.attacker/list",
    "https://evil-instacart.com/list",
    "https://notinstacart.com/list",
    "https://www.instacart.com:8443/list",
    "https://www.instacart.com:80/list",
    "https://user@www.instacart.com/list",
    "https://user:pass@www.instacart.com/list",
    "https://@www.instacart.com/list",
    "https://www.instacart.com/list#frag",
    "https://www.instacart.com/list with space",
    "https://www.instacart.com/list\t",
    "https://www.instacart.com/list\n",
    "https://www.instacart.com/a\\b",
    "https://127.0.0.1/list",
    "https://192.168.0.1/list",
    "https://[::1]/list",
    "https://localhost/list",
    "http://localhost/list",
    "file://www.instacart.com/list",
    "ftp://www.instacart.com/list",
    "javascript:alert(1)",
    "https://www.instacart.com/a%0d%0aSet-Cookie:x",
    "https://www.instacart.com/%0a",
    "https://www.instacart.com/%00",
    "https://www.instacart.com/%09",
    "https://www.instacart.com/list?q=%09",
    "https://www.instacart.com/%01",
    "https://www.instacart.com/%1f",
    "https://www.instacart.com/%1F",
    "https://www.instacart.com/%7f",
    "https://www.instacart.com/%7F",
    "https://www.instacart.com/" + ("a" * 2048),
    "https://www.instacart.com:abc/list",
)
VALID_URLS = (
    SUCCESS_URL,
    "https://instacart.com/path",
    "https://www.instacart.ca/foo?bar=1&baz=2",
    "https://instacart.ca/",
    "https://WWW.INSTACART.COM/Path",
    "https://www.instacart.com:443/path?q=1",
    "https://www.instacart.com/" + ("a" * (2048 - 26)),
)
REJECTED_STATUSES = (400, 401, 403, 422)
UNCERTAIN_STATUSES = (201, 204, 301, 302, 307, 308, 404, 409, 429, 500, 502, 503)


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    follow_redirects: bool = False,
) -> tuple[InstacartDevelopmentProvider, httpx.Client]:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=follow_redirects,
        trust_env=False,
    )
    provider = InstacartDevelopmentProvider(API_KEY, client=client)
    return provider, client


def assert_static_error(error: BaseException, message: str) -> None:
    assert str(error) == message
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = str(error) + repr(error)
    for marker in LEAK_MARKERS:
        assert marker not in rendered


def test_create_link_posts_exact_url_method_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    try:
        url = provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert url == SUCCESS_URL
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == PRODUCTS_LINK_URL
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Content-Type"].startswith("application/json")


def test_payload_is_preserved_on_the_wire() -> None:
    original = dict(PAYLOAD)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    try:
        provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert PAYLOAD == original
    sent: object = json.loads(requests[0].content)
    assert sent == original


def test_redirects_are_not_followed_when_injected_client_follows() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host != "connect.dev.instacart.tools":
            raise AssertionError("redirect followed")
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.example/SECRET_REDIRECT_MARKER"},
        )

    provider, client = make_provider(handler, follow_redirects=True)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert str(requests[0].url) == PRODUCTS_LINK_URL
    assert_static_error(raised.value, "Instacart products_link result is uncertain")


def test_each_post_sets_timeout_and_disables_redirects() -> None:
    posts: list[dict[str, object]] = []

    class RecordingClient(httpx.Client):
        def post(self, url: str | httpx.URL, **kwargs: object) -> httpx.Response:
            posts.append({"url": str(url), **kwargs})
            return super().post(url, **kwargs)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY)

    client = RecordingClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        trust_env=False,
    )
    provider = InstacartDevelopmentProvider(API_KEY, client=client)
    try:
        provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert len(posts) == 1
    assert posts[0]["url"] == PRODUCTS_LINK_URL
    assert posts[0]["follow_redirects"] is False
    timeout = posts[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 3.0
    assert timeout.read == 20.0
    assert timeout.write == 20.0
    assert timeout.pool == 3.0


def test_owned_client_uses_fixed_http_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    transport_kwargs: dict[str, object] = {}
    closed = {"value": False}

    class FakeTransport:
        def __init__(self, **kwargs: object) -> None:
            transport_kwargs.update(kwargs)

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def close(self) -> None:
            closed["value"] = True

    monkeypatch.setattr("app.providers.instacart.httpx.HTTPTransport", FakeTransport)
    monkeypatch.setattr("app.providers.instacart.httpx.Client", FakeClient)
    provider = InstacartDevelopmentProvider(API_KEY)
    provider.close()

    assert captured["base_url"] == "https://connect.dev.instacart.tools"
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False
    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 3.0
    assert timeout.read == 20.0
    assert timeout.write == 20.0
    assert timeout.pool == 3.0
    transport = captured["transport"]
    assert isinstance(transport, FakeTransport)
    assert transport_kwargs == {"retries": 0, "trust_env": False}
    assert closed["value"] is True


def test_injected_client_is_not_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    provider.close()
    url = provider.create_link(PAYLOAD)
    client.close()
    assert url == SUCCESS_URL


def test_timeout_is_one_attempt_and_uncertain() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.TimeoutException("SECRET_TRANSPORT_MARKER", request=request)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, "Instacart products_link result is uncertain")


def test_connect_error_is_one_attempt_and_uncertain() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ConnectError("SECRET_TRANSPORT_MARKER", request=request)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, "Instacart products_link result is uncertain")


@pytest.mark.parametrize("status", UNCERTAIN_STATUSES)
def test_non_success_status_is_uncertain_after_one_call(status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, content=b"SECRET_ERROR_BODY")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, "Instacart products_link result is uncertain")


@pytest.mark.parametrize("status", REJECTED_STATUSES)
def test_explicit_client_errors_are_rejected(status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, content=b"SECRET_ERROR_BODY")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartRejected) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, "Instacart rejected the products_link request")


def test_malformed_json_is_uncertain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"{not-json SECRET_ERROR_BODY")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Instacart products_link result is uncertain")


@pytest.mark.parametrize(
    "content",
    [
        b"[]",
        b'"https://www.instacart.com/list"',
        b"{}",
        b'{"products_link_url":null}',
        b'{"products_link_url":1}',
        b'{"products_link_url":"https://example.com/list"}',
        b'{"url":"https://www.instacart.com/list"}',
        b'{"products_link_url":"https://www.instacart.com/list#x"}',
        b'{"products_link_url":"https://www.instacart.com/%09"}',
        b'{"products_link_url":"https://www.instacart.com/%7f"}',
    ],
)
def test_malformed_success_body_is_uncertain_and_does_not_fabricate(
    content: bytes,
) -> None:
    result: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=content)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            result = provider.create_link(PAYLOAD)
        assert_static_error(raised.value, "Instacart products_link result is uncertain")
    finally:
        provider.close()
        client.close()
    assert result is None


@pytest.mark.parametrize("url", VALID_URLS)
def test_validate_link_url_preserves_path_and_query(url: str) -> None:
    assert validate_link_url(url) == url
    assert len(url) <= 2048


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_validate_link_url_rejects_unsafe_values(url: object) -> None:
    with pytest.raises(ValueError) as raised:
        validate_link_url(url)
    assert_static_error(raised.value, "Instacart link URL is invalid")


def test_create_link_returns_validated_products_link_url() -> None:
    link = "https://www.instacart.ca/store/lists/keep?x=1&y=2"

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=json.dumps({"products_link_url": link, "extra": "ignore"}).encode(),
        )

    provider, client = make_provider(handler)
    try:
        assert provider.create_link(PAYLOAD) == link
    finally:
        provider.close()
        client.close()


def test_blank_and_control_api_keys_are_rejected_without_echo() -> None:
    with pytest.raises(ValueError) as blank:
        InstacartDevelopmentProvider("")
    assert str(blank.value) == "api_key MUST be a nonblank string"
    assert blank.value.__cause__ is None
    assert blank.value.__context__ is None

    with pytest.raises(ValueError) as spaces:
        InstacartDevelopmentProvider("   ")
    assert str(spaces.value) == "api_key MUST be a nonblank string"

    with pytest.raises(ValueError) as control:
        InstacartDevelopmentProvider("TEST_API_KEY_MARKER\n")
    assert str(control.value) == "api_key MUST NOT contain control characters"
    assert API_KEY not in str(control.value)
    assert control.value.__cause__ is None
    assert control.value.__context__ is None


def test_deeply_nested_json_is_static_uncertain() -> None:
    nested = ("[" * 20000 + "]" * 20000).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=nested)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Instacart products_link result is uncertain")


def test_json_loads_recursion_error_is_static_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_raw: object) -> object:
        raise RecursionError("SECRET_ERROR_BODY")

    monkeypatch.setattr("app.providers.instacart.json.loads", boom)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InstacartUncertain) as raised:
            provider.create_link(PAYLOAD)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Instacart products_link result is uncertain")
