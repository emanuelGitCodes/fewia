"""Tests for matching plan grocery lines to Kroger products, using invented data."""

from collections.abc import Sequence

import httpx
import pytest

from app import kroger_cart
from app.domain.plan_revision import PlanMeal, PlanSnapshot
from app.kroger_cart import build_preview, grocery_ingredient_ids
from app.providers import kroger
from app.providers.kroger import KrogerClient, KrogerUnavailable
from app.services.kroger_overlay import kroger_search_term

LOCATION = "01234567"
PANTRY = ("olive_oil", "cumin", "salt")
TACO_LINES = ["chicken_breast", "onion", "salsa", "tortillas"]
BOTH = ("chicken_tacos", "bean_tacos")


def _snapshot(
    recipes: Sequence[str] = ("chicken_tacos",), pantry: Sequence[str] = PANTRY
) -> PlanSnapshot:
    return PlanSnapshot(
        meals=[PlanMeal(recipe_id=recipe, servings=2) for recipe in recipes],
        pantry_ingredient_ids=list(pantry),
    )


def _product(upc: str | None, description: str, size: str = "1 lb") -> object:
    entry: dict[str, object] = {
        "productId": f"id-{description}",
        "description": description,
        "items": [{"size": size}],
    }
    if upc is not None:
        entry["upc"] = upc
    return entry


class Catalog:
    def __init__(self, by_ingredient: dict[str, list[object]]) -> None:
        self.by_term = {
            kroger_search_term(ingredient_id): products
            for ingredient_id, products in by_ingredient.items()
        }
        self.searches: list[httpx.Request] = []
        self.fail_on: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        self.searches.append(request)
        term = request.url.params["filter.term"]
        if term == self.fail_on:
            return httpx.Response(500)
        return httpx.Response(200, json={"data": self.by_term.get(term, [])})

    def terms(self) -> list[str]:
        return [r.url.params["filter.term"] for r in self.searches]


def _client(catalog: Catalog) -> KrogerClient:
    http = httpx.Client(transport=httpx.MockTransport(catalog))
    return KrogerClient(
        "invented-id",
        "invented-secret",
        base_url=kroger.HOSTS["certification"],
        client=http,
    )


def test_lines_are_distinct_sorted_and_exclude_the_pantry() -> None:
    assert grocery_ingredient_ids(_snapshot()) == TACO_LINES
    both = grocery_ingredient_ids(_snapshot(BOTH))
    assert both == sorted([*TACO_LINES, "black_beans"])
    everything = grocery_ingredient_ids(_snapshot(pantry=()))
    assert everything == sorted([*TACO_LINES, *PANTRY])


def test_lines_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kroger_cart, "MAX_LINES", 2)
    assert grocery_ingredient_ids(_snapshot()) == TACO_LINES[:2]


def test_preview_matches_the_first_product_with_a_valid_upc() -> None:
    catalog = Catalog(
        {
            "chicken_breast": [
                _product("1234567", "Too short"),
                _product("0001112223334", "Invented Chicken", "2 lb"),
                _product("99999999", "Later Chicken"),
            ],
            "salsa": [
                _product("123456789012345", "Too long"),
                _product("12345678", "Invented Salsa"),
            ],
            "onion": [],
            "tortillas": [_product(None, "No UPC")],
        }
    )
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert preview.model_dump() == {
        "items": [
            {
                "ingredient_id": "chicken_breast",
                "name": "chicken breast",
                "upc": "0001112223334",
                "description": "Invented Chicken",
                "size": "2 lb",
                "quantity": 1,
            },
            {
                "ingredient_id": "salsa",
                "name": "salsa",
                "upc": "12345678",
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


def test_preview_merges_lines_that_match_the_same_upc() -> None:
    catalog = Catalog(
        {
            "chicken_breast": [_product("12345678", "Shared Item", "2 lb")],
            "onion": [_product("0001112223334", "Invented Onion")],
            "salsa": [_product("12345678", "Shared Again")],
            "tortillas": [_product("12345678", "Shared Third")],
        }
    )
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert [item.upc for item in preview.items] == ["12345678", "0001112223334"]
    assert preview.model_dump() == {
        "items": [
            {
                "ingredient_id": "chicken_breast",
                "name": "chicken breast",
                "upc": "12345678",
                "description": "Shared Item",
                "size": "2 lb",
                "quantity": 3,
            },
            {
                "ingredient_id": "onion",
                "name": "onion",
                "upc": "0001112223334",
                "description": "Invented Onion",
                "size": "1 lb",
                "quantity": 1,
            },
        ],
        "unmatched": [],
    }
    assert len(catalog.searches) == 4


def test_merged_quantity_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    assert kroger_cart.MAX_QUANTITY == 10
    monkeypatch.setattr(kroger_cart, "MAX_QUANTITY", 2)
    shared = [_product("12345678", "Shared Item")]
    catalog = Catalog({line: shared for line in TACO_LINES})
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert [(i.upc, i.quantity) for i in preview.items] == [("12345678", 2)]
    assert preview.unmatched == []


def test_preview_searches_once_per_line_in_order_with_the_store() -> None:
    catalog = Catalog({})
    snapshot = _snapshot(BOTH)
    build_preview(snapshot, _client(catalog), LOCATION)
    lines = grocery_ingredient_ids(snapshot)
    assert catalog.terms() == [kroger_search_term(line) for line in lines]
    for request in catalog.searches:
        assert request.url.params["filter.locationId"] == LOCATION
        assert request.url.params["filter.limit"] == "5"


def test_preview_marks_a_line_without_a_term_unmatched_and_does_not_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = kroger_cart.kroger_search_term
    monkeypatch.setattr(
        kroger_cart, "kroger_search_term", lambda i: None if i == "onion" else real(i)
    )
    catalog = Catalog({})
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert "onion" not in catalog.terms()
    assert len(catalog.searches) == 3
    assert [line.ingredient_id for line in preview.unmatched] == TACO_LINES
    assert preview.items == []


def test_preview_is_all_or_nothing_when_kroger_is_unavailable() -> None:
    catalog = Catalog({"chicken_breast": [_product("12345678", "Chicken")]})
    catalog.fail_on = kroger_search_term("salsa")
    with pytest.raises(KrogerUnavailable):
        build_preview(_snapshot(), _client(catalog), LOCATION)
