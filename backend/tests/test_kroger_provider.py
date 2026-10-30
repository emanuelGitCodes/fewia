"""Tests for the Kroger client, using invented data and a mock transport."""

import base64
import logging
import threading
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.providers import kroger
from app.providers.kroger import KrogerClient, KrogerUnavailable

CLIENT_ID = "SENTINEL-CLIENT-ID"
SECRET = "SENTINEL-SECRET"
TOKEN = "SENTINEL-ACCESS-TOKEN"
ZIP = "98765"
BASE = "https://kroger.test"
LOCATION = "01234567"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Server:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_status = 200
        self.token_body: dict[str, object] = {"access_token": TOKEN, "expires_in": 1800}
        self.data_status = 200
        self.data_headers: dict[str, str] = {}
        self.locations: object = {"data": []}
        self.products: object = {"data": []}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/connect/oauth2/token":
            return httpx.Response(self.token_status, json=self.token_body)
        body = self.locations if path == "/v1/locations" else self.products
        return httpx.Response(self.data_status, json=body, headers=self.data_headers)

    def count(self, path: str) -> int:
        return sum(1 for r in self.requests if r.url.path == path)


def _make(
    server: Server, clock: Clock | None = None, day: date = date(2030, 1, 1)
) -> tuple[KrogerClient, Clock]:
    clock = clock or Clock()
    http = httpx.Client(transport=httpx.MockTransport(server))
    client = KrogerClient(
        CLIENT_ID, SECRET, base_url=BASE, client=http, clock=clock, today=lambda: day
    )
    return client, clock


def _store(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "locationId": LOCATION,
        "name": "Test Market",
        "chain": "TESTCHAIN",
        "address": {
            "addressLine1": "1 Example Way",
            "city": "Sampleton",
            "state": "ZZ",
            "zipCode": "00000",
        },
    }
    entry.update(overrides)
    return entry


def _product(
    price: dict[str, object] | None = None, **overrides: object
) -> dict[str, object]:
    entry: dict[str, object] = {
        "productId": "0001112223334",
        "upc": "0001112223334",
        "description": "Invented Ground Beef",
        "brand": "Made Up",
        "items": [
            {
                "size": "1 lb",
                "soldBy": "UNIT",
                "inventory": {"stockLevel": "HIGH"},
                "price": price if price is not None else {"regular": 2.49, "promo": 0},
            }
        ],
    }
    entry.update(overrides)
    return entry


def test_token_request_shape_and_reuse() -> None:
    server = Server()
    client, clock = _make(server)
    client.find_stores(ZIP)
    client.find_stores(ZIP)
    assert server.count("/v1/connect/oauth2/token") == 1
    request = server.requests[0]
    expected = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    assert request.headers["authorization"] == f"Basic {expected}"
    form = parse_qs(request.content.decode())
    assert form == {"grant_type": ["client_credentials"], "scope": ["product.compact"]}
    assert server.requests[1].headers["authorization"] == f"Bearer {TOKEN}"
    clock.now += 1800 - 60
    client.find_stores(ZIP)
    assert server.count("/v1/connect/oauth2/token") == 2


def test_expires_in_just_above_margin_is_accepted() -> None:
    server = Server()
    server.token_body = {"access_token": TOKEN, "expires_in": 61}
    client, _ = _make(server)
    assert client.find_stores(ZIP) == []


def test_huge_prices_become_none() -> None:
    server = Server()
    server.products = {
        "data": [
            _product(price={"regular": 1e30, "promo": 100000.01}, productId="P1"),
            _product(price={"regular": 100000, "promo": 1.5}, productId="P2"),
        ]
    }
    client, _ = _make(server)
    by_id = {p.product_id: p for p in client.search_products("x", LOCATION).products}
    assert (by_id["P1"].regular_cents, by_id["P1"].promo_cents) == (None, None)
    assert (by_id["P2"].regular_cents, by_id["P2"].promo_cents) == (10_000_000, 150)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (10**400, None),
        (1e30, None),
        (float("nan"), None),
        (float("inf"), None),
        (-1, None),
        (0, None),
        (True, None),
        ("2.49", None),
        (None, None),
        (2.49, 249),
        (2.495, 250),
        (100000, 10_000_000),
        (100000.01, None),
    ],
)
def test_cents_is_total(value: object, expected: int | None) -> None:
    assert kroger._cents(value) == expected


