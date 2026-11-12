"""Tests for matching plan grocery lines to Kroger products, using invented data."""

import threading
import time
from collections.abc import Callable, Sequence
from typing import cast

import httpx
import pytest

from app import kroger_cart
from app.domain.curated_foods import ALL_INGREDIENTS
from app.domain.plan_revision import PlanMeal, PlanSnapshot
from app.kroger_cart import (
    PREVIEW_WORKERS,
    CartPreview,
    build_preview,
    grocery_ingredient_ids,
)
from app.providers import kroger
from app.providers.kroger import (
    KrogerClient,
    KrogerProduct,
    KrogerSearch,
    KrogerUnavailable,
    Source,
)
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


def _product(
    upc: str | None,
    description: str,
    size: str = "1 lb",
    stock_level: str | None = None,
) -> object:
    item: dict[str, object] = {"size": size}
    if stock_level is not None:
        item["inventory"] = {"stockLevel": stock_level}
    entry: dict[str, object] = {
        "productId": f"id-{description}",
        "description": description,
        "items": [item],
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
        "source": "live",
    }


def test_preview_skips_an_out_of_stock_product() -> None:
    catalog = Catalog(
        {
            "chicken_breast": [
                _product(
                    "12345678", "Sold Out", stock_level="TEMPORARILY_OUT_OF_STOCK"
                ),
                _product("0001112223334", "In Stock", stock_level="HIGH"),
            ]
        }
    )
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert [(i.ingredient_id, i.upc) for i in preview.items] == [
        ("chicken_breast", "0001112223334")
    ]


def test_preview_allows_an_unknown_stock_level() -> None:
    catalog = Catalog({"chicken_breast": [_product("12345678", "Unknown Stock")]})
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert [i.upc for i in preview.items] == ["12345678"]


def test_preview_leaves_a_line_unmatched_when_every_product_is_out_of_stock() -> None:
    sold_out = "TEMPORARILY_OUT_OF_STOCK"
    catalog = Catalog(
        {
            "chicken_breast": [
                _product("12345678", "Sold Out A", stock_level=sold_out),
                _product("0001112223334", "Sold Out B", stock_level=sold_out),
            ]
        }
    )
    preview = build_preview(_snapshot(), _client(catalog), LOCATION)
    assert preview.items == []
    assert "chicken_breast" in [line.ingredient_id for line in preview.unmatched]


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
        "source": "live",
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


IDS = list(ALL_INGREDIENTS)[:12]


def _kp(upc: str | None, description: str, stock_level: str | None = None) -> object:
    return KrogerProduct(
        product_id=f"id-{description}",
        upc=upc,
        description=description,
        brand=None,
        size="1 lb",
        sold_by=None,
        regular_cents=None,
        promo_cents=None,
        stock_level=stock_level,
    )


