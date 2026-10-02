"""Test the Spoonacular estimatedCost HTTP adapter."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.providers.spoonacular import (
    BASE_URL,
    CACHE_SECONDS,
    INFORMATION_PATH,
    SpoonacularEstimateProvider,
    SpoonacularUnavailable,
    _parse_estimated_cents,
)

API_KEY = "TEST_SPOONACULAR_KEY_MARKER"
INGREDIENT_ID = 1001
AMOUNT = 2
UNIT = "g"
SUCCESS_BODY = json.dumps(
    {"estimatedCost": {"value": 299.4, "unit": "US Cents"}}
).encode()
CENTS_BODY = json.dumps({"estimatedCost": {"value": 26.41, "unit": "cents"}}).encode()
NEGATIVE_BODY = json.dumps(
    {"estimatedCost": {"value": -1, "unit": "US Cents"}}
).encode()
INFORMATION_URL = f"{BASE_URL}{INFORMATION_PATH.format(id=INGREDIENT_ID)}"
LEAK_MARKERS = (
    API_KEY,
    "SECRET_TRANSPORT_MARKER",
    "SECRET_ERROR_BODY",
)
UNAVAILABLE = "Spoonacular estimate is unavailable"


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    clock: Callable[[], float] | None = None,
) -> tuple[SpoonacularEstimateProvider, httpx.Client]:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    )
    provider = SpoonacularEstimateProvider(
        API_KEY,
        client=client,
        clock=(lambda: 0.0) if clock is None else clock,
    )
    return provider, client


def assert_static_error(error: BaseException, message: str) -> None:
    assert str(error) == message
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = str(error) + repr(error)
    for marker in LEAK_MARKERS:
        assert marker not in rendered


def test_us_cents_rounds_to_int() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    try:
        cents = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert cents == 299
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url.copy_with(query=None)) == INFORMATION_URL
    assert request.url.params["apiKey"] == API_KEY
    assert request.url.params["amount"] == str(AMOUNT)
    assert request.url.params["unit"] == UNIT


def test_cents_unit_rounds_to_int_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=CENTS_BODY)

    provider, client = make_provider(handler)
    try:
        cents = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert cents == 26


@pytest.mark.parametrize(
    "estimated_cost",
    [
        {"value": 26.41, "unit": "dollars"},
        {"value": 26.41, "unit": "Cents"},
        {"value": 26.41, "unit": ""},
        {"value": 26.41},
        {"value": 26.41, "unit": []},
        {"value": 26.41, "unit": {}},
    ],
)
def test_unrecognized_or_missing_unit_returns_none(
    estimated_cost: dict[str, object],
) -> None:
    assert _parse_estimated_cents({"estimatedCost": estimated_cost}) is None


def test_second_call_within_cache_window_does_not_get() -> None:
    requests: list[httpx.Request] = []
    now = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler, clock=lambda: now[0])
    try:
        first = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        now[0] = CACHE_SECONDS - 1
        second = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert first == 299
    assert second == 299
    assert len(requests) == 1


def test_call_after_cache_window_gets_again() -> None:
    requests: list[httpx.Request] = []
    now = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler, clock=lambda: now[0])
    try:
        first = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        now[0] = CACHE_SECONDS
        second = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert first == 299
    assert second == 299
    assert len(requests) == 2


def test_timeout_raises_unavailable() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.TimeoutException("SECRET_TRANSPORT_MARKER", request=request)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(SpoonacularUnavailable) as raised:
            provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, UNAVAILABLE)


def test_http_401_raises_unavailable() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, content=b"SECRET_ERROR_BODY")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(SpoonacularUnavailable) as raised:
            provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert_static_error(raised.value, UNAVAILABLE)


def test_api_key_marker_is_absent_from_exception_strings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("SECRET_TRANSPORT_MARKER", request=request)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(SpoonacularUnavailable) as raised:
            provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, UNAVAILABLE)
    assert API_KEY not in str(raised.value)
    assert API_KEY not in repr(raised.value)


def test_negative_cost_value_returns_none_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=NEGATIVE_BODY)

    provider, client = make_provider(handler)
    try:
        cents = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert cents is None


def test_blank_api_key_is_rejected_without_echo() -> None:
    with pytest.raises(ValueError) as blank:
        SpoonacularEstimateProvider("")
    assert str(blank.value) == "api_key MUST be a nonblank string"
    assert blank.value.__cause__ is None
    assert blank.value.__context__ is None

    with pytest.raises(ValueError) as spaces:
        SpoonacularEstimateProvider("   ")
    assert str(spaces.value) == "api_key MUST be a nonblank string"
    assert API_KEY not in str(spaces.value)
