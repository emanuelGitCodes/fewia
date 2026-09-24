"""Tests for the Plaid sync HTTP routes."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import UserSeeder
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import sync as sync_api
from app.api.sync_models import CreateSyncJobBody
from app.deps import get_session
from app.job_models import Job, JobOutbox
from app.main import app as main_app
from app.plaid_models import PlaidItem
from app.provider_settings import GroceryProviderSettings
from app.services.job_submission import create_job

ITEM_ID = "item-1"
OTHER_ITEM_ID = "item-2"
JOBS_PATH = "/grocery/sync/jobs"
ITEMS_PATH = "/grocery/sync/items"
SENTINEL = "SECRET_DB_TOKEN"
SYNCED_AT = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)
ITEM_PUBLIC_FIELDS = frozenset({"id", "last_synced_at"})
FORBIDDEN_FIELDS = ("token", "account", "transaction", "access_token", "cursor")
INTERNAL_JOB_FIELDS = (
    "payload",
    "lease_token",
    "lease_expires_at",
    "request_key",
    "user_id",
    "attempts",
    "kind",
)


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    test_app = FastAPI()
    test_app.exception_handlers.update(main_app.exception_handlers)
    test_app.include_router(sync_api.router)

    def get_test_session() -> Iterator[Session]:
        yield session

    test_app.dependency_overrides[get_session] = get_test_session
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    calls: list[str] = []

    def commit() -> None:
        calls.append("commit")
        session.flush()

    monkeypatch.setattr(session, "commit", commit)
    return calls


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> GroceryProviderSettings:
    settings = GroceryProviderSettings(
        plaid_client_id="test-plaid-client",
        plaid_secret_file=Path("secret"),
        plaid_tokens_file=Path("tokens"),
    )
    monkeypatch.setattr(sync_api, "get_provider_settings", lambda: settings)
    return settings


@pytest.fixture(autouse=True)
def forbid_provider_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("providers and secret files MUST NOT be used")

    monkeypatch.setattr("app.provider_runtime.build_plaid", boom)
    monkeypatch.setattr("app.provider_runtime.build_bedrock", boom)
    monkeypatch.setattr("app.provider_runtime.build_instacart", boom)
    monkeypatch.setattr("app.provider_runtime.read_secret_file", boom)
    monkeypatch.setattr("app.provider_settings.read_secret_file", boom)
    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", boom)


def job_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"item_id": ITEM_ID}
    body.update(overrides)
    return body


def post_job(
    client: TestClient,
    *,
    key: str = "sync-1",
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    request_headers = {} if headers is None else dict(headers)
    names = {name.lower() for name in request_headers}
    if "idempotency-key" not in names:
        request_headers["Idempotency-Key"] = key
    return client.post(JOBS_PATH, json=body or job_body(), headers=request_headers)


def seed_item(
    session: Session,
    *,
    item_id: str = ITEM_ID,
    user_id: int = 1,
    last_synced_at: datetime | None = None,
    credential_ref: str = "plaid-item-ref",
    cursor: str | None = None,
    provider_item_id: str | None = None,
) -> PlaidItem:
    item = PlaidItem(
        id=item_id,
        user_id=user_id,
        provider_item_id=provider_item_id or f"provider-{item_id}",
        credential_ref=credential_ref,
        cursor=cursor,
        last_synced_at=last_synced_at,
    )
    session.add(item)
    session.flush()
    return item


def miss_first_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    lookups = {"count": 0}
    real = sync_api._existing_sync_job

    def lookup(session: Session, request_key: str) -> Job | None:
        lookups["count"] += 1
        if lookups["count"] == 1:
            return None
        return real(session, request_key)

    monkeypatch.setattr(sync_api, "_existing_sync_job", lookup)


def secret_blob(value: object) -> str:
    return str(value).lower()


def raise_secret_integrity(*_args: object, **_kwargs: object) -> None:
    raise IntegrityError("INSERT", {"token": SENTINEL}, Exception(SENTINEL))


def raise_secret_value(*_args: object, **_kwargs: object) -> None:
    raise ValueError(SENTINEL)


def assert_static_http_error(error: HTTPException, status: int, detail: str) -> None:
    assert error.status_code == status
    assert error.detail == detail
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = str(error) + repr(error)
    assert SENTINEL not in rendered


def test_sync_routes_are_mounted_on_main_app() -> None:
    operations = frozenset(
        {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
    )
    inventory = main_app.openapi()["paths"]
    routes = {
        (path, method.upper())
        for path, spec in inventory.items()
        for method in spec
        if method in operations
    }
    assert (JOBS_PATH, "POST") in routes
    assert (f"{JOBS_PATH}/{{job_id}}", "GET") in routes
    assert (ITEMS_PATH, "GET") in routes


def test_repeated_identical_request_reuses_job_and_outbox(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    commit_without_ending_the_test_transaction: list[str],
) -> None:
    seed_user()
    seed_item(session)
    first = post_job(client)
    second = post_job(client)
    job_id = first.json()["job_id"]
    jobs = session.scalars(select(Job).where(Job.id == job_id)).all()
    outboxes = session.scalars(
        select(JobOutbox).where(JobOutbox.job_id == job_id)
    ).all()
    stored = session.get(Job, job_id)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()
    assert first.json()["status"] == "queued"
    assert len(jobs) == 1
    assert len(outboxes) == 1
    assert outboxes[0].published_at is None
    assert stored is not None
    assert stored.kind == "sync"
    assert stored.user_id == 1
    assert stored.request_key == "sync:sync-1"
    assert stored.payload == {"operation": "plaid_sync", "item_id": ITEM_ID}
    for field in FORBIDDEN_FIELDS:
        assert field not in stored.payload
    assert commit_without_ending_the_test_transaction


def test_changed_item_id_conflicts(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session)
    seed_item(session, item_id=OTHER_ITEM_ID)
    first = post_job(client)
    second = post_job(client, body=job_body(item_id=OTHER_ITEM_ID))

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["message"] == sync_api.CONFLICT_MESSAGE


def test_insert_race_same_fields_keeps_winner_snapshot(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {"operation": "plaid_sync", "item_id": ITEM_ID}
    winner, _created = create_job(session, 1, "sync", "sync:race-same", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    response = post_job(client, key="race-same")
    stored = session.get(Job, winner.id)

    assert response.status_code == 202
    assert response.json()["job_id"] == winner.id
    assert stored is not None
    assert stored.payload == payload


def test_insert_race_different_fields_keeps_conflict(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {
        "operation": "plaid_sync",
        "item_id": OTHER_ITEM_ID,
    }
    winner, _created = create_job(session, 1, "sync", "sync:race-diff", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    response = post_job(client, key="race-diff")
    stored = session.get(Job, winner.id)

    assert response.status_code == 409
    assert response.json()["error"]["message"] == sync_api.CONFLICT_MESSAGE
    assert stored is not None
    assert stored.payload == payload


def test_missing_and_foreign_item_are_not_found(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_user(2, "Other user")
    seed_item(session, item_id=OTHER_ITEM_ID, user_id=2)
    missing = post_job(client, key="missing-item")
    foreign = post_job(client, key="foreign-item", body=job_body(item_id=OTHER_ITEM_ID))

    assert missing.status_code == 404
    assert foreign.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "not_found",
            "message": sync_api.ITEM_NOT_FOUND_MESSAGE,
        }
    }
    assert foreign.json() == missing.json()
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_absent_config_rejects_new_jobs(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    monkeypatch.setattr(
        sync_api, "get_provider_settings", lambda: GroceryProviderSettings()
    )
    response = post_job(client)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": sync_api.CONFIG_UNAVAILABLE_MESSAGE,
        }
    }
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_same_body_replays_before_config_check(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {"operation": "plaid_sync", "item_id": ITEM_ID}
    job, _created = create_job(session, 1, "sync", "sync:cached", payload)
    session.flush()
    monkeypatch.setattr(
        sync_api, "get_provider_settings", lambda: GroceryProviderSettings()
    )
    response = post_job(client, key="cached")

    assert response.status_code == 202
    assert response.json() == {"job_id": job.id, "status": job.status}


def test_changed_body_conflicts_without_config(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {"operation": "plaid_sync", "item_id": ITEM_ID}
    create_job(session, 1, "sync", "sync:cached-diff", payload)
    session.flush()
    monkeypatch.setattr(
        sync_api, "get_provider_settings", lambda: GroceryProviderSettings()
    )
    response = post_job(client, key="cached-diff", body=job_body(item_id=OTHER_ITEM_ID))

    assert response.status_code == 409
    assert response.json()["error"]["message"] == sync_api.CONFLICT_MESSAGE


def test_extra_fields_and_secrets_are_rejected(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session)
    responses = [
        post_job(client, key=f"extra-{name}", body=job_body(**{name: "secret"}))
        for name in (*FORBIDDEN_FIELDS, "user_id", "operation")
    ]

    for response in responses:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_invalid_item_id_and_idempotency_key_are_rejected(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session)
    missing = client.post(JOBS_PATH, json=job_body())
    blank = post_job(client, headers={"Idempotency-Key": " "})
    too_long = post_job(client, headers={"Idempotency-Key": "x" * 121})
    max_key = post_job(client, headers={"Idempotency-Key": "k" * 120})
    blank_item = post_job(client, key="blank-item", body=job_body(item_id="   "))
    long_item = post_job(client, key="long-item", body=job_body(item_id="x" * 257))

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert too_long.status_code == 422
    assert max_key.status_code == 202
    stored = session.get(Job, max_key.json()["job_id"])
    assert stored is not None
    assert stored.request_key == "sync:" + ("k" * 120)
    assert blank_item.status_code == 422
    assert long_item.status_code == 422


def test_commit_runs_before_accepted_response(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    commit_without_ending_the_test_transaction: list[str],
) -> None:
    seed_user()
    seed_item(session)
    commit_without_ending_the_test_transaction.clear()
    response = post_job(client)
    job_id = response.json()["job_id"]

    assert response.status_code == 202
    assert commit_without_ending_the_test_transaction == ["commit"]
    assert session.get(Job, job_id) is not None
    assert session.scalar(select(func.count()).select_from(JobOutbox)) == 1


def test_get_job_returns_public_fields_only(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session)
    created = post_job(client)
    job_id = created.json()["job_id"]
    response = client.get(f"{JOBS_PATH}/{job_id}")
    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"id", "status", "result", "error_code"}
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["result"] is None
    assert body["error_code"] is None
    for field in (*INTERNAL_JOB_FIELDS, *FORBIDDEN_FIELDS):
        assert field not in body


def test_another_users_job_and_non_sync_jobs_are_not_found(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_user(2, "Other user")
    other, _created = create_job(session, 2, "sync", "sync:other", job_body())
    agent, _agent = create_job(session, 1, "agent", "sync:agent", job_body())
    wrong_op, _wrong = create_job(
        session, 1, "sync", "sync:chat", {"operation": "chat", "item_id": ITEM_ID}
    )
    session.flush()
    missing = client.get(f"{JOBS_PATH}/{uuid4()}")
    other_response = client.get(f"{JOBS_PATH}/{other.id}")
    agent_response = client.get(f"{JOBS_PATH}/{agent.id}")
    wrong_response = client.get(f"{JOBS_PATH}/{wrong_op.id}")
    invalid = client.get(f"{JOBS_PATH}/not-a-uuid")

    assert missing.status_code == 404
    assert other_response.status_code == 404
    assert agent_response.status_code == 404
    assert wrong_response.status_code == 404
    assert invalid.status_code == 422
    for response in (missing, other_response, agent_response, wrong_response):
        assert response.json()["error"]["message"] == sync_api.JOB_NOT_FOUND_MESSAGE
        assert "payload" not in response.json()
        for field in FORBIDDEN_FIELDS:
            assert field not in secret_blob(response.json())


def test_owner_is_server_selected_user(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session)
    response = post_job(client, body=job_body(item_id=ITEM_ID))
    job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert job is not None
    assert job.user_id == 1
    assert job.payload == {"operation": "plaid_sync", "item_id": ITEM_ID}


def test_integrity_error_without_winner_has_no_chain(
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_integrity)
    with pytest.raises(HTTPException) as raised:
        sync_api.create_sync_job(CreateSyncJobBody(item_id=ITEM_ID), session, "bare")
    assert_static_http_error(raised.value, 503, sync_api.JOB_UNAVAILABLE_MESSAGE)


def test_integrity_error_same_body_replays_winner(
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {"operation": "plaid_sync", "item_id": ITEM_ID}
    winner, _created = create_job(session, 1, "sync", "sync:replay", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_integrity)
    accepted = sync_api.create_sync_job(
        CreateSyncJobBody(item_id=ITEM_ID), session, "replay"
    )
    stored = session.get(Job, winner.id)

    assert accepted.job_id == winner.id
    assert accepted.status == winner.status
    assert stored is not None
    assert stored.payload == payload


def test_integrity_error_changed_body_has_no_chain(
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {
        "operation": "plaid_sync",
        "item_id": OTHER_ITEM_ID,
    }
    winner, _created = create_job(session, 1, "sync", "sync:changed", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_integrity)
    with pytest.raises(HTTPException) as raised:
        sync_api.create_sync_job(CreateSyncJobBody(item_id=ITEM_ID), session, "changed")
    stored = session.get(Job, winner.id)
    assert_static_http_error(raised.value, 409, sync_api.CONFLICT_MESSAGE)
    assert stored is not None
    assert stored.payload == payload


def test_create_job_value_error_has_no_chain(
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_value)
    with pytest.raises(HTTPException) as raised:
        sync_api.create_sync_job(CreateSyncJobBody(item_id=ITEM_ID), session, "invalid")
    assert_static_http_error(raised.value, 422, sync_api.INVALID_JOB_MESSAGE)


def test_http_same_body_integrity_error_replays_winner(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {"operation": "plaid_sync", "item_id": ITEM_ID}
    winner, _created = create_job(session, 1, "sync", "sync:http-replay", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_integrity)
    response = post_job(client, key="http-replay")
    stored = session.get(Job, winner.id)

    assert response.status_code == 202
    assert response.json() == {"job_id": winner.id, "status": winner.status}
    assert SENTINEL not in secret_blob(response.text)
    assert stored is not None
    assert stored.payload == payload


def test_integrity_error_without_winner_is_unavailable(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_integrity)
    response = post_job(client, key="http-integrity")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": sync_api.JOB_UNAVAILABLE_MESSAGE,
        }
    }
    assert SENTINEL not in secret_blob(response.text)
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_create_job_value_error_is_unprocessable(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_value)
    response = post_job(client, key="http-value")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "unprocessable_entity",
            "message": sync_api.INVALID_JOB_MESSAGE,
        }
    }
    assert SENTINEL not in secret_blob(response.text)
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_http_changed_body_integrity_error_conflicts(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)
    payload: dict[str, object] = {
        "operation": "plaid_sync",
        "item_id": OTHER_ITEM_ID,
    }
    winner, _created = create_job(session, 1, "sync", "sync:http-changed", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    monkeypatch.setattr(sync_api, "create_job", raise_secret_integrity)
    response = post_job(client, key="http-changed")
    stored = session.get(Job, winner.id)

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": sync_api.CONFLICT_MESSAGE,
        }
    }
    assert SENTINEL not in secret_blob(response.text)
    assert stored is not None
    assert stored.payload == payload


def test_item_inventory_is_empty_without_owned_rows(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    response = client.get(ITEMS_PATH)

    assert response.status_code == 200
    assert response.json() == []


def test_item_inventory_returns_owned_rows_sorted_by_id(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session, item_id="item-c")
    seed_item(session, item_id="item-a", last_synced_at=SYNCED_AT)
    seed_item(session, item_id="item-b")
    response = client.get(ITEMS_PATH)
    body = response.json()

    assert response.status_code == 200
    assert [row["id"] for row in body] == ["item-a", "item-b", "item-c"]
    assert body[0]["last_synced_at"] in (
        "2026-09-06T15:00:00Z",
        "2026-09-06T15:00:00+00:00",
    )
    assert body[1]["last_synced_at"] is None
    assert body[2]["last_synced_at"] is None


def test_item_inventory_hides_other_users_rows(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_user(2, "Other user")
    seed_item(session, item_id=ITEM_ID)
    seed_item(
        session,
        item_id=OTHER_ITEM_ID,
        user_id=2,
        credential_ref=SENTINEL,
        cursor=SENTINEL,
        provider_item_id=SENTINEL,
    )
    response = client.get(ITEMS_PATH)
    body = response.json()

    assert response.status_code == 200
    assert body == [{"id": ITEM_ID, "last_synced_at": None}]
    assert SENTINEL not in secret_blob(body)
    assert OTHER_ITEM_ID not in secret_blob(body)


def test_item_inventory_exposes_only_public_fields(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session, last_synced_at=SYNCED_AT)
    response = client.get(ITEMS_PATH)
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert set(body[0]) == ITEM_PUBLIC_FIELDS
    for field in (*FORBIDDEN_FIELDS, "provider_item_id", "credential_ref", "user_id"):
        assert field not in body[0]


def test_item_inventory_omits_secret_sentinels(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(
        session,
        credential_ref=SENTINEL,
        cursor=SENTINEL,
        provider_item_id=SENTINEL,
    )
    response = client.get(ITEMS_PATH)
    blob = secret_blob(response.json()) + secret_blob(response.text)

    assert response.status_code == 200
    assert SENTINEL.lower() not in blob
    for field in ("provider_item_id", "credential_ref", "cursor", "user_id"):
        assert field not in response.json()[0]


def test_item_inventory_allows_null_last_synced_at(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_item(session, last_synced_at=None)
    response = client.get(ITEMS_PATH)

    assert response.status_code == 200
    assert response.json() == [{"id": ITEM_ID, "last_synced_at": None}]


def test_item_inventory_ignores_unconfigured_provider(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_item(session)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider capabilities MUST NOT run")

    monkeypatch.setattr(
        sync_api, "get_provider_settings", lambda: GroceryProviderSettings()
    )
    monkeypatch.setattr(sync_api, "capabilities", boom)
    response = client.get(ITEMS_PATH)

    assert response.status_code == 200
    assert response.json() == [{"id": ITEM_ID, "last_synced_at": None}]
