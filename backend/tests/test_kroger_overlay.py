"""Tests for the read-time Kroger quote overlay, using invented data."""

import copy
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from app.providers.kroger import KrogerClient
from app.providers.kroger_fixture import build_fixture_client
from app.services.kroger_overlay import attach_kroger_quote, kroger_search_term

BASE = "https://kroger.test"
LOCATION = "01234567"
NOW = datetime(2030, 1, 2, 3, 4, 5, 678, tzinfo=UTC)


class Shop:
    def __init__(self, status: int = 200, data: list[object] | None = None) -> None:
        self.status = status
        self.data: list[object] = [_product()] if data is None else data
        self.terms: list[str] = []
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        self.terms.append(request.url.params["filter.term"])
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, json={"data": self.data})


def _product(regular: float | None = 2.49, **overrides: object) -> dict[str, object]:
    price: dict[str, object] = {} if regular is None else {"regular": regular}
    entry: dict[str, object] = {
        "productId": "0001112223334",
        "description": "Invented Ground Beef",
        "brand": "Made Up",
        "items": [
            {"size": "1 lb", "inventory": {"stockLevel": "HIGH"}, "price": price}
        ],
    }
    entry.update(overrides)
    return entry


def _client(shop: Shop) -> KrogerClient:
    http = httpx.Client(transport=httpx.MockTransport(shop))
    return KrogerClient("invented-id", "invented-secret", base_url=BASE, client=http)


def _swap(food: str, outcome: str = "success") -> dict[str, object]:
    return {
        "tool": "what_if_substitute",
        "outcome": outcome,
        "inputs": {"status": "swapped", "with_ingredient_id": food},
    }


def _facts(food: str) -> dict[str, object]:
    return {
        "tool": "get_ingredient_facts",
        "outcome": "success",
        "inputs": {"status": "found", "ingredient_id": food},
    }


def _result(*trace: object) -> dict[str, object]:
    return {
        "answer": "stored text",
        "budget": {"total_cents": 1200},
        "tool_trace": list(trace),
    }


def _forbid_admission() -> bool:
    raise AssertionError("This lookup MUST NOT reserve quota")


def test_search_terms() -> None:
    assert kroger_search_term("ground_beef_80") == "ground beef 80% lean"
    assert kroger_search_term("ground_beef_93") == "ground beef 93% lean"
    assert kroger_search_term("usda_172475") == "tofu"
    assert kroger_search_term("chicken_breast") == "chicken breast"
    assert kroger_search_term("no_such_food") is None


def test_swap_to_unpriced_food_gets_quote() -> None:
    shop = Shop()
    result = _result(_swap("ground_beef_80"))
    out = attach_kroger_quote(result, _client(shop), LOCATION, lambda: NOW)
    assert shop.terms == ["ground beef 80% lean"]
    assert out["kroger_quote"] == {
        "kind": "store_live",
        "ingredient_id": "ground_beef_80",
        "product_label": "Invented Ground Beef",
        "brand": "Made Up",
        "size": "1 lb",
        "regular_cents": 249,
        "promo_cents": None,
        "stock_level": "HIGH",
        "location_id": LOCATION,
        "retrieved_at": "2030-01-02T03:04:05Z",
    }
    assert out["answer"] == "stored text"
    assert out["budget"] == result["budget"]


def test_retrieved_at_is_utc() -> None:
    local = NOW.astimezone(timezone(timedelta(hours=-5)))
    out = attach_kroger_quote(
        _result(_swap("ground_beef_80")), _client(Shop()), LOCATION, lambda: local
    )
    quote = out["kroger_quote"]
    assert isinstance(quote, dict)
    assert quote["retrieved_at"] == "2030-01-02T03:04:05Z"


def test_priced_food_makes_no_call() -> None:
    shop = Shop()
    result = _result(_swap("chicken_breast"))
    out = attach_kroger_quote(
        result, _client(shop), LOCATION, lambda: NOW, before_lookup=_forbid_admission
    )
    assert out == result
    assert shop.terms == []


def test_facts_for_unpriced_usda_food_uses_short_name() -> None:
    shop = Shop()
    out = attach_kroger_quote(
        _result(_facts("usda_172475")), _client(shop), LOCATION, lambda: NOW
    )
    assert shop.terms == ["tofu"]
    assert "kroger_quote" in out


