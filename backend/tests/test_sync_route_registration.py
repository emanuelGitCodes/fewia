"""Tests for Plaid sync routes on the main FastAPI app."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import UserSeeder
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import sync as sync_api
from app.deps import get_session
from app.job_models import Job, JobOutbox
from app.main import app
from app.plaid_models import PlaidItem
from app.provider_settings import GroceryProviderSettings
from app.services.job_submission import create_job

ITEM_ID = "item-1"
OTHER_ITEM_ID = "item-2"
JOBS_PATH = "/grocery/sync/jobs"
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
    def get_test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def commit() -> None:
        session.flush()

    monkeypatch.setattr(session, "commit", commit)


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
    monkeypatch.setattr("app.provider_runtime.read_secret_file", boom)
    monkeypatch.setattr("app.provider_settings.read_secret_file", boom)
    monkeypatch.setattr("app.provider_runtime.PlaidSandboxProvider", boom)


@pytest.fixture()
def owned_item(session: Session, seed_user: UserSeeder) -> PlaidItem:
    seed_user()
    item = PlaidItem(
        id=ITEM_ID,
        user_id=1,
        provider_item_id=f"provider-{ITEM_ID}",
        credential_ref="plaid-item-ref",
    )
    session.add(item)
    session.flush()
    return item


def post_job(
    client: TestClient,
    *,
    key: str = "sync-1",
    body: dict[str, object] | None = None,
) -> Response:
    payload: dict[str, object] = {"item_id": ITEM_ID}
    if body is not None:
        payload = body
    return client.post(JOBS_PATH, json=payload, headers={"Idempotency-Key": key})


def test_post_creates_one_job_and_same_body_replay_returns_same_job(
    client: TestClient, session: Session, owned_item: PlaidItem
) -> None:
    assert owned_item.user_id == 1
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
    assert stored.user_id == 1
    assert stored.kind == "sync"
    assert stored.payload == {"operation": "plaid_sync", "item_id": ITEM_ID}


def test_missing_and_foreign_item_return_static_404(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_user(2, "Other user")
    session.add(
        PlaidItem(
            id=OTHER_ITEM_ID,
            user_id=2,
            provider_item_id=f"provider-{OTHER_ITEM_ID}",
            credential_ref="plaid-item-ref",
        )
    )
    session.flush()
    missing = post_job(client, key="missing-item")
    foreign = post_job(client, key="foreign-item", body={"item_id": OTHER_ITEM_ID})
    expected = {
        "error": {
            "code": "not_found",
            "message": sync_api.ITEM_NOT_FOUND_MESSAGE,
        }
    }

    assert missing.status_code == 404
    assert foreign.status_code == 404
    assert missing.json() == expected
    assert foreign.json() == expected
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_disabled_configuration_returns_static_503(
    client: TestClient,
    session: Session,
    owned_item: PlaidItem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert owned_item.user_id == 1
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


def test_get_returns_public_fields_and_ownership_in_main_envelope(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    owned_item: PlaidItem,
) -> None:
    assert owned_item.user_id == 1
    created = post_job(client, key="sync-get")
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    seed_user(2, "Other user")
    other, _created = create_job(
        session,
        2,
        "sync",
        "sync:other",
        {"operation": "plaid_sync", "item_id": ITEM_ID},
    )
    session.flush()
    shown = client.get(f"{JOBS_PATH}/{job_id}")
    foreign = client.get(f"{JOBS_PATH}/{other.id}")
    stored = session.get(Job, job_id)
    body = shown.json()

    assert shown.status_code == 200
    assert set(body) == {"id", "status", "result", "error_code"}
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["result"] is None
    assert body["error_code"] is None
    assert stored is not None
    assert stored.user_id == 1
    assert foreign.status_code == 404
    assert foreign.json() == {
        "error": {
            "code": "not_found",
            "message": sync_api.JOB_NOT_FOUND_MESSAGE,
        }
    }
    for field in (*INTERNAL_JOB_FIELDS, *FORBIDDEN_FIELDS):
        assert field not in body
        assert field not in foreign.json()