class FakeClient:
    """Count concurrent searches. Delays and errors are set per term."""

    source: Source = "live"

    def __init__(
        self,
        products: dict[str, list[object]] | None = None,
        delays: dict[str, float] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.products = products or {}
        self.delays = delays or {}
        self.errors = errors or {}
        self.lock = threading.Lock()
        self.current = 0
        self.peak = 0
        self.calls: list[str] = []

    def search_products(
        self, term: str, location_id: str, limit: int = 5
    ) -> KrogerSearch:
        with self.lock:
            self.current += 1
            self.peak = max(self.peak, self.current)
            self.calls.append(term)
        try:
            time.sleep(self.delays.get(term, 0))
            error = self.errors.get(term)
            if error is not None:
                raise error
            found = cast(list[KrogerProduct], self.products.get(term, []))
            return KrogerSearch(products=found, cache_control=None)
        finally:
            with self.lock:
                self.current -= 1


def _use_lines(
    monkeypatch: pytest.MonkeyPatch,
    ids: Sequence[str],
    term_of: Callable[[str], str | None] = lambda i: f"term-{i}",
) -> None:
    monkeypatch.setattr(kroger_cart, "grocery_ingredient_ids", lambda s: list(ids))
    monkeypatch.setattr(kroger_cart, "kroger_search_term", term_of)


def _run(client: FakeClient) -> CartPreview:
    return build_preview(_snapshot(), cast(KrogerClient, client), LOCATION)


def _reference(client: FakeClient) -> CartPreview:
    """Search in series, with no pool."""
    items: list[kroger_cart.PreviewItem] = []
    by_upc: dict[str, kroger_cart.PreviewItem] = {}
    unmatched: list[kroger_cart.UnmatchedLine] = []
    for ingredient_id in kroger_cart.grocery_ingredient_ids(_snapshot()):
        name = ALL_INGREDIENTS[ingredient_id].name
        term = kroger_cart.kroger_search_term(ingredient_id)
        found = (
            []
            if term is None
            else client.search_products(term, LOCATION, limit=5).products
        )
        product = next(
            (
                p
                for p in found
                if p.upc is not None
                and p.upc.isdigit()
                and 8 <= len(p.upc) <= 14
                and p.stock_level != "TEMPORARILY_OUT_OF_STOCK"
            ),
            None,
        )
        if product is None or product.upc is None:
            unmatched.append(
                kroger_cart.UnmatchedLine(ingredient_id=ingredient_id, name=name)
            )
            continue
        if product.upc in by_upc:
            existing = by_upc[product.upc]
            existing.quantity = min(existing.quantity + 1, kroger_cart.MAX_QUANTITY)
            continue
        item = kroger_cart.PreviewItem(
            ingredient_id=ingredient_id,
            name=name,
            upc=product.upc,
            description=product.description,
            size=product.size,
            quantity=1,
        )
        by_upc[product.upc] = item
        items.append(item)
    return CartPreview(items=items, unmatched=unmatched, source=client.source)


def test_preview_runs_searches_in_parallel_within_the_worker_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_lines(monkeypatch, IDS)
    client = FakeClient(delays={f"term-{i}": 0.05 for i in IDS})
    start = time.perf_counter()
    _run(client)
    elapsed = time.perf_counter() - start
    assert len(client.calls) == 12
    assert 1 < client.peak <= PREVIEW_WORKERS
    assert elapsed < 12 * 0.05 / 2


def _term_map(overrides: dict[str, str]) -> Callable[[str], str | None]:
    """Return a term function. An empty override means no term."""
    return lambda i: overrides.get(i, f"term-{i}") or None


def test_preview_equals_the_sequential_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sold_out = "TEMPORARILY_OUT_OF_STOCK"
    a, b, c, d, e, f = IDS[:6]
    plans: list[tuple[Sequence[str], dict[str, str], dict[str, list[object]]]] = [
        (
            [a, b, c, d, e, f],
            {e: ""},
            {
                f"term-{a}": [
                    _kp("11111111", "Sold Out", sold_out),
                    _kp("22222222", "In Stock"),
                ],
                f"term-{b}": [_kp("33333333", "Shared")],
                f"term-{c}": [_kp("33333333", "Shared Again")],
                f"term-{d}": [_kp("22222222", "In Stock Again")],
            },
        ),
        (
            IDS,
            {},
            {f"term-{i}": [_kp("44444444", "Same")] for i in IDS},
        ),
        (
            [a, b, c],
            {b: f"term-{a}", c: f"term-{a}"},
            {f"term-{a}": [_kp("55555555", "Duplicated term")]},
        ),
        ([a, b], {}, {}),
    ]
    for index, (ids, term_map, products) in enumerate(plans):
        _use_lines(monkeypatch, ids, _term_map(term_map))
        expected = _reference(FakeClient(products))
        assert _run(FakeClient(products)) == expected
        if index == 0:
            assert expected.unmatched
        if ids is IDS:
            quantities = [i.quantity for i in expected.items]
            assert quantities == [min(len(IDS), kroger_cart.MAX_QUANTITY)]


def test_a_failed_search_raises_with_no_partial_and_cancels_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = IDS[:5]
    _use_lines(monkeypatch, ids)
    delays = {f"term-{i}": 0.3 for i in ids}
    delays[f"term-{ids[1]}"] = 0.0
    client = FakeClient(delays=delays, errors={f"term-{ids[1]}": KrogerUnavailable()})
    with pytest.raises(KrogerUnavailable):
        _run(client)
    assert client.current == 0
    assert f"term-{ids[4]}" not in client.calls
    assert len(client.calls) < 5
    seen = list(client.calls)
    time.sleep(0.4)
    assert client.calls == seen


def test_two_failures_raise_the_earlier_line_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = IDS[:3]
    _use_lines(monkeypatch, ids)
    client = FakeClient(
        delays={f"term-{ids[1]}": 0.2},
        errors={
            f"term-{ids[1]}": ValueError("earlier line"),
            f"term-{ids[2]}": RuntimeError("later line"),
        },
    )
    with pytest.raises(ValueError, match="earlier line"):
        _run(client)
    assert client.current == 0


def test_a_duplicated_search_term_makes_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = IDS[:3]
    _use_lines(monkeypatch, ids, lambda i: "other" if i == ids[2] else "same")
    client = FakeClient({"same": [_kp("66666666", "Same Item")]})
    preview = _run(client)
    assert sorted(client.calls) == ["other", "same"]
    assert [(i.ingredient_id, i.quantity) for i in preview.items] == [(ids[0], 2)]
    assert [line.ingredient_id for line in preview.unmatched] == [ids[2]]


def test_lines_without_a_term_make_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = IDS[:6]
    _use_lines(monkeypatch, ids, _term_map({i: "" for i in ids[1::2]}))
    client = FakeClient()
    preview = _run(client)
    assert sorted(client.calls) == sorted(f"term-{i}" for i in ids[::2])
    assert [line.ingredient_id for line in preview.unmatched] == ids

    _use_lines(monkeypatch, ids, lambda i: None)
    none_client = FakeClient()
    _run(none_client)
    assert none_client.calls == []


def test_concurrent_previews_share_the_worker_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_lines(monkeypatch, IDS)
    client = FakeClient(delays={f"term-{i}": 0.02 for i in IDS})
    results: list[CartPreview] = []
    errors: list[Exception] = []

    def work() -> None:
        try:
            results.append(_run(client))
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(results) == 2
    assert len(client.calls) == 24
    assert 1 <= client.peak <= PREVIEW_WORKERS
