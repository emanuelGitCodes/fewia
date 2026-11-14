"""Tests for service admission through authenticated chat requests."""

import os
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from conftest import UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import chat as chat_api
from app.auth import AuthSettings
from app.job_models import Job, JobOutbox
from app.services import chat_history
from app.services.job_submission import create_job
from tests.test_chat_api import (
    FIXED_NY,
    PARENT_ID,
    add_parent,
    chat_body,
    enable_chat,
    post_chat,
)
from tests.test_chat_api import mutation_admission as mutation_admission

UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-")


@pytest.fixture(autouse=True)
def local_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AuthSettings(
        auth_mode="local_demo", database_mode="local", transport_mode="local"
    )
    monkeypatch.setattr("app.deps.load_auth_settings", lambda: settings)


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def freeze_new_york_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    def now() -> datetime:
        return FIXED_NY

    monkeypatch.setattr(chat_api, "_ny_now", now)


@pytest.fixture(autouse=True)
def commit_without_ending_the_test_transaction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "commit", session.flush)


def prepare(monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder) -> None:
    seed_user()
    enable_chat(monkeypatch)


def test_fourth_active_job_gets_429_without_storing_a_job_or_outbox(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user)
    for index in range(3):
        assert post_chat(client, key=f"key-{index}").status_code == 202
    jobs = list(session.scalars(select(Job.id)))
    outboxes = list(session.scalars(select(JobOutbox.id)))
    response = post_chat(client, key="key-3")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json()["error"]["code"] == "too_many_requests"
    assert response.json()["error"]["message"] == (
        "Action limit reached. Try again later."
    )
    assert list(session.scalars(select(Job.id))) == jobs
    assert list(session.scalars(select(JobOutbox.id))) == outboxes


def test_same_key_and_body_is_reused_after_the_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder
) -> None:
    prepare(monkeypatch, seed_user)
    first = post_chat(client, key="key-0")
    for index in range(1, 3):
        assert post_chat(client, key=f"key-{index}").status_code == 202
    assert post_chat(client, key="key-3").status_code == 429
    repeat = post_chat(client, key="key-0")

    assert repeat.status_code == 202
    assert repeat.json()["job_id"] == first.json()["job_id"]


def test_same_key_with_another_body_stays_409_after_the_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder
) -> None:
    prepare(monkeypatch, seed_user)
    for index in range(3):
        assert post_chat(client, key=f"key-{index}").status_code == 202
    assert post_chat(client, key="key-3").status_code == 429
    response = post_chat(client, key="key-0", body=chat_body(message="plan eggs"))

    assert response.status_code == 409


def test_plan_and_sync_jobs_share_the_active_chat_limit(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user)
    create_job(session, 1, "agent", "plan-key", {"operation": "plan"})
    create_job(session, 1, "sync", "chat:sync-key", {"operation": "plaid_sync"})

    assert post_chat(client, key="key-0").status_code == 202
    assert post_chat(client, key="key-1").status_code == 429


def test_completed_plan_jobs_share_the_agent_minute_limit(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user)
    for index in range(20):
        job, _created = create_job(
            session, 1, "agent", f"plan-{index}", {"operation": "plan"}
        )
        job.status = "succeeded"
    session.flush()

    assert post_chat(client, key="limited-by-plans").status_code == 429


def test_completed_chats_reach_the_minute_limit_until_the_window_expires(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user)
    for index in range(20):
        response = post_chat(client, key=f"key-{index}")
        assert response.status_code == 202
        job = session.get(Job, response.json()["job_id"])
        assert job is not None
        job.status = "succeeded"
        session.flush()
    assert post_chat(client, key="key-20").status_code == 429
    assert post_chat(client, key="key-0").status_code == 202
    old = datetime.now(UTC) - timedelta(seconds=120)
    for job in session.scalars(select(Job)):
        job.created_at = old
    session.flush()

    assert post_chat(client, key="key-20").status_code == 202


def test_other_owners_jobs_share_the_global_active_limit(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user)
    seed_user(2, "Other owner")
    for index in range(200):
        create_job(session, 2, "sync", f"sync:{index}", {"operation": "plaid_sync"})

    response = post_chat(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_the_429_body_holds_no_job_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder
) -> None:
    prepare(monkeypatch, seed_user)
    first = post_chat(client, key="key-0")
    for index in range(1, 3):
        assert post_chat(client, key=f"key-{index}").status_code == 202
    response = post_chat(client, key="key-3")

    assert response.status_code == 429
    assert "job_id" not in response.text
    assert UUID_TEXT.search(response.text) is None
    assert first.json()["job_id"] not in response.text


def test_one_previous_job_load_per_chat_job(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    add_parent(session)
    real = chat_history._previous_job
    calls: list[str | UUID | None] = []

    def counted(
        counted_session: Session, user_id: int, previous_job_id: str | UUID | None
    ) -> Job | None:
        calls.append(previous_job_id)
        return real(counted_session, user_id, previous_job_id)

    monkeypatch.setattr(chat_history, "_previous_job", counted)
    response = post_chat(client, body=chat_body(previous_job_id=str(PARENT_ID)))

    assert response.status_code == 202
    assert len(calls) == 1
