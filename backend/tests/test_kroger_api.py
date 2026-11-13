"""Exercise Kroger ownership and one-use actions with synthetic credentials."""

import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event, Lock
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import UserSeeder, require_test_database_url
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.pool import StaticPool

from app import kroger_pairing_cli
from app.api import kroger as routes
from app.auth import AuthSettings
from app.db import Base
from app.deps import (
    get_current_user,
    get_kroger_cipher,
    get_kroger_client,
    get_kroger_pairing_cipher,
    get_provider_settings,
    get_session,
)
from app.kroger_customer import store_tokens
from app.kroger_models import KrogerCustomerToken
from app.main import app
from app.models import User
from app.plan_models import PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.providers import kroger
from app.providers.kroger import CartItem, CustomerTokens, KrogerClient
from app.security_models import KrogerOwner, QuotaCounter, SecurityIntent
from app.services import kroger_security as security
from app.services import security_admission as admission


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database:
        yield database
    engine.dispose()


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    cipher = Fernet(Fernet.generate_key())
    settings = GroceryProviderSettings(kroger_mode="fixture")
    monkeypatch.setattr("app.deps.load_auth_settings", lambda: AuthSettings())

    def forbid_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests MUST NOT use the network.")

    monkeypatch.setattr(kroger, "build_http_client", forbid_network)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbid_network)
    dependencies = {
        get_kroger_client: lambda: None,
        get_kroger_cipher: lambda: cipher,
        get_kroger_pairing_cipher: lambda: cipher,
        get_provider_settings: lambda: settings,
    }
    previous = dict(app.dependency_overrides)
    app.dependency_overrides.update(dependencies)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


SENTINEL_ZIP = "97531"
BASE = "https://kroger.test"
URL = "/grocery/kroger/stores"


def _store() -> dict[str, object]:
    return {
        "locationId": "01234567",
        "name": "Invented Market",
        "chain": "INVENTED",
        "address": {
            "addressLine1": "1 Test Way",
            "city": "Testville",
            "state": "ZZ",
            "zipCode": "00000",
        },
    }


def _client(handler: httpx.MockTransport) -> KrogerClient:
    http = httpx.Client(transport=handler)
    return KrogerClient("invented-id", "invented-secret", base_url=BASE, client=http)


@pytest.fixture
def api(client: TestClient, seed_user: UserSeeder) -> TestClient:
    seed_user(1)
    return client


def _override(client: KrogerClient | None) -> None:
    app.dependency_overrides[get_kroger_client] = lambda: client


def test_returns_stores_without_store_zip(api: TestClient) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        return httpx.Response(200, json={"data": [_store()]})

    _override(_client(httpx.MockTransport(handler)))
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 200
    assert response.json() == {
        "stores": [
            {
                "location_id": "01234567",
                "name": "Invented Market",
                "address_line": "1 Test Way",
                "city": "Testville",
                "state": "ZZ",
            }
        ],
        "source": "live",
    }
    assert seen[-1].url.params["filter.zipCode.near"] == SENTINEL_ZIP