def test_search_products_keeps_product_with_huge_price() -> None:
    server = Server()
    server.products = {"data": [_product(price={"regular": 10**400, "promo": 1.5})]}
    client, _ = _make(server)
    (product,) = client.search_products("x", LOCATION).products
    assert (product.regular_cents, product.promo_cents) == (None, 150)


def test_clean_strips_line_and_paragraph_separators() -> None:
    assert kroger._clean("a b c") == "abc"


def test_products_budget_per_utc_day() -> None:
    server = Server()
    client, _ = _make(server)
    for _ in range(10_000):
        client.search_products("milk", LOCATION)
    sent = len(server.requests)
    with pytest.raises(KrogerUnavailable):
        client.search_products("milk", LOCATION)
    assert len(server.requests) == sent
    client.find_stores(ZIP)
    assert len(server.requests) == sent + 1


@pytest.mark.parametrize("expires", [0, -5, 60, "1800", None, True, 1.5])
def test_bad_expires_in_is_unavailable(expires: object) -> None:
    server = Server()
    server.token_body = {"access_token": TOKEN, "expires_in": expires}
    client, _ = _make(server)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    server.token_body = {"access_token": TOKEN}
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)


def test_find_stores_parses_and_skips_malformed() -> None:
    server = Server()
    server.locations = {
        "data": [
            _store(),
            _store(locationId="0123456"),
            _store(name=None),
            _store(address="nope"),
            "junk",
            _store(locationId="ABCDEFGH", name="A\x00\nB" + "x" * 300),
        ]
    }
    client, _ = _make(server)
    stores = client.find_stores(ZIP, limit=3)
    assert [s.location_id for s in stores] == [LOCATION, "ABCDEFGH"]
    assert stores[0].city == "Sampleton"
    assert stores[1].name.startswith("AB") and len(stores[1].name) == 160
    query = server.requests[1].url.params
    assert query["filter.zipCode.near"] == ZIP and query["filter.limit"] == "3"


@pytest.mark.parametrize("zip_code", ["1234", "123456", "12a45", "１２３４５", ""])
def test_find_stores_rejects_bad_zip(zip_code: str) -> None:
    server = Server()
    client, _ = _make(server)
    with pytest.raises(ValueError, match="5 digits") as exc_info:
        client.find_stores(zip_code)
    assert zip_code not in str(exc_info.value) or zip_code == ""
    assert server.requests == []


def test_search_products_prices_and_text() -> None:
    server = Server()
    server.data_headers = {"Cache-Control": "max-age=60"}
    server.products = {
        "data": [
            _product(),
            _product(price={"regular": 2.495, "promo": 1.1}, productId="P2"),
            _product(price={"regular": 0}, productId="P3"),
            _product(price={"regular": -1.0, "promo": "1"}, productId="P4"),
            _product(description="Bad\x07Text" + "y" * 300, productId="P5"),
            _product(items=[], productId="P6"),
            _product(description=None, productId="P7"),
            "junk",
        ]
    }
    client, _ = _make(server)
    result = client.search_products("ground beef", LOCATION)
    by_id = {p.product_id: p for p in result.products}
    assert list(by_id) == ["0001112223334", "P2", "P3", "P4", "P5"]
    first = by_id["0001112223334"]
    assert (first.regular_cents, first.promo_cents) == (249, None)
    assert first.stock_level == "HIGH" and first.size == "1 lb"
    assert (by_id["P2"].regular_cents, by_id["P2"].promo_cents) == (250, 110)
    assert (by_id["P3"].regular_cents, by_id["P3"].promo_cents) == (None, None)
    assert (by_id["P4"].regular_cents, by_id["P4"].promo_cents) == (None, None)
    assert by_id["P5"].description.startswith("BadText")
    assert len(by_id["P5"].description) == 160
    assert result.cache_control == "max-age=60"
    query = server.requests[1].url.params
    assert query["filter.term"] == "ground beef"
    assert query["filter.locationId"] == LOCATION


def test_search_products_without_cache_header_and_bad_input() -> None:
    server = Server()
    client, _ = _make(server)
    assert client.search_products("milk", LOCATION).cache_control is None
    for term, loc in [
        ("", LOCATION),
        ("x" * 65, LOCATION),
        ("a\nb", LOCATION),
        ("ok", "short"),
    ]:
        with pytest.raises(ValueError):
            client.search_products(term, loc)


