"""Tests for trusted hosts, docs routes, and request bounds."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.chat_models import CreateChatJobBody
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import GroceryRequest
from app.domain.plan_proposal import ProposalDietaryConstraints
from app.main import HostCheckMiddleware, allowed_hosts, create_app, host_name

DEFAULT_HOSTS = ["localhost", "127.0.0.1", "[::1]", "api"]
REJECTED_HOST_BODY = {
    "error": {"code": "bad_request", "message": "The Host header is not allowed."}
}
INGREDIENT_ID = next(iter(INGREDIENTS))
OVER_LIMIT_CENTS = 100_000_001
MEALS = [{"recipe_id": "bean_tacos", "servings": 2}]


@pytest.fixture(autouse=True)
def _clear_hardening_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEWIA_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("FEWIA_API_DOCS", raising=False)


def grocery_request(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"meals": MEALS, "budget_period": "2026-09-01"}
    body.update(overrides)
    return body


def post_grocery_job(client: TestClient, request: dict[str, object]) -> int:
    response = client.post(
        "/grocery/jobs",
        json={"request": request, "monthly_limit_cents": 40000},
        headers={"Idempotency-Key": "hardening-1"},
    )
    status_code: int = response.status_code
    return status_code


def call_app(
    app: ASGIApp, scope_type: str, headers: list[tuple[bytes, bytes]]
) -> list[Message]:
    """Run one raw ASGI request through the app and return the sent messages."""
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": scope_type,
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/healthz",
        "raw_path": b"/healthz",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    return sent


@pytest.mark.parametrize(
    "host",
    [
        "localhost:8010",
        "127.0.0.1:8000",
        "api:8000",
        "[::1]:8000",
        "[::1]",
        "LOCALHOST:8010",
    ],
)
def test_healthz_accepts_default_hosts(host: str) -> None:
    client = TestClient(create_app(), base_url="http://localhost")

    response = client.get("/healthz", headers={"host": host})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "testserver",
        "127.0.0.1.evil.example",
        "localhost.evil.example",
        "evil.example:8010",
        "[::2]:8000",
    ],
)
def test_healthz_rejects_another_host(host: str) -> None:
    client = TestClient(create_app(), base_url="http://localhost")

    response = client.get("/healthz", headers={"host": host})

    assert response.status_code == 400
    assert response.json() == REJECTED_HOST_BODY
    assert response.headers["content-type"] == "application/json"


def test_healthz_rejects_two_host_headers() -> None:
    sent = call_app(
        create_app(),
        "http",
        [(b"host", b"localhost"), (b"host", b"localhost")],
    )

    assert sent[0]["status"] == 400
    assert json.loads(sent[1]["body"]) == REJECTED_HOST_BODY


def test_healthz_rejects_a_missing_host_header() -> None:
    sent = call_app(create_app(), "http", [])

    assert sent[0]["status"] == 400


def test_healthz_accepts_a_configured_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEWIA_ALLOWED_HOSTS", "Fewia.Example.org")
    client = TestClient(create_app(), base_url="http://localhost")

    configured = client.get("/healthz", headers={"host": "fewia.example.org"})
    other = client.get("/healthz", headers={"host": "evil.example"})

    assert configured.status_code == 200
    assert other.status_code == 400


def test_host_check_passes_other_scope_types_through() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    middleware = HostCheckMiddleware(inner, ["localhost"])
    scope: Scope = {"type": "lifespan"}

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        raise AssertionError(message)

    asyncio.run(middleware(scope, receive, send))

    assert seen == ["lifespan"]


def test_host_check_closes_a_rejected_websocket() -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("the app must not run")

    sent = call_app(
        HostCheckMiddleware(inner, ["localhost"]),
        "websocket",
        [(b"host", b"evil.example")],
    )

    assert [message["type"] for message in sent] == ["websocket.close"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("localhost", "localhost"),
        ("localhost:8010", "localhost"),
        ("[::1]:8000", "[::1]"),
        ("[::1]", "[::1]"),
        ("LocalHost:80", "localhost"),
        ("", None),
        (":8000", None),
        ("localhost:", None),
        ("localhost:abc", None),
        ("localhost:123456", None),
        ("a:b:c", None),
        ("[::1]x", None),
        ("[::1", None),
        ("evil.example/", None),
        ("user@localhost", None),
        ("local host", None),
        ("local\thost", None),
    ],
)
def test_host_name(value: str, expected: str | None) -> None:
    assert host_name(value) == expected


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_routes_are_off_by_default(path: str) -> None:
    client = TestClient(create_app(), base_url="http://localhost")

    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_routes_turn_on_with_the_flag(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setenv("FEWIA_API_DOCS", "1")
    client = TestClient(create_app(), base_url="http://localhost")

    assert client.get(path).status_code == 200


def test_openapi_schema_builds_without_the_docs_routes() -> None:
    schema = create_app().openapi()

    assert "/healthz" in schema["paths"]


def test_allowed_hosts_without_extras_returns_the_defaults() -> None:
    assert allowed_hosts(None) == DEFAULT_HOSTS
    assert allowed_hosts("") == DEFAULT_HOSTS
    assert allowed_hosts(" , ,") == DEFAULT_HOSTS


def test_allowed_hosts_trims_extras_and_drops_empty_entries() -> None:
    result = allowed_hosts(" one.example , two.example ,, ")

    assert result == [*DEFAULT_HOSTS, "one.example", "two.example"]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "ok.example,*",
        "*.example.org",
        "a.example/b",
        "a b.example",
        "a.example:80",
    ],
)
def test_allowed_hosts_rejects_invalid_entries(value: str) -> None:
    with pytest.raises(ValueError, match=r"^FEWIA_ALLOWED_HOSTS is invalid\.$"):
        allowed_hosts(value)


def test_allowed_hosts_lower_cases_extras() -> None:
    assert allowed_hosts("Fewia.Example.org") == [*DEFAULT_HOSTS, "fewia.example.org"]


def test_allowed_hosts_accepts_the_bracketed_ipv6_form() -> None:
    assert allowed_hosts("[::1]") == [*DEFAULT_HOSTS, "[::1]"]


def test_create_app_rejects_an_invalid_host_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEWIA_ALLOWED_HOSTS", "*")

    with pytest.raises(ValueError, match="FEWIA_ALLOWED_HOSTS is invalid."):
        create_app()


def test_grocery_request_accepts_64_pantry_ingredients() -> None:
    request = GroceryRequest.model_validate(
        grocery_request(pantry_ingredients=[INGREDIENT_ID] * 64)
    )

    assert len(request.pantry_ingredients) == 64


def test_grocery_request_accepts_64_exclusions() -> None:
    request = GroceryRequest.model_validate(
        grocery_request(ingredient_exclusions=[INGREDIENT_ID] * 64)
    )

    assert len(request.ingredient_exclusions) == 64


@pytest.mark.parametrize("field", ["pantry_ingredients", "ingredient_exclusions"])
def test_grocery_request_rejects_65_entries(field: str) -> None:
    with pytest.raises(ValidationError):
        GroceryRequest.model_validate(grocery_request(**{field: [INGREDIENT_ID] * 65}))


@pytest.mark.parametrize("field", ["pantry_ingredients", "ingredient_exclusions"])
def test_grocery_request_limits_entry_length_to_160(field: str) -> None:
    accepted = GroceryRequest.model_validate(grocery_request(**{field: ["a" * 160]}))

    assert getattr(accepted, field) == ["a" * 160]
    with pytest.raises(ValidationError):
        GroceryRequest.model_validate(grocery_request(**{field: ["a" * 161]}))


def test_grocery_request_rejects_a_cap_over_the_limit() -> None:
    with pytest.raises(ValidationError):
        GroceryRequest.model_validate(grocery_request(plan_cap_cents=OVER_LIMIT_CENTS))


def test_grocery_job_route_rejects_65_pantry_ingredients(client: TestClient) -> None:
    request = grocery_request(pantry_ingredients=[INGREDIENT_ID] * 65)

    assert post_grocery_job(client, request) == 422


def test_grocery_job_route_rejects_a_cap_over_the_limit(client: TestClient) -> None:
    request = grocery_request(plan_cap_cents=OVER_LIMIT_CENTS)

    assert post_grocery_job(client, request) == 422


@pytest.mark.parametrize("field", ["monthly_limit_cents", "plan_cap_cents"])
def test_chat_job_route_rejects_cents_over_the_limit(
    client: TestClient, field: str
) -> None:
    body: dict[str, object] = {
        "message": "plan chicken tacos",
        "monthly_limit_cents": 40000,
    }
    body[field] = OVER_LIMIT_CENTS

    response = client.post(
        "/grocery/chat/jobs", json=body, headers={"Idempotency-Key": "hardening-2"}
    )

    assert response.status_code == 422


def test_chat_body_accepts_cents_at_the_limit() -> None:
    body = CreateChatJobBody.model_validate(
        {
            "message": "plan chicken tacos",
            "monthly_limit_cents": 100_000_000,
            "plan_cap_cents": 100_000_000,
        }
    )

    assert body.monthly_limit_cents == 100_000_000


def test_proposal_constraints_accept_64_exclusions() -> None:
    constraints = ProposalDietaryConstraints(ingredient_exclusions=["egg"] * 64)

    assert len(constraints.ingredient_exclusions) == 64


def test_proposal_constraints_reject_65_exclusions() -> None:
    with pytest.raises(ValidationError):
        ProposalDietaryConstraints(ingredient_exclusions=["egg"] * 65)


def test_proposal_constraints_limit_entry_length_to_160() -> None:
    ProposalDietaryConstraints(ingredient_exclusions=["a" * 160])

    with pytest.raises(ValidationError):
        ProposalDietaryConstraints(ingredient_exclusions=["a" * 161])