def _locations_calls(
    api: TestClient, responses: list[list[dict[str, object]]]
) -> tuple[httpx.Response, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        calls.append(request)
        return httpx.Response(200, json={"data": responses[len(calls) - 1]})

    _override(_client(httpx.MockTransport(handler)))
    return api.post(URL, json={"zip_code": SENTINEL_ZIP}), calls


def test_wider_search_runs_once_when_first_is_empty(api: TestClient) -> None:
    store = _store()
    store["name"] = "INVENTED - - Far Spoke"
    store["chain"] = "INVENTED"
    response, calls = _locations_calls(api, [[], [store]])
    assert response.status_code == 200
    assert response.json()["stores"][0]["name"] == "Far Spoke"
    assert len(calls) == 2
    assert "filter.radiusInMiles" not in calls[0].url.params
    assert calls[1].url.params["filter.radiusInMiles"] == "50"


def test_no_wider_search_when_first_has_stores(api: TestClient) -> None:
    response, calls = _locations_calls(api, [[_store()]])
    assert response.status_code == 200
    assert len(calls) == 1


def test_at_most_two_calls_when_both_empty(api: TestClient) -> None:
    response, calls = _locations_calls(api, [[], []])
    assert response.status_code == 200
    assert response.json() == {"stores": [], "source": "live"}
    assert len(calls) == 2


def test_not_configured(api: TestClient) -> None:
    _override(None)
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Kroger is not configured"


def _assert_no_sentinel(caplog: pytest.LogCaptureFixture, text: str) -> None:
    assert SENTINEL_ZIP not in text
    for record in caplog.records:
        assert SENTINEL_ZIP not in record.getMessage()
        assert SENTINEL_ZIP not in str(record.args)
    assert SENTINEL_ZIP not in caplog.text


def _token_then(status: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
        return httpx.Response(status)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("status", [500, 429])
def test_unavailable_hides_zip(
    api: TestClient, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    caplog.set_level(logging.DEBUG)
    _override(_client(_token_then(status)))
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Kroger is unavailable"
    _assert_no_sentinel(caplog, response.text)


def test_token_failure_hides_zip(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _override(_client(httpx.MockTransport(lambda r: httpx.Response(500))))
    response = api.post(URL, json={"zip_code": SENTINEL_ZIP})
    assert response.status_code == 503
    _assert_no_sentinel(caplog, response.text)


@pytest.mark.parametrize("bad", ["97531x", "9753", "975311", "9753a", "", "97 31"])
def test_bad_zip_is_422_without_echo(
    api: TestClient, caplog: pytest.LogCaptureFixture, bad: str
) -> None:
    caplog.set_level(logging.DEBUG)
    _override(_client(httpx.MockTransport(lambda r: httpx.Response(500))))
    response = api.post(URL, json={"zip_code": bad})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "zip_code MUST be exactly 5 digits"
    assert bad not in response.text if bad else True
    _assert_no_sentinel(caplog, response.text)


def test_bad_zip_is_422_even_when_not_configured(api: TestClient) -> None:
    _override(None)
    response = api.post(URL, json={"zip_code": "9753"})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "zip_code MUST be exactly 5 digits"


def test_invalid_body_detail_is_empty(api: TestClient) -> None:
    _override(None)
    for body in ({"zip_code": 97531}, {"zip_code": SENTINEL_ZIP, "extra": 1}, {}):
        response = api.post(URL, json=body)
        assert response.status_code == 422
        assert response.json()["error"]["detail"] == []
        assert SENTINEL_ZIP not in response.text


def test_get_is_405_and_query_zip_unused(api: TestClient) -> None:
    _override(None)
    assert api.get(URL, params={"zip_code": SENTINEL_ZIP}).status_code == 405
    response = api.post(URL, params={"zip_code": SENTINEL_ZIP}, json={})
    assert response.status_code == 422


CONNECT = "/grocery/kroger/connect"
START = CONNECT + "/start"
CALLBACK = "/grocery/kroger/callback"
CONNECTION = "/grocery/kroger/connection"
REDEEM = "/grocery/kroger/pairing/redeem"
PREVIEW = "/grocery/kroger/cart/preview"
CART_ADD = "/grocery/kroger/cart/add"
REDIRECT = "http://localhost:8010/grocery/kroger/callback"
RETURN_URL = "http://127.0.0.1:5173/prototype"
CODE = "SENTINEL-AUTH-CODE"
ACCESS = "SENTINEL-ACCESS-TOKEN"
REFRESH = "SENTINEL-REFRESH-TOKEN"
UPC = "0001112223334"


@dataclass
class Rig:
    api: TestClient
    session: Session
    cipher: Fernet
    pairing_cipher: Fernet
    headers: dict[str, str] = field(default_factory=dict)
    token_status: int = 200
    cart_status: int = 204
    cart_error: httpx.RequestError | None = None
    calls: list[httpx.Request] = field(default_factory=list)
    hook: Callable[[httpx.Request], None] | None = None
    locks_held: bool = False
    settings: GroceryProviderSettings = field(
        default_factory=lambda: GroceryProviderSettings(
            kroger_redirect_uri=REDIRECT, kroger_return_url=RETURN_URL
        )
    )

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert not self.locks_held
        self.calls.append(request)
        if self.hook is not None:
            self.hook(request)
        if request.url.path == kroger.CART_ADD_PATH:
            if self.cart_error is not None:
                raise self.cart_error
            return httpx.Response(self.cart_status)
        if request.url.path == kroger.PRODUCTS_PATH:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "productId": "invented",
                            "upc": UPC,
                            "description": "Invented product",
                            "items": [{"size": "1 lb"}],
                        }
                    ]
                },
            )
        if request.url.path == kroger.LOCATIONS_PATH:
            return httpx.Response(200, json={"data": [_store()]})
        return httpx.Response(
            self.token_status,
            json={
                "access_token": ACCESS,
                "refresh_token": REFRESH,
                "expires_in": 1800,
                "error": "invalid_grant",
            },
        )

    def proof(self, owner_id: int = 1) -> str:
        ticket = security.issue_pairing_ticket(self.session, owner_id)
        proof = security.redeem_pairing_ticket(self.session, owner_id, ticket)
        self.session.commit()
        return proof

    def connected(
        self, owner_id: int = 1, expired: bool = False
    ) -> KrogerCustomerToken:
        store_tokens(
            self.session, owner_id, self.cipher, CustomerTokens(ACCESS, REFRESH, 1800)
        )
        row = self.session.get(KrogerCustomerToken, owner_id)
        assert row is not None
        if expired:
            row.access_expires_at = datetime.now(UTC) - timedelta(seconds=5)
        self.session.commit()
        return row

    def plan(self, owner_id: int = 1) -> UUID:
        revision_id = uuid4()
        self.session.add(
            PlanRevision(
                id=revision_id,
                user_id=owner_id,
                snapshot={
                    "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
                    "pantry_ingredient_ids": ["olive_oil", "cumin", "salt"],
                    "plan_cap_cents": None,
                },
            )
        )
        self.session.commit()
        return revision_id

    def preview(self, revision: UUID | None = None) -> httpx.Response:
        revision = revision or self.plan()
        return self.api.post(
            PREVIEW,
            headers=self.headers,
            json={"plan_revision_id": str(revision), "location_id": "01234567"},
        )

    def confirmation(self, owner_id: int = 1, now: int | None = None) -> str:
        token = security.issue_cart_confirmation(
            self.session,
            owner_id,
            self.pairing_cipher,
            self.plan(owner_id),
            [security.CartLine(upc=UPC, quantity=2)],
            now_seconds=now,
        )
        self.session.commit()
        return token

    def add(self, token: str) -> httpx.Response:
        return self.api.post(
            CART_ADD, headers=self.headers, json={"confirmation_token": token}
        )

    def start(self) -> tuple[str, str]:
        posted = self.api.post(CONNECT, headers=self.headers)
        assert posted.status_code == 200
        assert set(posted.json()) == {"authorization_url"}
        target = posted.json()["authorization_url"]
        assert target.startswith("/api/grocery/kroger/connect/start?ticket=")
        assert "set-cookie" not in posted.headers
        started = self.api.get(target.removeprefix("/api"), follow_redirects=False)
        assert started.status_code == 302
        assert "set-cookie" not in started.headers
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        return target, state

    def callback(self, state: str) -> httpx.Response:
        return self.api.get(
            CALLBACK, params={"code": CODE, "state": state}, follow_redirects=False
        )