def test_429_starts_cooldown() -> None:
    server = Server()
    client, clock = _make(server)
    client.find_stores(ZIP)
    server.data_status = 429
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    sent = len(server.requests)
    clock.now += 599
    server.data_status = 200
    with pytest.raises(KrogerUnavailable):
        client.search_products("milk", LOCATION)
    assert len(server.requests) == sent
    clock.now += 1
    client.search_products("milk", LOCATION)
    assert len(server.requests) == sent + 1


def test_locations_budget_per_utc_day() -> None:
    server = Server()
    client, _ = _make(server)
    for _ in range(1600):
        client.find_stores(ZIP)
    sent = len(server.requests)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    assert len(server.requests) == sent
    client.search_products("milk", LOCATION)
    assert len(server.requests) == sent + 1


def test_budget_resets_next_day() -> None:
    server = Server()
    days = [date(2030, 1, 1)]
    http = httpx.Client(transport=httpx.MockTransport(server))
    client = KrogerClient(
        CLIENT_ID, SECRET, base_url=BASE, client=http, today=lambda: days[0]
    )
    for _ in range(1600):
        client.find_stores(ZIP)
    sent = len(server.requests)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    assert len(server.requests) == sent
    days[0] = date(2030, 1, 2)
    client.find_stores(ZIP)
    assert len(server.requests) == sent + 1


def test_401_drops_token() -> None:
    server = Server()
    client, _ = _make(server)
    client.search_products("milk", LOCATION)
    server.data_status = 401
    with pytest.raises(KrogerUnavailable):
        client.search_products("milk", LOCATION)
    server.data_status = 200
    client.search_products("milk", LOCATION)
    assert server.count("/v1/connect/oauth2/token") == 2


@pytest.mark.parametrize("status", [302, 500, 403])
def test_non_200_and_redirect_are_unavailable(status: int) -> None:
    server = Server()
    server.token_status = status
    client, _ = _make(server)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    assert len(server.requests) == 1


def test_data_redirect_not_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/connect/oauth2/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 1800})
        return httpx.Response(302, headers={"Location": f"{BASE}/elsewhere"})

    calls: list[httpx.Request] = []
    http = httpx.Client(follow_redirects=True, transport=httpx.MockTransport(handler))
    client = KrogerClient(CLIENT_ID, SECRET, base_url=BASE, client=http)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    assert all(r.url.path != "/elsewhere" for r in calls)


def test_truncated_token_body_has_no_cause_or_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"access_token": "abc')

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = KrogerClient(CLIENT_ID, SECRET, base_url=BASE, client=http)
    with pytest.raises(KrogerUnavailable) as exc_info:
        client.find_stores(ZIP)
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None


def test_concurrent_find_stores_makes_one_token_request() -> None:
    server = Server()
    server.locations = {"data": [_store()]}
    client, _ = _make(server)
    results: list[int] = []

    def work() -> None:
        results.append(len(client.find_stores(ZIP)))

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [1] * 8
    assert server.count("/v1/connect/oauth2/token") == 1
    assert server.count("/v1/locations") == 8


def test_transport_error_and_invalid_json() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"{CLIENT_ID} {SECRET} {ZIP}")

    http = httpx.Client(transport=httpx.MockTransport(boom))
    client = KrogerClient(CLIENT_ID, SECRET, base_url=BASE, client=http)
    with pytest.raises(KrogerUnavailable) as exc_info:
        client.find_stores(ZIP)
    assert str(exc_info.value) == "Kroger is unavailable"
    assert exc_info.value.__cause__ is None

    def bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    http = httpx.Client(transport=httpx.MockTransport(bad_json))
    client = KrogerClient(CLIENT_ID, SECRET, base_url=BASE, client=http)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)


def test_no_sentinels_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    server = Server()
    server.data_status = 500
    client, _ = _make(server)
    with pytest.raises(KrogerUnavailable) as exc_info:
        client.find_stores(ZIP)
    rendered = f"{exc_info.value!s}{exc_info.value!r}{caplog.text}"
    for sentinel in (CLIENT_ID, SECRET, TOKEN, ZIP):
        assert sentinel not in rendered


