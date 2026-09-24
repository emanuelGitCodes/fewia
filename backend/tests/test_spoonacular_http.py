"""Test the Spoonacular estimatedCost HTTP adapter."""

import inspect
import json
from collections.abc import Callable

import httpx
import pytest

from app.providers import spoonacular as spoonacular_mod
from app.providers.spoonacular import (
    BASE_URL,
    INFORMATION_PATH,
    REQUEST_LOCALE,
    SpoonacularEstimateProvider,
    SpoonacularUnavailable,
)

API_KEY = "TEST_SPOONACULAR_KEY_MARKER"
INGREDIENT_ID = 1001
AMOUNT = 2
UNIT = "g"
SUCCESS_BODY = json.dumps(
    {"estimatedCost": {"value": 299.4, "unit": "US Cents"}}
).encode()
SECOND_BODY = json.dumps(
    {"estimatedCost": {"value": 150.6, "unit": "US Cents"}}
).encode()
NEGATIVE_BODY = json.dumps(
    {"estimatedCost": {"value": -1, "unit": "US Cents"}}
).encode()
WRONG_UNIT_BODY = json.dumps({"estimatedCost": {"value": 10, "unit": "USD"}}).encode()
CENTS_ALIAS_BODY = json.dumps(
    {"estimatedCost": {"value": 299.4, "unit": "cents"}}
).encode()
MINOR_UNIT_BODY = json.dumps({"estimatedCost": {"value": 12, "unit": "cents"}}).encode()
NEGATIVE_FRACTION_BODY = json.dumps(
    {"estimatedCost": {"value": -0.4, "unit": "cents"}}
).encode()
BOOL_VALUE_BODY = json.dumps(
    {"estimatedCost": {"value": True, "unit": "cents"}}
).encode()
STRING_VALUE_BODY = json.dumps(
    {"estimatedCost": {"value": "12", "unit": "cents"}}
).encode()
NAN_VALUE_BODY = b'{"estimatedCost": {"value": NaN, "unit": "cents"}}'
INF_VALUE_BODY = b'{"estimatedCost": {"value": Infinity, "unit": "cents"}}'
OVERFLOW_VALUE_BODY = json.dumps(
    {"estimatedCost": {"value": 10**400, "unit": "cents"}}
).encode()
MALFORMED_UNIT_LIST_BODY = json.dumps(
    {"estimatedCost": {"value": 12, "unit": ["cents"]}}
).encode()
MALFORMED_UNIT_DICT_BODY = json.dumps(
    {"estimatedCost": {"value": 12, "unit": {"label": "cents"}}}
).encode()
INFORMATION_URL = f"{BASE_URL}{INFORMATION_PATH.format(id=INGREDIENT_ID)}"
LEAK_MARKERS = (
    API_KEY,
    "SECRET_TRANSPORT_MARKER",
    "SECRET_ERROR_BODY",
)
UNAVAILABLE = "Spoonacular estimate is unavailable"
ALLOWED_FIELDS = {"_api_key", "_client", "_owns_client"}


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[SpoonacularEstimateProvider, httpx.Client]:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    )
    provider = SpoonacularEstimateProvider(API_KEY, client=client)
    return provider, client


def assert_static_error(error: BaseException, message: str) -> None:
    assert str(error) == message
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = str(error) + repr(error)
    for marker in LEAK_MARKERS:
        assert marker not in rendered


def assert_information_get(request: httpx.Request) -> None:
    assert request.method == "GET"
    assert str(request.url.copy_with(query=None)) == INFORMATION_URL
    assert request.url.params["apiKey"] == API_KEY
    assert request.url.params["amount"] == str(AMOUNT)
    assert request.url.params["unit"] == UNIT
    assert request.url.params["locale"] == REQUEST_LOCALE
    assert request.url.params["locale"] == "en_US"


def estimate_from_body(content: bytes) -> int | None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=content)

    provider, client = make_provider(handler)
    try:
        return provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()


def assert_no_instance_cache(provider: SpoonacularEstimateProvider) -> None:
    fields = vars(provider)
    assert set(fields) == ALLOWED_FIELDS
    assert not hasattr(spoonacular_mod, "CACHE_SECONDS")
    assert (
        "clock"
        not in inspect.signature(SpoonacularEstimateProvider.__init__).parameters
    )


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
    assert_information_get(requests[0])