@pytest.fixture
def rig(client: TestClient, session: Session, seed_user: UserSeeder) -> Rig:
    seed_user(1)
    seed_user(2)
    session.commit()
    rig = Rig(
        client, session, Fernet(Fernet.generate_key()), Fernet(Fernet.generate_key())
    )

    def capture(state: ORMExecuteState) -> None:
        if state.is_select and "FOR UPDATE" in str(
            state.statement.compile(dialect=postgresql.dialect())
        ):
            rig.locks_held = True

    def released(database: Session, transaction: object) -> None:
        if not database.in_transaction():
            rig.locks_held = False

    event.listen(session, "do_orm_execute", capture)
    event.listen(session, "after_transaction_end", released)
    provider = KrogerClient(
        "invented-id",
        "invented-secret",
        base_url=kroger.HOSTS["certification"],
        client=httpx.Client(transport=httpx.MockTransport(rig.handle)),
    )
    app.dependency_overrides.update(
        {
            get_kroger_client: lambda: provider,
            get_kroger_cipher: lambda: rig.cipher,
            get_kroger_pairing_cipher: lambda: rig.pairing_cipher,
            get_provider_settings: lambda: rig.settings,
        }
    )
    rig.headers = {"X-FEWIA-Kroger-Owner": rig.proof()}
    return rig


def _intent(rig: Rig, raw: str) -> SecurityIntent:
    row = rig.session.scalar(
        select(SecurityIntent).where(
            SecurityIntent.digest == hashlib.sha256(raw.encode()).hexdigest()
        )
    )
    assert row is not None
    return row


def test_pairing_redeems_once_and_returns_eight_hour_proof(rig: Rig) -> None:
    ticket = security.issue_pairing_ticket(rig.session, 1)
    rig.session.commit()
    redeemed = rig.api.post(REDEEM, json={"ticket": ticket})
    assert redeemed.status_code == 200
    assert redeemed.json()["expires_in_seconds"] == 28800
    proof = redeemed.json()["proof"]
    assert len(proof) == 43 and proof != ticket
    assert _intent(rig, ticket).state == "consumed"
    assert _intent(rig, proof).details["purpose"] == "tab_proof"
    assert rig.api.post(REDEEM, json={"ticket": ticket}).status_code == 422
    assert (
        rig.api.get(CONNECTION, headers={"X-FEWIA-Kroger-Owner": proof}).status_code
        == 200
    )
    assert rig.calls == []


@pytest.mark.parametrize("reason", ["expired", "revoked", "foreign"])
def test_pairing_rejects_invalid_ticket(rig: Rig, reason: str) -> None:
    ticket = security.issue_pairing_ticket(rig.session, 2 if reason == "foreign" else 1)
    if reason == "expired":
        _intent(rig, ticket).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    if reason == "revoked":
        security.revoke_pairing(rig.session, 1)
    rig.session.commit()
    response = rig.api.post(REDEEM, json={"ticket": ticket})
    assert response.status_code == 422
    assert ticket not in response.text
    assert rig.calls == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", CONNECTION, None),
        ("DELETE", CONNECTION, None),
        ("POST", CONNECT, None),
        ("POST", URL, {"zip_code": "12345"}),
        ("POST", PREVIEW, None),
        ("POST", CART_ADD, None),
    ],
)
@pytest.mark.parametrize("proof", [None, "1", "x" * 43])
def test_live_operations_require_opaque_proof(
    rig: Rig, method: str, path: str, body: object, proof: str | None
) -> None:
    rig.connected()
    if path == PREVIEW:
        body = {"plan_revision_id": str(rig.plan()), "location_id": "01234567"}
    if path == CART_ADD:
        body = {"confirmation_token": rig.confirmation()}
    headers = {"X-FEWIA-Kroger-Owner-ID": "1"}
    if proof is not None:
        headers["X-FEWIA-Kroger-Owner"] = proof
    response = rig.api.request(method, path, json=body, headers=headers)
    assert response.status_code == 403
    assert rig.calls == []


def test_duplicate_and_expired_proofs_fail(rig: Rig) -> None:
    proof = rig.headers["X-FEWIA-Kroger-Owner"]
    duplicate = [("X-FEWIA-Kroger-Owner", proof)] * 2
    assert rig.api.get(CONNECTION, headers=duplicate).status_code == 403
    _intent(rig, proof).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    rig.session.commit()
    assert rig.api.get(CONNECTION, headers=rig.headers).status_code == 403


@pytest.mark.parametrize("path", [CONNECTION, CONNECT, URL, PREVIEW, CART_ADD])
def test_live_mode_fails_closed_without_pairing_cipher(rig: Rig, path: str) -> None:
    app.dependency_overrides[get_kroger_pairing_cipher] = lambda: None
    if path == CONNECTION:
        response = rig.api.get(path, headers=rig.headers)
    else:
        body = {
            URL: {"zip_code": "12345"},
            PREVIEW: {
                "plan_revision_id": str(rig.plan()),
                "location_id": "01234567",
            },
            CART_ADD: {"confirmation_token": "synthetic"},
        }.get(path)
        response = rig.api.post(path, headers=rig.headers, json=body)
    assert response.status_code == 503
    assert rig.calls == []


