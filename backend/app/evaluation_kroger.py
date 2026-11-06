"""Deterministic evaluation of the Kroger path: python -m app.evaluation_kroger.

Every product, UPC, store, and token here is invented. The real KrogerClient
runs over httpx.MockTransport, so request building and parsing run for real
and nothing touches the network. The report holds ids, counts, rates, and
status classes only.
"""

import argparse
import base64
import json
import math
import os
import re
import sys
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

import httpx

from app.domain.plan_revision import PlanMeal, PlanSnapshot
from app.kroger_cart import CartPreview, build_preview, grocery_ingredient_ids
from app.providers import kroger
from app.providers.kroger import (
    CartItem,
    KrogerAuthRejected,
    KrogerCartUnknown,
    KrogerClient,
    KrogerUnavailable,
)
from app.services.kroger_overlay import attach_kroger_quote, kroger_search_term

VERSION = "kroger-eval-v1"
EVIDENCE_CLASS = "deterministic_fake_provider"
LATENCY_SCOPE = "our code, synthetic transport, no network"
LATENCY_RUNS = 30
_INVALID = "Invalid evaluation CLI input"

CLIENT_ID = "eval-client-id-7f3a"
CLIENT_SECRET = "eval-client-secret-9c1d"
APP_TOKEN = "eval-app-token-4b2e"
CUSTOMER_TOKEN = "eval-customer-token-8d5f"
LOCATION = "0eval001"
BASE_URL = kroger.HOSTS["certification"]
OUT_OF_STOCK_LEVEL = "TEMPORARILY_OUT_OF_STOCK"
_VALID_UPC = re.compile(r"[0-9]{8,14}")

PLAN = PlanSnapshot(
    meals=[
        PlanMeal(recipe_id="chicken_and_rice_bowls", servings=2),
        PlanMeal(recipe_id="chicken_tacos", servings=2),
    ],
    pantry_ingredient_ids=["olive_oil", "cumin", "salt"],
    plan_cap_cents=None,
)
QUOTE_INGREDIENT = "ground_beef_80"
QUOTE_NOW = datetime(2030, 1, 1, 22, 4, 5, 678, tzinfo=timezone(timedelta(hours=-5)))
QUOTE_READ_TIME = "2030-01-02T03:04:05Z"


def _product(
    upc: str, description: str, stock: str | None, regular: float | None = None
) -> dict[str, object]:
    item: dict[str, object] = {"size": "1 unit"}
    if stock is not None:
        item["inventory"] = {"stockLevel": stock}
    if regular is not None:
        item["price"] = {"regular": regular}
    return {
        "productId": f"eval-{upc}",
        "upc": upc,
        "description": description,
        "items": [item],
    }


# One synthetic line per case. onion has no product at all.
LINE_PRODUCTS: dict[str, list[dict[str, object]]] = {
    # out-of-stock first product, then an in-stock one
    "chicken_breast": [
        _product("0000000000101", "Eval Sold Out Chicken", OUT_OF_STOCK_LEVEL),
        _product("0000000000102", "Eval Chicken", "HIGH"),
    ],
    # in-stock product
    "rice": [_product("0000000000103", "Eval Rice", "HIGH")],
    # low-stock product
    "mixed_vegetables": [_product("0000000000104", "Eval Vegetables", "LOW")],
    # product with no stock field
    "salsa": [_product("0000000000105", "Eval Salsa", None)],
    # only out-of-stock products
    "tortillas": [
        _product("0000000000106", "Eval Sold Out Tortillas", OUT_OF_STOCK_LEVEL)
    ],
    # invalid UPC
    "garlic": [_product("NOT-A-UPC", "Eval Garlic", "HIGH")],
    "onion": [],
}
SOLD_OUT_UPCS = frozenset({"0000000000101", "0000000000106"})
_QUOTE_PRODUCT = _product("0000000000107", "Eval Ground Beef", "HIGH", 2.49)


def _catalog() -> dict[str, list[dict[str, object]]]:
    catalog: dict[str, list[dict[str, object]]] = {}
    for ingredient_id, products in LINE_PRODUCTS.items():
        term = kroger_search_term(ingredient_id)
        if term is not None:
            catalog[term] = products
    quote_term = kroger_search_term(QUOTE_INGREDIENT)
    if quote_term is not None:
        catalog[quote_term] = [_QUOTE_PRODUCT]
    return catalog


def _choosable(products: list[dict[str, object]]) -> bool:
    """Our own rule for a line with a product the cart may take."""
    for entry in products:
        upc = entry["upc"]
        items = entry["items"]
        assert isinstance(upc, str) and isinstance(items, list)
        inventory = items[0].get("inventory", {})
        stock = inventory.get("stockLevel") if isinstance(inventory, dict) else None
        if _VALID_UPC.fullmatch(upc) and stock != OUT_OF_STOCK_LEVEL:
            return True
    return False


Failure = Callable[[httpx.Request], httpx.Response]