def test_repeat_call_issues_fresh_get_and_uses_new_value() -> None:
    requests: list[httpx.Request] = []
    bodies = [SUCCESS_BODY, SECOND_BODY]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=bodies[len(requests) - 1])

    provider, client = make_provider(handler)
    try:
        first = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        second = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        assert_no_instance_cache(provider)
    finally:
        provider.close()
        client.close()

    assert first == 299
    assert second == 151
    assert len(requests) == 2
    assert_information_get(requests[0])
    assert_information_get(requests[1])


def test_failed_then_recovered_call_issues_fresh_get() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.TimeoutException("SECRET_TRANSPORT_MARKER", request=request)
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    try:
        with pytest.raises(SpoonacularUnavailable) as raised:
            provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        recovered = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        assert_no_instance_cache(provider)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, UNAVAILABLE)
    assert recovered == 299
    assert len(requests) == 2
    assert_information_get(requests[0])
    assert_information_get(requests[1])


def test_provider_holds_no_cost_or_response_cache() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=SUCCESS_BODY)

    provider, client = make_provider(handler)
    try:
        cents = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        owned = {
            name: value for name, value in vars(provider).items() if name != "_client"
        }
        payload = repr(owned)
        assert_no_instance_cache(provider)
    finally:
        provider.close()
        client.close()

    assert cents == 299
    assert "299" not in payload
    assert "299.4" not in payload
    assert SUCCESS_BODY.decode() not in payload


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
    assert_information_get(requests[0])
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
    assert_information_get(requests[0])
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


def test_non_us_cents_unit_returns_none_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=WRONG_UNIT_BODY)

    provider, client = make_provider(handler)
    try:
        cents = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert cents is None


def test_malformed_json_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"{not-json")

    provider, client = make_provider(handler)
    try:
        with pytest.raises(SpoonacularUnavailable) as raised:
            provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
    finally:
        provider.close()
        client.close()

    assert_static_error(raised.value, UNAVAILABLE)


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


def test_cents_alias_matches_us_cents_integer() -> None:
    requests: list[httpx.Request] = []
    bodies = [SUCCESS_BODY, CENTS_ALIAS_BODY]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=bodies[len(requests) - 1])

    provider, client = make_provider(handler)
    try:
        us_cents = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        cents_alias = provider.estimate_ingredient_cents(INGREDIENT_ID, AMOUNT, UNIT)
        assert_no_instance_cache(provider)
    finally:
        provider.close()
        client.close()

    assert us_cents == 299
    assert cents_alias == 299
    assert us_cents == cents_alias
    assert len(requests) == 2
    assert_information_get(requests[0])
    assert_information_get(requests[1])


def test_cents_amount_is_not_multiplied_by_100() -> None:
    cents = estimate_from_body(MINOR_UNIT_BODY)
    assert cents == 12
    assert cents != 1200


def test_malformed_unit_list_returns_none() -> None:
    assert estimate_from_body(MALFORMED_UNIT_LIST_BODY) is None


def test_malformed_unit_dict_returns_none() -> None:
    assert estimate_from_body(MALFORMED_UNIT_DICT_BODY) is None


@pytest.mark.parametrize(
    "unit_label",
    ["USD", "US Dollars", "EUR", "pence"],
)
def test_unknown_unit_label_returns_none(unit_label: str) -> None:
    body = json.dumps({"estimatedCost": {"value": 12, "unit": unit_label}}).encode()
    assert estimate_from_body(body) is None


def test_negative_fraction_returns_none_before_rounding() -> None:
    assert estimate_from_body(NEGATIVE_FRACTION_BODY) is None


def test_bool_cost_value_returns_none() -> None:
    assert estimate_from_body(BOOL_VALUE_BODY) is None


def test_string_cost_value_returns_none() -> None:
    assert estimate_from_body(STRING_VALUE_BODY) is None


def test_nonfinite_cost_value_returns_none() -> None:
    assert estimate_from_body(NAN_VALUE_BODY) is None
    assert estimate_from_body(INF_VALUE_BODY) is None


def test_overflowing_cost_value_returns_none() -> None:
    assert estimate_from_body(OVERFLOW_VALUE_BODY) is None