def test_start_ticket_is_one_use_and_callback_retains_existing_session(
    rig: Rig,
) -> None:
    target, state = rig.start()
    assert rig.api.get(target.removeprefix("/api")).status_code == 422
    response = rig.callback(state)
    assert response.headers["location"] == RETURN_URL + "?kroger=connected"
    assert "set-cookie" not in response.headers
    assert _intent(rig, state).state == "consumed"
    row = rig.session.get(KrogerCustomerToken, 1)
    assert row is not None
    assert rig.cipher.decrypt(row.access_token).decode() == ACCESS
    version = row.connection_version
    assert rig.callback(state).headers["location"].endswith("kroger=error")
    assert len(rig.calls) == 1
    assert row.connection_version == version
    assert rig.api.get(CONNECTION, headers=rig.headers).json() == {"connected": True}


def test_callback_replay_during_exchange_cannot_exchange_twice(rig: Rig) -> None:
    _, state = rig.start()

    def replay(request: httpx.Request) -> None:
        rig.hook = None
        assert rig.callback(state).headers["location"].endswith("kroger=error")

    rig.hook = replay
    assert rig.callback(state).headers["location"].endswith("kroger=connected")
    assert len(rig.calls) == 1


@pytest.mark.parametrize("when", ["before_start", "before_exchange", "during_exchange"])
def test_oauth_is_bound_to_pairing_generation(rig: Rig, when: str) -> None:
    if when == "before_start":
        posted = rig.api.post(CONNECT, headers=rig.headers)
        security.revoke_pairing(rig.session, 1)
        rig.session.commit()
        target = posted.json()["authorization_url"].removeprefix("/api")
        assert rig.api.get(target).status_code == 422
        assert rig.calls == []
        return
    _, state = rig.start()

    def revoke() -> None:
        security.revoke_pairing(rig.session, 1)
        rig.session.commit()

    if when == "before_exchange":
        revoke()
    else:
        rig.hook = lambda request: revoke()
    assert rig.callback(state).headers["location"].endswith("kroger=error")
    assert rig.session.get(KrogerCustomerToken, 1) is None
    assert len(rig.calls) == (1 if when == "during_exchange" else 0)


@pytest.mark.parametrize("reason", ["expired", "foreign", "provider", "database"])
def test_callback_failure_keeps_existing_connection(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    original = rig.connected().connection_version
    _, state = rig.start()
    if reason == "expired":
        _intent(rig, state).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        rig.session.commit()
    elif reason == "foreign":
        app.dependency_overrides[get_current_user] = lambda: rig.session.get(User, 2)
    elif reason == "provider":
        rig.token_status = 500
    else:

        def fail(*args: object, **kwargs: object) -> None:
            raise SQLAlchemyError("SENTINEL-DATABASE")

        monkeypatch.setattr(routes, "store_tokens", fail)
    response = rig.callback(state)
    assert response.headers["location"].endswith("kroger=error")
    row = rig.session.get(KrogerCustomerToken, 1)
    assert row is not None and row.connection_version == original


@pytest.mark.parametrize("refusal", ["quota", "owner"])
def test_refusal_does_not_consume_pending_oauth_state(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    _, state = rig.start()
    reserve = admission.reserve_action

    def refuse(*args: object, **kwargs: object) -> None:
        if refusal == "quota":
            raise admission.AdmissionLimitError(7)
        raise admission.OwnerUnavailableError()

    monkeypatch.setattr(admission, "reserve_action", refuse)
    response = rig.callback(state)
    assert response.status_code == (429 if refusal == "quota" else 403)
    assert _intent(rig, state).state == "pending"
    assert rig.calls == []
    monkeypatch.setattr(admission, "reserve_action", reserve)
    assert rig.callback(state).headers["location"].endswith("kroger=connected")


@pytest.mark.parametrize(
    "bad",
    [
        [("code", CODE), ("code", "SENTINEL-SECOND")],
        [("state", "SENTINEL-STATE")],
        [("code", "SENTINEL-" * 600)],
        [("error", "SENTINEL-ERROR")],
        [("other", "SENTINEL-" * 600)],
    ],
)
def test_callback_rejects_bad_query_without_echo_or_state_consumption(
    rig: Rig, bad: list[tuple[str, str]]
) -> None:
    _, state = rig.start()
    params = [("code", CODE), ("state", state), *bad]
    response = rig.api.get(CALLBACK, params=params, follow_redirects=False)
    assert response.headers["location"].endswith("kroger=error")
    assert "SENTINEL" not in response.text + str(response.headers)
    assert _intent(rig, state).state == "pending"
    assert rig.calls == []


def test_reconnect_changes_connection_version(rig: Rig) -> None:
    original = rig.connected().connection_version
    _, state = rig.start()
    assert rig.callback(state).headers["location"].endswith("kroger=connected")
    current = rig.session.get(KrogerCustomerToken, 1)
    assert current is not None and current.connection_version != original


def test_disconnect_deletes_only_current_tokens_and_revokes_proofs(rig: Rig) -> None:
    rig.connected()
    other = rig.connected(2).connection_version
    response = rig.api.delete(CONNECTION, headers=rig.headers)
    assert response.status_code == 204 and response.content == b""
    assert rig.session.get(KrogerCustomerToken, 1) is None
    row = rig.session.get(KrogerCustomerToken, 2)
    assert row is not None and row.connection_version == other
    assert rig.api.get(CONNECTION, headers=rig.headers).status_code == 403
    rig.headers["X-FEWIA-Kroger-Owner"] = rig.proof()
    assert rig.api.get(CONNECTION, headers=rig.headers).json() == {"connected": False}
    assert rig.api.delete(CONNECTION, headers=rig.headers).status_code == 204


def test_preview_issues_confirmation_and_keeps_only_safe_intent_details(
    rig: Rig,
) -> None:
    rig.connected()
    revision = rig.plan()
    response = rig.preview(revision)
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in_seconds"] == 300
    assert len(body["items"]) == 1
    token = body["confirmation_token"]
    payload = json.loads(rig.pairing_cipher.decrypt(token.encode()))
    assert set(payload) == {
        "owner_id",
        "pairing_generation",
        "connection_version",
        "plan_revision",
        "action_id",
        "items",
        "expires_at",
    }
    assert payload["owner_id"] == 1 and payload["plan_revision"] == str(revision)
    details = _intent(rig, token).details
    assert set(details) == {
        "action_id",
        "input_sha256",
        "pairing_generation",
        "connection_version",
    }
    assert UPC not in json.dumps(details)
    assert token not in json.dumps(details)
    assert rig.add(token).status_code == 204


def test_preview_hides_foreign_plan_and_rechecks_generation(rig: Rig) -> None:
    rig.connected()
    foreign = rig.plan(2)
    assert rig.preview(foreign).status_code == 404
    assert rig.calls == []

    def revoke(request: httpx.Request) -> None:
        rig.hook = None
        security.revoke_pairing(rig.session, 1)
        rig.session.commit()

    rig.hook = revoke
    assert rig.preview().status_code == 403
    assert (
        rig.session.scalar(
            select(SecurityIntent).where(SecurityIntent.kind == "cart_confirmation")
        )
        is None
    )


@pytest.mark.parametrize("kind", ["signature", "expiry", "owner", "version"])
def test_cart_confirmation_rejects_invalid_binding(rig: Rig, kind: str) -> None:
    rig.connected()
    rig.connected(2)
    token = rig.confirmation(
        2 if kind == "owner" else 1,
        int(time.time()) - 301 if kind == "expiry" else None,
    )
    if kind == "signature":
        row = _intent(rig, token)
        token = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
        row.digest = hashlib.sha256(token.encode()).hexdigest()
        rig.session.commit()
    elif kind == "version":
        rig.connected()
    assert rig.add(token).status_code == 422
    assert rig.calls == []


@pytest.mark.parametrize(
    ("status", "expected", "state"),
    [
        (204, 204, "succeeded"),
        (400, 503, "failed"),
        (401, 409, "failed"),
        (429, 503, "failed"),
        (500, 504, "uncertain"),
        (503, 504, "uncertain"),
    ],
)
def test_cart_replays_terminal_result_without_second_call_or_quota(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, status: int, expected: int, state: str
) -> None:
    rig.connected()
    token = rig.confirmation()
    rig.cart_status = status
    first = rig.add(token)
    assert first.status_code == expected
    assert _intent(rig, token).state == state

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Replays MUST NOT reserve admission.")

    monkeypatch.setattr(admission, "reserve_action", forbid)
    assert rig.add(token).status_code == expected
    assert len(rig.calls) == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectTimeout("SENTINEL"), 503),
        (httpx.ReadTimeout("SENTINEL"), 504),
        (httpx.WriteError("SENTINEL"), 504),
    ],
)
def test_cart_transport_outcomes_stay_terminal(
    rig: Rig, error: httpx.RequestError, expected: int
) -> None:
    rig.connected()
    token = rig.confirmation()
    rig.cart_error = error
    assert rig.add(token).status_code == expected
    assert rig.add(token).status_code == expected
    assert len(rig.calls) == 1