def _fail_status(status: int) -> Failure:
    return lambda request: httpx.Response(status)


def _raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("eval timeout", request=request)


def _raise_connect(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("eval connection error", request=request)


def _malformed(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"{not json")


FAILURES: dict[str, Failure] = {
    "http_429": _fail_status(429),
    "http_401": _fail_status(401),
    "http_500": _fail_status(500),
    "http_503": _fail_status(503),
    "timeout": _raise_timeout,
    "connection_error": _raise_connect,
    "malformed_json": _malformed,
}


class Shop:
    """Synthetic Kroger transport. It records every request and sees no network."""

    def __init__(
        self,
        *,
        failure: Failure | None = None,
        fail_after: int = 0,
        cart_status: int = 204,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._catalog = _catalog()
        self._failure = failure
        self._fail_after = fail_after
        self._cart_status = cart_status
        self._product_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == kroger.TOKEN_PATH:
            return httpx.Response(
                200, json={"access_token": APP_TOKEN, "expires_in": 1800}
            )
        if path == kroger.CART_ADD_PATH:
            return httpx.Response(self._cart_status)
        if path == kroger.PRODUCTS_PATH:
            self._product_calls += 1
            if self._failure is not None and self._product_calls > self._fail_after:
                return self._failure(request)
            term = request.url.params["filter.term"]
            return httpx.Response(200, json={"data": self._catalog.get(term, [])})
        return httpx.Response(404)

    def client(self) -> KrogerClient:
        return KrogerClient(
            CLIENT_ID,
            CLIENT_SECRET,
            base_url=BASE_URL,
            client=httpx.Client(transport=httpx.MockTransport(self)),
        )

    def cart_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == kroger.CART_ADD_PATH]


def _product_match(preview: CartPreview) -> dict[str, object]:
    lines = len(LINE_PRODUCTS)
    matched = len(preview.items)
    return {
        "lines": lines,
        "matched": matched,
        "unmatched": len(preview.unmatched),
        "rate": round(matched / lines, 4),
    }


def _add_items(preview: CartPreview) -> list[CartItem]:
    return [CartItem(item.upc, item.quantity) for item in preview.items]


def _cart_safety(
    shop: Shop, preview: CartPreview, errors: list[str]
) -> dict[str, object]:
    client = shop.client()
    before = len(shop.cart_requests())
    try:
        client.add_to_cart(CUSTOMER_TOKEN, _add_items(preview))
        sent = shop.cart_requests()[before:]
        expected = [{"upc": i.upc, "quantity": i.quantity} for i in preview.items]
        equal = len(sent) == 1 and json.loads(sent[0].content) == {"items": expected}
        for status in (401, 503):
            rejecting = Shop(cart_status=status)
            try:
                rejecting.client().add_to_cart(CUSTOMER_TOKEN, _add_items(preview))
            except (KrogerAuthRejected, KrogerCartUnknown) as error:
                errors.append(_error_text(error))
    except Exception as error:  # noqa: BLE001
        errors.append(_error_text(error))
        return {
            "cart_requests_before_add": before,
            "cart_requests_by_add": len(shop.cart_requests()) - before,
            "add_items_equal_preview": False,
        }
    return {
        "cart_requests_before_add": before,
        "cart_requests_by_add": len(sent),
        "add_items_equal_preview": equal,
    }


def _status_class(error: BaseException | None) -> str:
    if error is None:
        return "none"
    classes: dict[type[BaseException], str] = {
        KrogerUnavailable: "unavailable",
        KrogerCartUnknown: "cart_unknown",
        KrogerAuthRejected: "auth_rejected",
    }
    return classes.get(type(error), "unexpected")


def _error_text(error: BaseException) -> str:
    return "".join(traceback.format_exception(error)) + repr(error)


def _failure_handling(errors: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, failure in FAILURES.items():
        shop = Shop(failure=failure, fail_after=1)
        raised: BaseException | None = None
        result: CartPreview | None = None
        try:
            result = build_preview(PLAN, shop.client(), LOCATION)
        except Exception as error:  # noqa: BLE001
            raised = error
            errors.append(_error_text(error))
        rows.append(
            {
                "error": name,
                "status_class": _status_class(raised),
                "partial_preview": result is not None,
            }
        )
    return rows


def _secret_needles() -> list[str]:
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    return [
        CLIENT_ID,
        CLIENT_SECRET,
        APP_TOKEN,
        CUSTOMER_TOKEN,
        f"Bearer {APP_TOKEN}",
        f"Bearer {CUSTOMER_TOKEN}",
        f"Basic {basic}",
        basic,
    ]


def _hits(text: str) -> int:
    return sum(text.count(needle) for needle in _secret_needles())


def _quote_label(errors: list[str]) -> dict[str, object]:
    result: dict[str, object] = {
        "tool_trace": [
            {
                "tool": "what_if_substitute",
                "outcome": "success",
                "inputs": {"status": "swapped", "with_ingredient_id": QUOTE_INGREDIENT},
            }
        ]
    }
    try:
        attached = attach_kroger_quote(
            result, Shop().client(), LOCATION, lambda: QUOTE_NOW
        )
    except Exception as error:  # noqa: BLE001
        errors.append(_error_text(error))
        return {"store_label": False, "utc_read_time": False}
    quote = attached.get("kroger_quote")
    if not isinstance(quote, dict):
        return {"store_label": False, "utc_read_time": False}
    return {
        "store_label": quote.get("kind") == "store_live"
        and quote.get("location_id") == LOCATION,
        "utc_read_time": quote.get("retrieved_at") == QUOTE_READ_TIME,
    }


def _percentile(sorted_ms: list[float], percent: int) -> float:
    rank = math.ceil(percent / 100 * len(sorted_ms))
    return round(sorted_ms[max(rank, 1) - 1], 3)


def _code_latency(errors: list[str]) -> dict[str, object]:
    samples: list[float] = []
    for _ in range(LATENCY_RUNS):
        client = Shop().client()
        start = time.perf_counter()
        try:
            build_preview(PLAN, client, LOCATION)
        except Exception as error:  # noqa: BLE001
            errors.append(_error_text(error))
            break
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {
        "p50": _percentile(samples, 50) if samples else 0.0,
        "p95": _percentile(samples, 95) if samples else 0.0,
        "runs": len(samples),
        "scope": LATENCY_SCOPE,
    }


def _target(name: str, goal: object, value: object) -> dict[str, object]:
    return {
        "name": name,
        "goal": goal,
        "value": value,
        "status": "PASS" if value == goal and type(value) is type(goal) else "FAIL",
    }


def run_evaluation() -> dict[str, object]:
    errors: list[str] = []
    ids = grocery_ingredient_ids(PLAN)
    if set(ids) != set(LINE_PRODUCTS):
        raise ValueError("fixture lines MUST match the plan lines")
    shop = Shop()
    preview: CartPreview | None = None
    try:
        preview = build_preview(PLAN, shop.client(), LOCATION)
    except Exception as error:  # noqa: BLE001
        errors.append(_error_text(error))
    match: dict[str, object]
    safety: dict[str, object]
    if preview is None:
        match = {
            "lines": len(LINE_PRODUCTS),
            "matched": 0,
            "unmatched": -1,
            "rate": 0.0,
        }
        sold_out_chosen = -1
        safety = {
            "cart_requests_before_add": -1,
            "cart_requests_by_add": 0,
            "add_items_equal_preview": False,
        }
    else:
        match = _product_match(preview)
        sold_out_chosen = sum(1 for item in preview.items if item.upc in SOLD_OUT_UPCS)
        safety = _cart_safety(shop, preview, errors)
    expected_unmatched = sum(
        1 for products in LINE_PRODUCTS.values() if not _choosable(products)
    )
    failures = _failure_handling(errors)
    quote = _quote_label(errors)
    latency = _code_latency(errors)
    measures: dict[str, object] = {
        "product_match": match,
        "cart_safety": safety,
        "failure_handling": failures,
        "secret_scan": {},
        "quote_label": quote,
        "code_latency_ms": latency,
    }
    head = [
        _target("out_of_stock_chosen", 0, sold_out_chosen),
        _target("unmatched_listed", expected_unmatched, match["unmatched"]),
        _target("cart_requests_before_add", 0, safety["cart_requests_before_add"]),
        _target("add_items_equal_preview", True, safety["add_items_equal_preview"]),
        *(
            _target(f"partial_preview_{row['error']}", False, row["partial_preview"])
            for row in failures
        ),
    ]
    targets = [
        *head,
        _target("quote_store_label", True, quote["store_label"]),
        _target("quote_utc_read_time", True, quote["utc_read_time"]),
    ]
    report: dict[str, object] = {
        "version": VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "measures": measures,
        "targets": targets,
    }
    scan = {
        "preview": _hits(preview.model_dump_json()) if preview is not None else 0,
        "errors": _hits("\n".join(errors)),
        "report": 0,
    }
    measures["secret_scan"] = {**scan, "count": sum(scan.values())}
    scan["report"] = _hits(json.dumps(report, sort_keys=True))
    total = sum(scan.values())
    measures["secret_scan"] = {**scan, "count": total}
    targets.insert(len(head), _target("secret_hits", 0, total))
    return report


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(_INVALID) from None


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(
            prog="python -m app.evaluation_kroger", allow_abbrev=False, add_help=False
        )
        parser.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        if not args.output or os.path.lexists(args.output):
            raise ValueError(_INVALID)
    except ValueError:
        print(_INVALID, file=sys.stderr)
        return 2
    try:
        text = json.dumps(run_evaluation(), indent=2, sort_keys=True) + "\n"
        with Path(args.output).open("x", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        print(_INVALID, file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001
        print("Evaluation failed", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