def test_httpx_info_records_dropped_even_after_setlevel(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.providers.http_client import build_http_client

    build_http_client(BASE).close()
    caplog.set_level(logging.DEBUG)
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            logger.info("HTTP Request: GET https://x/?filter.zipCode.near=%s", ZIP)
        finally:
            logger.setLevel(previous)
    assert not any(ZIP in record.getMessage() for record in caplog.records)


def test_failed_token_request_does_not_charge_budget() -> None:
    server = Server()
    server.token_status = 500
    client, _ = _make(server)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    server.token_status = 200
    for _ in range(1600):
        client.find_stores(ZIP)
    sent = len(server.requests)
    with pytest.raises(KrogerUnavailable):
        client.find_stores(ZIP)
    assert len(server.requests) == sent


def test_clean_strips_format_characters() -> None:
    server = Server()
    server.locations = {"data": [_store(name="A‮B​C")]}
    client, _ = _make(server)
    assert client.find_stores(ZIP)[0].name == "ABC"


def test_location_id_not_trimmed_before_match() -> None:
    server = Server()
    server.locations = {"data": [_store(locationId=" 01234567 ")]}
    client, _ = _make(server)
    assert client.find_stores(ZIP) == []


def test_token_reused_just_before_margin() -> None:
    server = Server()
    client, clock = _make(server)
    client.find_stores(ZIP)
    clock.now += 1800 - 61
    client.find_stores(ZIP)
    assert server.count("/v1/connect/oauth2/token") == 1


def test_base_urls() -> None:
    assert kroger.kroger_base_url("certification") == "https://api-ce.kroger.com"
    assert kroger.kroger_base_url("production") == "https://api.kroger.com"


def _smoke_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "id").write_text(CLIENT_ID, encoding="utf-8")
    (tmp_path / "secret").write_text(f"{SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("FEWIA_KROGER_CLIENT_ID_FILE", str(tmp_path / "id"))
    monkeypatch.setenv("FEWIA_KROGER_SECRET_FILE", str(tmp_path / "secret"))


def test_smoke_prints_products_and_cache_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _smoke_env(monkeypatch, tmp_path)
    server = Server()
    server.locations = {"data": [_store()]}
    server.products = {"data": [_product()]}
    server.data_headers = {"Cache-Control": "max-age=5"}
    real = httpx.Client

    def fake_build(base_url: str) -> httpx.Client:
        return real(transport=httpx.MockTransport(server))

    monkeypatch.setattr(kroger, "build_http_client", fake_build)
    assert kroger.main(["--zip", ZIP, "--term", "ground beef"]) == 0
    out = capsys.readouterr().out
    assert "Test Market\tInvented Ground Beef\t1 lb\t249\tnone\tHIGH" in out
    assert "cache-control locations: max-age=5" in out
    assert "cache-control products: max-age=5" in out
    assert "cache-control token: none" in out
    for sentinel in (CLIENT_ID, SECRET, TOKEN, ZIP):
        assert sentinel not in out


def test_smoke_without_stores_reports_products_not_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _smoke_env(monkeypatch, tmp_path)
    server = Server()
    monkeypatch.setattr(
        kroger,
        "build_http_client",
        lambda base_url: httpx.Client(transport=httpx.MockTransport(server)),
    )
    assert kroger.main(["--zip", ZIP, "--term", "milk"]) == 0
    out = capsys.readouterr().out
    assert "cache-control products: not requested" in out


def test_smoke_exits_2_when_unconfigured_or_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FEWIA_KROGER_CLIENT_ID_FILE", raising=False)
    monkeypatch.delenv("FEWIA_KROGER_SECRET_FILE", raising=False)
    assert kroger.main(["--zip", ZIP, "--term", "milk"]) == 2
    _smoke_env(monkeypatch, tmp_path)
    server = Server()
    server.token_status = 500
    monkeypatch.setattr(
        kroger,
        "build_http_client",
        lambda base_url: httpx.Client(transport=httpx.MockTransport(server)),
    )
    assert kroger.main(["--zip", ZIP, "--term", "milk"]) == 2
    out = capsys.readouterr().out
    assert "Kroger is unavailable" in out
    for sentinel in (CLIENT_ID, SECRET, TOKEN, ZIP):
        assert sentinel not in out