def test_claimed_cart_replay_is_unknown_without_second_call(rig: Rig) -> None:
    rig.connected()
    token = rig.confirmation()

    def replay(request: httpx.Request) -> None:
        rig.hook = None
        assert rig.add(token).status_code == 504

    rig.hook = replay
    assert rig.add(token).status_code == 204
    assert rig.add(token).status_code == 204
    assert len(rig.calls) == 1


def test_refresh_keeps_connection_version_and_commits_before_cart(rig: Rig) -> None:
    original = rig.connected(expired=True).connection_version
    token = rig.confirmation()
    assert rig.add(token).status_code == 204
    assert len(rig.calls) == 2
    row = rig.session.get(KrogerCustomerToken, 1)
    assert row is not None and row.connection_version == original
    assert rig.calls[-1].headers["authorization"] == "Bearer " + ACCESS


@pytest.mark.parametrize("change", ["connection", "generation"])
def test_cart_rechecks_connection_between_claim_and_token_load(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    original_version = rig.connected().connection_version
    token = rig.confirmation()
    load_token = routes.customer_access_token

    def change_before_lookup(
        db: Session,
        user_id: int,
        client: KrogerClient,
        cipher: Fernet,
        *,
        expected_connection_version: UUID | None = None,
        expected_pairing_generation: UUID | None = None,
    ) -> str | None:
        assert not db.in_transaction()
        assert _intent(rig, token).state == "claimed"
        db.commit()
        assert expected_connection_version == original_version
        assert expected_pairing_generation is not None
        with Session(db.get_bind()) as other:
            admission.lock_active_owner(other, user_id)
            if change == "connection":
                store_tokens(
                    other, user_id, cipher, CustomerTokens("WINNER", "WINNER-R", 1800)
                )
            else:
                security.revoke_pairing(other, user_id)
            other.commit()
        return load_token(
            db,
            user_id,
            client,
            cipher,
            expected_connection_version=expected_connection_version,
            expected_pairing_generation=expected_pairing_generation,
        )

    monkeypatch.setattr(routes, "customer_access_token", change_before_lookup)
    response = rig.add(token)
    assert response.status_code == 409
    assert response.json()["error"]["message"] == routes.NOT_CONNECTED_MESSAGE
    assert _intent(rig, token).state == "failed"
    assert rig.calls == []
    current = rig.session.get(KrogerCustomerToken, 1)
    assert current is not None
    if change == "connection":
        assert current.connection_version != original_version
        assert rig.cipher.decrypt(current.access_token) == b"WINNER"


@pytest.mark.parametrize("refresh_status", [200, 401])
@pytest.mark.parametrize("change", ["connection", "generation"])
def test_cart_rechecks_connection_after_refresh(
    rig: Rig, refresh_status: int, change: str
) -> None:
    original_version = rig.connected(expired=True).connection_version
    token = rig.confirmation()
    rig.token_status = refresh_status
    replacement_pair: list[tuple[bytes, bytes]] = []

    def replace(request: httpx.Request) -> None:
        assert request.url.path.endswith("/token")
        assert not rig.session.in_transaction()
        with Session(rig.session.get_bind()) as other:
            admission.lock_active_owner(other, 1)
            if change == "connection":
                store_tokens(
                    other, 1, rig.cipher, CustomerTokens("WINNER", "WINNER-R", 1800)
                )
            else:
                security.revoke_pairing(other, 1)
            current = other.get(KrogerCustomerToken, 1)
            assert current is not None
            replacement_pair.append((current.access_token, current.refresh_token))
            other.commit()

    rig.hook = replace
    response = rig.add(token)
    assert response.status_code == 409
    assert response.json()["error"]["message"] == routes.NOT_CONNECTED_MESSAGE
    assert _intent(rig, token).state == "failed"
    assert len(rig.calls) == 1
    assert rig.calls[0].url.path.endswith("/token")
    current = rig.session.get(KrogerCustomerToken, 1)
    assert current is not None
    assert (current.access_token, current.refresh_token) == replacement_pair[0]
    assert (current.connection_version != original_version) == (change == "connection")


def test_stale_cart_401_preserves_reconnect_with_the_same_token(rig: Rig) -> None:
    original_version = rig.connected().connection_version
    token = rig.confirmation()
    rig.cart_status = 401

    def reconnect(request: httpx.Request) -> None:
        assert request.url.path == kroger.CART_ADD_PATH
        assert request.headers["authorization"] == "Bearer " + ACCESS
        with Session(rig.session.get_bind()) as other:
            admission.lock_active_owner(other, 1)
            store_tokens(other, 1, rig.cipher, CustomerTokens(ACCESS, REFRESH, 1800))
            other.commit()

    rig.hook = reconnect
    assert rig.add(token).status_code == 409
    current = rig.session.get(KrogerCustomerToken, 1)
    assert current is not None
    assert current.connection_version != original_version
    assert rig.cipher.decrypt(current.access_token).decode() == ACCESS
    assert rig.add(token).status_code == 409
    assert len(rig.calls) == 1


@pytest.mark.parametrize("reconnect", [False, True])
def test_stale_cart_401_preserves_a_replacement(rig: Rig, reconnect: bool) -> None:
    row = rig.connected()
    original = row.connection_version
    token = rig.confirmation()
    rig.cart_status = 401

    def replace(request: httpx.Request) -> None:
        if reconnect:
            store_tokens(
                rig.session, 1, rig.cipher, CustomerTokens("WINNER", "WINNER-R", 1800)
            )
        else:
            current = rig.session.get(KrogerCustomerToken, 1)
            assert current is not None
            current.access_token = rig.cipher.encrypt(b"WINNER")
            current.refresh_token = rig.cipher.encrypt(b"WINNER-R")
        rig.session.commit()

    rig.hook = replace
    assert rig.add(token).status_code == 409
    current = rig.session.get(KrogerCustomerToken, 1)
    assert current is not None
    assert rig.cipher.decrypt(current.access_token) == b"WINNER"
    assert (current.connection_version != original) == reconnect
    assert rig.add(token).status_code == 409
    assert len(rig.calls) == 1


def test_current_user_scopes_store_connection_preview_and_cart(rig: Rig) -> None:
    rig.connected(2)
    other_plan = rig.plan(2)
    other_token = rig.confirmation(2)
    assert rig.api.get(CONNECTION, headers=rig.headers).json() == {"connected": False}
    assert rig.preview(other_plan).status_code == 404
    assert rig.add(other_token).status_code == 422
    assert rig.calls == []
    second_proof = rig.proof(2)
    app.dependency_overrides[get_current_user] = lambda: rig.session.get(User, 2)
    rig.headers = {"X-FEWIA-Kroger-Owner": second_proof, "X-User-ID": "1"}
    assert rig.api.get(CONNECTION, headers=rig.headers).json() == {"connected": True}
    seen: list[int] = []
    reserve = admission.reserve_action

    def capture(db: Session, owner: int, action: admission.Action) -> None:
        seen.append(owner)
        reserve(db, owner, action)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(admission, "reserve_action", capture)
        found = rig.api.post(URL, headers=rig.headers, json={"zip_code": "12345"})
        assert found.status_code == 200
        assert rig.preview(other_plan).status_code == 200
        assert rig.add(other_token).status_code == 204
    assert seen == [2, 2, 2]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (REDEEM, {"ticket": "SENTINEL-" * 1000}),
        (REDEEM, {"ticket": {"SENTINEL": "SENTINEL"}}),
        (PREVIEW, {"plan_revision_id": "SENTINEL", "location_id": "SENTINEL"}),
        (CART_ADD, {"confirmation_token": "SENTINEL-" * 5000}),
        (CART_ADD, {"confirmation_token": {"SENTINEL": "SENTINEL"}}),
        (CART_ADD, {"items": [{"upc": "SENTINEL", "quantity": "SENTINEL"}]}),
        (URL, {"zip_code": {"SENTINEL": "SENTINEL"}}),
    ],
)
def test_validation_hides_sentinel_inputs(
    rig: Rig, path: str, body: dict[str, object]
) -> None:
    response = rig.api.post(path, headers=rig.headers, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["detail"] == []
    assert "SENTINEL" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert rig.calls == []


def test_no_http_route_mints_pairing_tickets(rig: Rig) -> None:
    for path in ("/pairing", "/pairing/ticket", "/pairing/issue"):
        assert rig.api.post("/grocery/kroger" + path).status_code == 404
    assert rig.api.get(CONNECT).status_code == 405


@pytest.mark.parametrize(
    ("host", "accepted"),
    [
        ("postgres", True),
        ("localhost", True),
        ("127.0.0.1", True),
        ("[::1]", True),
        ("postgres.example.test", False),
        ("db.postgres", False),
        ("postgres-remote", False),
        ("postgres.", False),
        ("POSTGRES", False),
        ("remote.test", False),
        ("192.0.2.1", False),
        ("[2001:db8::1]", False),
    ],
)
def test_operator_cli_database_allowlist(host: str, accepted: bool) -> None:
    engine = create_engine(f"postgresql+psycopg://synthetic@{host}:5432/fewia")
    try:
        assert kroger_pairing_cli._local_database(engine) is accepted
    finally:
        engine.dispose()


@pytest.mark.parametrize("host", ["postgres", "localhost", "127.0.0.1", "[::1]"])
@pytest.mark.parametrize(
    "query",
    [
        "host=remote.test",
        "hostaddr=192.0.2.1",
        "service=remote",
        "host=postgres",
        "hostaddr=127.0.0.1",
        "service=local",
    ],
)
def test_operator_cli_database_refuses_dsn_overrides(host: str, query: str) -> None:
    engine = create_engine(f"postgresql+psycopg://synthetic@{host}:5432/fewia?{query}")
    try:
        assert not kroger_pairing_cli._local_database(engine)
    finally:
        engine.dispose()


def test_operator_cli_prints_only_fragment_and_commits_ticket(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        kroger_pairing_cli, "load_auth_settings", lambda: AuthSettings()
    )
    monkeypatch.setattr(
        kroger_pairing_cli, "load_provider_settings", lambda: rig.settings
    )
    monkeypatch.setattr(
        kroger_pairing_cli, "get_kroger_pairing_cipher", lambda: rig.pairing_cipher
    )
    monkeypatch.setattr(kroger_pairing_cli, "SessionLocal", lambda: rig.session)
    assert kroger_pairing_cli.main(["--user-id", "1"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.startswith("#kroger-pair=")
    ticket = unquote(output.out.strip().split("=", 1)[1])
    assert len(ticket) == 43
    row = _intent(rig, ticket)
    assert row.kind == "pairing_ticket" and row.state == "pending"
    assert row.details["purpose"] == "pairing_ticket"
    expiry = row.expires_at.replace(tzinfo=UTC)
    assert 290 < (expiry - datetime.now(UTC)).total_seconds() <= 300
    assert rig.calls == []


@pytest.mark.parametrize(
    "reason", ["fixture", "missing_key", "owner", "disabled", "aws"]
)
def test_operator_cli_refuses_unsafe_context(
    rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reason: str,
) -> None:
    monkeypatch.setattr(
        kroger_pairing_cli, "load_auth_settings", lambda: AuthSettings()
    )
    settings = (
        rig.settings.model_copy(update={"kroger_mode": "fixture"})
        if reason == "fixture"
        else rig.settings
    )
    monkeypatch.setattr(kroger_pairing_cli, "load_provider_settings", lambda: settings)
    cipher = None if reason == "missing_key" else rig.pairing_cipher
    monkeypatch.setattr(kroger_pairing_cli, "get_kroger_pairing_cipher", lambda: cipher)
    monkeypatch.setattr(kroger_pairing_cli, "SessionLocal", lambda: rig.session)
    if reason == "disabled":
        owner = rig.session.get(User, 1)
        assert owner is not None
        owner.status = "disabled"
        rig.session.commit()
    if reason == "aws":
        monkeypatch.setattr(kroger_pairing_cli, "_local_database", lambda bind: False)
    result = kroger_pairing_cli.main(["--user-id", "2" if reason == "owner" else "1"])
    assert result == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Kroger pairing is unavailable.\n"
    assert rig.calls == []


def test_concurrent_callback_replay_exchanges_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        make_url(require_test_database_url()).set(drivername="postgresql+psycopg"),
        connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    )
    user_id = (uuid4().int >> 66) + 1
    cipher = Fernet(Fernet.generate_key())
    entered, release, calls_lock = Event(), Event(), Lock()
    exchanges: list[str] = []
    settings = GroceryProviderSettings(
        kroger_redirect_uri=REDIRECT, kroger_return_url=RETURN_URL
    )

    def exchange(request: httpx.Request) -> httpx.Response:
        with calls_lock:
            exchanges.append(request.method)
        entered.set()
        assert release.wait(10)
        return httpx.Response(
            200,
            json={"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 1800},
        )

    provider = KrogerClient(
        "invented-id",
        "invented-secret",
        base_url=BASE,
        client=httpx.Client(transport=httpx.MockTransport(exchange)),
    )

    def database() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    def callback() -> httpx.Response:
        with TestClient(app, base_url="http://localhost") as browser:
            return browser.get(
                CALLBACK, params={"code": CODE, "state": state}, follow_redirects=False
            )

    try:
        with Session(engine, expire_on_commit=False) as db:
            owner = User(id=user_id, display_name="Synthetic callback owner")
            db.add(owner)
            db.flush()
            state = security.issue_oauth_state(db, user_id)
            db.commit()
        for dependency, override in (
            (get_session, database),
            (get_current_user, lambda: owner),
            (get_provider_settings, lambda: settings),
            (get_kroger_client, lambda: provider),
            (get_kroger_cipher, lambda: cipher),
            (get_kroger_pairing_cipher, lambda: cipher),
        ):
            monkeypatch.setitem(app.dependency_overrides, dependency, override)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(callback)
            try:
                assert entered.wait(5)
                second = executor.submit(callback).result(timeout=8)
                assert second.headers["location"].endswith("kroger=error")
            finally:
                release.set()
            connected = first.result(timeout=5)
            assert connected.headers["location"].endswith("kroger=connected")
        assert exchanges == ["POST"]
        with Session(engine) as db:
            assert db.get(KrogerCustomerToken, user_id) is not None
    finally:
        release.set()
        with Session(engine) as db:
            db.execute(
                delete(KrogerCustomerToken).where(
                    KrogerCustomerToken.user_id == user_id
                )
            )
            db.execute(delete(SecurityIntent).where(SecurityIntent.user_id == user_id))
            db.execute(delete(KrogerOwner).where(KrogerOwner.user_id == user_id))
            db.execute(delete(QuotaCounter).where(QuotaCounter.scope_key == user_id))
            db.execute(delete(User).where(User.id == user_id))
            db.commit()
        engine.dispose()


def test_rejected_cart_records_static_422_and_replays_once(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.connected()
    token = rig.confirmation()
    calls: list[str] = []

    def reject(
        self: KrogerClient, access_token: str, items: Sequence[CartItem]
    ) -> None:
        calls.append("add")
        raise ValueError("SENTINEL-PROVIDER-ERROR")

    monkeypatch.setattr(KrogerClient, "add_to_cart", reject)
    for _ in range(2):
        response = rig.add(token)
        assert response.status_code == 422
        assert "SENTINEL" not in response.text
    assert calls == ["add"]
    assert _intent(rig, token).state == "failed"


def test_missing_connection_after_claim_records_409(rig: Rig) -> None:
    rig.connected(expired=True)
    token = rig.confirmation()
    rig.token_status = 401
    assert rig.add(token).status_code == 409
    assert rig.add(token).status_code == 409
    assert _intent(rig, token).state == "failed"
    assert rig.session.get(KrogerCustomerToken, 1) is None
    assert len(rig.calls) == 1


def test_callback_rechecks_active_owner_after_exchange(rig: Rig) -> None:
    _, state = rig.start()

    def disable(request: httpx.Request) -> None:
        owner = rig.session.get(User, 1)
        assert owner is not None
        owner.status = "disabled"
        rig.session.commit()

    rig.hook = disable
    response = rig.callback(state)
    assert response.headers["location"].endswith("kroger=error")
    assert rig.session.get(KrogerCustomerToken, 1) is None
    assert len(rig.calls) == 1


def test_callback_refreshes_retained_owner_after_exchange(rig: Rig) -> None:
    _, state = rig.start()
    retained = rig.session.get(KrogerOwner, 1)
    assert retained is not None
    original_generation = retained.pairing_generation
    rig.session.commit()

    def revoke_elsewhere(request: httpx.Request) -> None:
        with Session(rig.session.get_bind()) as other:
            security.revoke_pairing(other, 1)
            other.commit()
        assert retained.pairing_generation == original_generation

    rig.hook = revoke_elsewhere
    response = rig.callback(state)
    assert response.headers["location"].endswith("kroger=error")
    assert retained.pairing_generation != original_generation
    assert rig.session.get(KrogerCustomerToken, 1) is None
    assert len(rig.calls) == 1


def test_pairing_ticket_and_tab_proof_have_distinct_purposes(rig: Rig) -> None:
    ticket = security.issue_pairing_ticket(rig.session, 1)
    rig.session.commit()
    assert (
        rig.api.get(CONNECTION, headers={"X-FEWIA-Kroger-Owner": ticket}).status_code
        == 403
    )
    proof = rig.headers["X-FEWIA-Kroger-Owner"]
    assert rig.api.post(REDEEM, json={"ticket": proof}).status_code == 422
    assert _intent(rig, ticket).state == "pending"


def test_cart_result_write_failure_returns_unknown_without_retry(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.connected()
    token = rig.confirmation()

    def fail(*args: object, **kwargs: object) -> security.CartOutcome:
        raise SQLAlchemyError("SENTINEL-RESULT-WRITE")

    monkeypatch.setattr(security, "record_cart_outcome", fail)
    for _ in range(2):
        response = rig.add(token)
        assert response.status_code == 504
        assert "SENTINEL" not in response.text
    assert _intent(rig, token).state == "claimed"
    assert len(rig.calls) == 1


def test_uncertain_result_cannot_be_upgraded_to_success(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.connected()
    token = rig.confirmation()
    record = security.record_cart_outcome

    def uncertain(
        db: Session, user_id: int, intent_id: UUID, state: security.TerminalState
    ) -> security.CartOutcome:
        return record(db, user_id, intent_id, "uncertain")

    monkeypatch.setattr(security, "record_cart_outcome", uncertain)
    assert rig.add(token).status_code == 504
    assert rig.add(token).status_code == 504
    assert _intent(rig, token).state == "uncertain"
    assert len(rig.calls) == 1
