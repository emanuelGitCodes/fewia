"""Tests for the live USDA FoodData Central search client."""

from collections.abc import Callable

import httpx
import pytest

from app.domain.nutrition import NutritionFacts
from app.providers import usda_live
from app.providers.usda_live import (
    COOLDOWN_SECONDS,
    HOURLY_LIMIT,
    UsdaLiveClient,
    UsdaUnavailable,
    get_usda_live_client,
)

KEY = "FAKE_USDA_LIVE_KEY_VALUE"


def _nutrients(skip: str | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"nutrientNumber": "208", "unitName": "KCAL", "value": 321.4},
        {"nutrientNumber": "203", "unitName": "G", "value": 18.4},
        {"nutrientNumber": "204", "unitName": "G", "value": 25},
        {"nutrientNumber": "205", "unitName": "G", "value": 3.04},
        {"nutrientNumber": "307", "unitName": "MG", "value": 600},
    ]
    return [row for row in rows if row["nutrientNumber"] != skip]


def _food(
    fdc_id: int = 100, description: str = "Cheese, paneer", **extra: object
) -> dict[str, object]:
    return {
        "fdcId": fdc_id,
        "description": description,
        "dataType": "SR Legacy",
        "foodNutrients": _nutrients(),
        **extra,
    }


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    clock: Callable[[], float] = lambda: 0.0,
) -> UsdaLiveClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return UsdaLiveClient(KEY, client=http, clock=clock)


def _ok(foods: list[object]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json={"foods": foods})


def test_key_travels_only_in_the_header_and_params_are_fixed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"foods": []})

    assert _client(handler).search("paneer") == []
    request = seen[0]
    assert request.headers["X-Api-Key"] == KEY
    assert KEY not in str(request.url)
    assert request.url.host == "api.nal.usda.gov"
    assert request.url.path == "/fdc/v1/foods/search"
    assert request.url.params["query"] == "paneer"
    assert request.url.params["dataType"] == "Foundation,SR Legacy,Branded"
    assert request.url.params["pageSize"] == "5"


def test_parses_branded_and_sr_legacy_items() -> None:
    branded = _food(200, "PANEER CHEESE", brandOwner="Acme Dairy", dataType="Branded")
    foods = _client(_ok([_food(), branded])).search("paneer")
    assert [f.fdc_id for f in foods] == [100, 200]
    assert foods[0].name == "cheese (paneer)"
    assert foods[0].brand is None
    assert foods[0].data_type == "SR Legacy"
    assert foods[0].facts == NutritionFacts(100, 321, 18400, 25000, 3040, 600)
    assert foods[1].brand == "Acme Dairy"
    assert foods[1].data_type == "Branded"


def test_energy_number_957_is_accepted() -> None:
    rows = _nutrients("208")
    rows.append({"nutrientNumber": "957", "unitName": "KCAL", "value": 99})
    entry = {**_food(), "foodNutrients": rows}
    assert _client(_ok([entry])).search("x")[0].facts.energy_kcal == 99


def test_food_missing_a_macro_is_skipped() -> None:
    no_protein = {**_food(1), "foodNutrients": _nutrients("203")}
    foods = _client(_ok([no_protein, _food(2), "junk", {"fdcId": "3"}])).search("x")
    assert [f.fdc_id for f in foods] == [2]


def test_control_characters_are_stripped_from_provider_text() -> None:
    entry = _food(brandOwner="Ac‮me\n\x00 Dairy" + "z" * 400)
    food = _client(_ok([entry])).search("x")[0]
    assert food.brand is not None
    assert food.brand.startswith("Acme Dairy")
    assert len(food.brand) <= 160
    assert food.brand.isprintable()


@pytest.mark.parametrize("query", ["", "a" * 161, "bad\nquery", 5])
def test_invalid_query_raises_value_error_without_a_request(query: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("no request expected")

    with pytest.raises(ValueError):
        _client(handler).search(query)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(403, json={"foods": []}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=["foods"]),
        httpx.Response(200, json={"foods": "x"}),
    ],
)
def test_bad_responses_are_unavailable(response: httpx.Response) -> None:
    with pytest.raises(UsdaUnavailable, match="^USDA FoodData Central is unavailable$"):
        _client(lambda request: response).search("x")


def test_transport_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(UsdaUnavailable):
        _client(handler).search("x")


def test_redirect_is_not_followed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://evil.example/x"})

    with pytest.raises(UsdaUnavailable):
        _client(handler).search("x")
    assert calls == ["api.nal.usda.gov"]


def test_429_starts_a_cooldown_without_requests() -> None:
    now = [0.0]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429 if len(calls) == 1 else 200, json={"foods": []})

    client = _client(handler, clock=lambda: now[0])
    with pytest.raises(UsdaUnavailable):
        client.search("x")
    now[0] = COOLDOWN_SECONDS - 1
    with pytest.raises(UsdaUnavailable):
        client.search("x")
    assert len(calls) == 1
    now[0] = COOLDOWN_SECONDS
    assert client.search("x") == []
    assert len(calls) == 2


def test_budget_stops_requests_until_the_next_clock_hour() -> None:
    now = [10.0]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"foods": []})

    client = _client(handler, clock=lambda: now[0])
    for _ in range(HOURLY_LIMIT):
        client.search("x")
    with pytest.raises(UsdaUnavailable):
        client.search("x")
    assert len(calls) == HOURLY_LIMIT
    now[0] = 3600.0
    client.search("x")
    assert len(calls) == HOURLY_LIMIT + 1


def test_blank_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        UsdaLiveClient("  ")


def test_builder_returns_none_without_a_key_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_usda_live_client.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(usda_live, "_load_api_key", lambda: None)
    try:
        assert get_usda_live_client() is None
    finally:
        get_usda_live_client.cache_clear()  # type: ignore[attr-defined]


def test_builder_builds_one_client_from_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    get_usda_live_client.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(usda_live, "_load_api_key", lambda: SecretStr(KEY))
    try:
        first = get_usda_live_client()
        assert isinstance(first, UsdaLiveClient)
        assert get_usda_live_client() is first
    finally:
        get_usda_live_client.cache_clear()  # type: ignore[attr-defined]