def test_last_target_wins() -> None:
    shop = Shop()
    result = _result(_swap("ground_beef_80"), _facts("usda_172475"))
    out = attach_kroger_quote(result, _client(shop), LOCATION, lambda: NOW)
    assert shop.terms == ["tofu"]
    quote = out["kroger_quote"]
    assert isinstance(quote, dict)
    assert quote["ingredient_id"] == "usda_172475"


@pytest.mark.parametrize(
    "trace",
    [
        None,
        "bad",
        [],
        ["bad", 3, None],
        [{"tool": "what_if_substitute", "outcome": "success"}],
        [_swap("ground_beef_80", outcome="error")],
        [{**_swap("ground_beef_80"), "inputs": {"status": "unchanged"}}],
        [{**_swap("ground_beef_80"), "inputs": {"status": "swapped"}}],
        [_swap("no_such_food")],
    ],
)
def test_malformed_or_missing_target_is_unchanged(trace: object) -> None:
    shop = Shop()
    result: dict[str, object] = {"answer": "x", "tool_trace": trace}
    out = attach_kroger_quote(
        result, _client(shop), LOCATION, lambda: NOW, before_lookup=_forbid_admission
    )
    assert out == result
    assert shop.terms == []


def test_kroger_failure_marks_degraded() -> None:
    result = _result(_swap("ground_beef_80"))
    out = attach_kroger_quote(result, _client(Shop(status=500)), LOCATION, lambda: NOW)
    assert out["kroger_degraded"] is True
    assert "kroger_quote" not in out


def test_bad_location_marks_degraded() -> None:
    shop = Shop()
    out = attach_kroger_quote(
        _result(_swap("ground_beef_80")),
        _client(shop),
        "bad",
        lambda: NOW,
        before_lookup=_forbid_admission,
    )
    assert out["kroger_degraded"] is True
    assert shop.terms == []


def test_no_priced_product_gives_none() -> None:
    shop = Shop(data=[_product(regular=None)])
    out = attach_kroger_quote(
        _result(_swap("ground_beef_80")), _client(shop), LOCATION, lambda: NOW
    )
    assert out["kroger_quote"] is None
    assert "kroger_degraded" not in out


def test_first_priced_product_is_used() -> None:
    shop = Shop(data=[_product(regular=None), _product(3.0, description="Second")])
    out = attach_kroger_quote(
        _result(_swap("ground_beef_80")), _client(shop), LOCATION, lambda: NOW
    )
    quote = out["kroger_quote"]
    assert isinstance(quote, dict)
    assert quote["product_label"] == "Second"
    assert quote["regular_cents"] == 300


def test_input_is_not_mutated() -> None:
    result = _result(_swap("ground_beef_80"))
    before = copy.deepcopy(result)
    out = attach_kroger_quote(result, _client(Shop()), LOCATION, lambda: NOW)
    assert result == before
    assert out is not result


def test_admission_runs_once_before_live_requests() -> None:
    shop = Shop()
    calls: list[bool] = []

    def admit() -> bool:
        assert shop.requests == []
        calls.append(True)
        return True

    out = attach_kroger_quote(
        _result(_swap("ground_beef_80"), _facts("usda_172475")),
        _client(shop),
        LOCATION,
        lambda: NOW,
        before_lookup=admit,
    )
    assert calls == [True]
    assert shop.terms == ["tofu"]
    assert "kroger_quote" in out


def test_denied_admission_sends_no_request() -> None:
    shop = Shop()
    result = _result(_swap("ground_beef_80"))
    out = attach_kroger_quote(
        result, _client(shop), LOCATION, lambda: NOW, before_lookup=lambda: False
    )
    assert out == {**result, "kroger_degraded": True}
    assert "kroger_degraded" not in result
    assert shop.requests == []


def test_fixture_quote_skips_admission() -> None:
    client = build_fixture_client("http://localhost/grocery/kroger/callback")
    assert client.fixture is True
    out = attach_kroger_quote(
        _result(_swap("ground_beef_80")),
        client,
        LOCATION,
        lambda: NOW,
        before_lookup=_forbid_admission,
    )
    quote = out["kroger_quote"]
    assert isinstance(quote, dict)
    assert quote["kind"] == "store_fixture"


def test_unusable_search_term_skips_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    shop = Shop()
    result = _result(_swap("ground_beef_80"))
    monkeypatch.setattr(
        "app.services.kroger_overlay.kroger_search_term", lambda _: None
    )
    out = attach_kroger_quote(
        result, _client(shop), LOCATION, lambda: NOW, before_lookup=_forbid_admission
    )
    assert out == result
    assert shop.requests == []
