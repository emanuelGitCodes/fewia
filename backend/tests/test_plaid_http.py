"""Test the Plaid Sandbox HTTP sync adapter."""

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import date

import httpx
import pytest

from app.providers.plaid import (
    PlaidNotReady,
    PlaidSandboxProvider,
    PlaidSyncMutation,
    PlaidUnavailable,
)
from app.providers.plaid_contract import InvalidPlaidResponse, TransactionData

CLIENT_ID = "TEST_CLIENT_ID_MARKER"
SECRET = "TEST_SECRET_MARKER"
ACCESS_TOKEN = "TEST_ACCESS_TOKEN_MARKER"
CREDENTIAL_REF = "plaid-item-ref"
SYNC_URL = "https://sandbox.plaid.com/transactions/sync"
SUCCESS_BODY = (
    "{"
    '"added":[{'
    '"transaction_id":"txn-1",'
    '"account_id":"acct-1",'
    '"amount":12.34,'
    '"iso_currency_code":"USD",'
    '"date":"2026-09-06",'
    '"pending":false,'
    '"pending_transaction_id":null,'
    '"personal_finance_category":{"detailed":"FOOD_AND_DRINK_GROCERIES"},'
    '"merchant_name":"SECRET_MERCHANT_MARKER"'
    "}],"
    '"modified":[{'
    '"transaction_id":"txn-2",'
    '"account_id":"acct-1",'
    '"amount":-5.67,'
    '"iso_currency_code":"USD",'
    '"date":"2026-09-06",'
    '"pending":true,'
    '"pending_transaction_id":"txn-1",'
    '"personal_finance_category":{"detailed":"OTHER"}'
    "}],"
    '"removed":[{"transaction_id":"txn-removed"}],'
    '"next_cursor":"cursor-2",'
    '"has_more":true,'
    '"transactions_update_status":"HISTORICAL_UPDATE_COMPLETE"'
    "}"
)
INCOMPLETE_STATUSES: tuple[str | None, ...] = (
    None,
    "NOT_READY",
    "INITIAL_UPDATE_COMPLETE",
    "TRANSACTIONS_UPDATE_STATUS_UNKNOWN",
    "UNEXPECTED_STATUS",
)
LEAK_MARKERS = (
    CLIENT_ID,
    SECRET,
    ACCESS_TOKEN,
    "SECRET_MERCHANT_MARKER",
    "SECRET_TRANSPORT_MARKER",
    "SECRET_ERROR_BODY",
)


def resolve(credential_ref: str) -> str:
    if credential_ref != CREDENTIAL_REF:
        return ""
    return ACCESS_TOKEN


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    follow_redirects: bool = False,
    resolver: Callable[[str], str] = resolve,
) -> tuple[PlaidSandboxProvider, httpx.Client]:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=follow_redirects,
        trust_env=False,
    )
    provider = PlaidSandboxProvider(CLIENT_ID, SECRET, resolver, client=client)
    return provider, client


def request_payload(request: httpx.Request) -> dict[str, object]:
    payload: object = json.loads(request.content)
    assert isinstance(payload, dict)
    return payload


def assert_static_error(error: BaseException, message: str) -> None:
    assert str(error) == message
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = str(error) + repr(error)
    for marker in LEAK_MARKERS:
        assert marker not in rendered


def body_with_status(status: str | None, *, empty: bool) -> bytes:
    if empty:
        payload: dict[str, object] = {
            "added": [],
            "modified": [],
            "removed": [],
            "next_cursor": "cursor-empty",
            "has_more": False,
        }
    else:
        loaded: object = json.loads(SUCCESS_BODY)
        assert isinstance(loaded, dict)
        payload = loaded
    if status is None:
        payload.pop("transactions_update_status", None)
    else:
        payload["transactions_update_status"] = status
    return json.dumps(payload).encode()


def test_first_page_posts_sandbox_sync_without_cursor() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY.encode())

    provider, client = make_provider(handler)
    try:
        page = provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == SYNC_URL
    payload = request_payload(request)
    assert payload == {
        "client_id": CLIENT_ID,
        "secret": SECRET,
        "access_token": ACCESS_TOKEN,
        "count": 500,
    }
    assert "cursor" not in payload
    assert page.next_cursor == "cursor-2"
    assert page.has_more is True
    assert page.removed_ids == ("txn-removed",)


def test_cursor_is_sent_only_when_provided() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY.encode())

    provider, client = make_provider(handler)
    try:
        provider.sync_page(CREDENTIAL_REF, "cursor-1")
        provider.sync_page(CREDENTIAL_REF, "cursor-1")
    finally:
        provider.close()
        client.close()

    assert len(requests) == 2
    first = request_payload(requests[0])
    second = request_payload(requests[1])
    assert first["cursor"] == "cursor-1"
    assert first == second


def test_json_decimal_amounts_normalize_to_exact_cents() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY.encode())

    provider, client = make_provider(handler)
    try:
        page = provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert page.added[0] == TransactionData(
        transaction_id="txn-1",
        account_id="acct-1",
        amount_cents=1234,
        currency="USD",
        transaction_date=date(2026, 9, 6),
        pending=False,
        pending_transaction_id=None,
        is_grocery=True,
        classification_version="plaid-pfc-v1",
    )
    assert page.modified[0].amount_cents == -567
    blob = repr(asdict(page.added[0])) + repr(asdict(page.modified[0]))
    for marker in LEAK_MARKERS:
        assert marker not in blob


def test_redirects_are_not_followed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host != "sandbox.plaid.com":
            raise AssertionError("redirect followed")
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.example/steal"},
        )

    provider, client = make_provider(handler)
    try:
        with pytest.raises(PlaidUnavailable) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, "Plaid Sandbox is unavailable")


def test_transport_failure_is_one_attempt_and_static() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ConnectError("SECRET_TRANSPORT_MARKER", request=request)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(PlaidUnavailable) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, "Plaid Sandbox is unavailable")


def test_mutation_during_pagination_is_classified() -> None:
    body = json.dumps(
        {
            "error_code": "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION",
            "error_message": ACCESS_TOKEN,
        }
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(400, content=body)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(PlaidSyncMutation) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Plaid sync mutated during pagination")


def test_non_200_status_is_static_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, content=b"SECRET_ERROR_BODY")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(PlaidUnavailable) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Plaid Sandbox is unavailable")


def test_malformed_json_is_static_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"{not-json SECRET_ERROR_BODY")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InvalidPlaidResponse) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Invalid Plaid sync response")


def test_malformed_sync_page_is_static_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=(
                b'{"added":"SECRET_ERROR_BODY",'
                b'"transactions_update_status":"HISTORICAL_UPDATE_COMPLETE"}'
            ),
        )

    provider, client = make_provider(handler)
    try:
        with pytest.raises(InvalidPlaidResponse) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "Invalid Plaid sync response")


def test_owned_client_uses_fixed_sandbox_http_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr("app.providers.plaid.httpx.HTTPTransport", FakeTransport)
    monkeypatch.setattr("app.providers.plaid.httpx.Client", FakeClient)
    provider = PlaidSandboxProvider(CLIENT_ID, SECRET, resolve)
    provider.close()

    assert captured["base_url"] == "https://sandbox.plaid.com"
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
        return httpx.Response(200, content=SUCCESS_BODY.encode())

    provider, client = make_provider(handler)
    provider.close()
    page = provider.sync_page(CREDENTIAL_REF, None)
    client.close()
    assert page.next_cursor == "cursor-2"


def test_blank_credentials_are_rejected_without_echo() -> None:
    with pytest.raises(ValueError) as raised:
        PlaidSandboxProvider("", SECRET, resolve)
    assert SECRET not in str(raised.value)
    assert "client_id" in str(raised.value)

    with pytest.raises(ValueError) as raised_secret:
        PlaidSandboxProvider(CLIENT_ID, "   ", resolve)
    assert CLIENT_ID not in str(raised_secret.value)


def test_access_token_is_resolved_only_at_request_time() -> None:
    seen: list[str] = []

    def tracking_resolve(credential_ref: str) -> str:
        seen.append(credential_ref)
        return ACCESS_TOKEN

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY.encode())

    provider, client = make_provider(handler, resolver=tracking_resolve)
    try:
        assert seen == []
        provider.sync_page(CREDENTIAL_REF, None)
        assert seen == [CREDENTIAL_REF]
    finally:
        provider.close()
        client.close()


def test_injected_redirecting_client_does_not_follow_cross_origin() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host != "sandbox.plaid.com":
            raise AssertionError("cross-origin request")
        return httpx.Response(
            307,
            headers={"Location": "https://attacker.example/steal"},
        )

    provider, client = make_provider(handler, follow_redirects=True)
    try:
        with pytest.raises(PlaidUnavailable) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert str(requests[0].url) == SYNC_URL
    assert_static_error(raised.value, "Plaid Sandbox is unavailable")


def test_token_resolver_error_is_static() -> None:
    def exploding_resolve(credential_ref: str) -> str:
        raise RuntimeError(f"{SECRET} {credential_ref} SECRET_TRANSPORT_MARKER")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise AssertionError("request sent")

    provider, client = make_provider(handler, resolver=exploding_resolve)
    try:
        with pytest.raises(ValueError) as raised:
            provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, "access_token MUST be a nonblank string")


def test_each_post_sets_timeout_and_disables_redirects() -> None:
    posts: list[dict[str, object]] = []

    class RecordingClient(httpx.Client):
        def post(self, url: str | httpx.URL, **kwargs: object) -> httpx.Response:
            posts.append({"url": str(url), **kwargs})
            return super().post(url, **kwargs)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY.encode())

    client = RecordingClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        trust_env=False,
    )
    provider = PlaidSandboxProvider(CLIENT_ID, SECRET, resolve, client=client)
    try:
        provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert len(posts) == 1
    assert posts[0]["url"] == SYNC_URL
    assert posts[0]["follow_redirects"] is False
    timeout = posts[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 3.0
    assert timeout.read == 20.0
    assert timeout.write == 20.0
    assert timeout.pool == 3.0


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("status", INCOMPLETE_STATUSES)
def test_incomplete_update_does_not_return_a_sync_page(
    status: str | None, empty: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=body_with_status(status, empty=empty))

    provider, client = make_provider(handler)
    page: object = None
    try:
        with pytest.raises(PlaidNotReady) as raised:
            page = provider.sync_page(CREDENTIAL_REF, None)
        assert_static_error(raised.value, "Plaid transactions are not ready")
    finally:
        provider.close()
        client.close()
    assert page is None


def test_empty_historical_complete_page_is_returned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=body_with_status("HISTORICAL_UPDATE_COMPLETE", empty=True),
        )

    provider, client = make_provider(handler)
    try:
        page = provider.sync_page(CREDENTIAL_REF, None)
    finally:
        provider.close()
        client.close()

    assert page.added == ()
    assert page.modified == ()
    assert page.removed_ids == ()
    assert page.next_cursor == "cursor-empty"
    assert page.has_more is False
