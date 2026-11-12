"""Tests for the chat job rate limit and the single load of the previous job."""

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
from app.api.chat import CHAT_RATE_LIMIT_MESSAGE, chat_jobs_per_minute
from app.job_models import Job
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

LIMIT_ENV = "FEWIA_CHAT_JOBS_PER_MINUTE"
UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-")


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


def prepare(monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder, limit: int) -> None:
    seed_user()
    enable_chat(monkeypatch)
    monkeypatch.setenv(LIMIT_ENV, str(limit))


def test_fourth_new_key_gets_429_at_a_limit_of_three(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder
) -> None:
    prepare(monkeypatch, seed_user, 3)
    for index in range(3):
        assert post_chat(client, key=f"key-{index}").status_code == 202
    response = post_chat(client, key="key-3")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json()["error"]["code"] == "too_many_requests"
    assert response.json()["error"]["message"] == CHAT_RATE_LIMIT_MESSAGE


def test_same_key_and_body_is_reused_after_the_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder
) -> None:
    prepare(monkeypatch, seed_user, 3)
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
    prepare(monkeypatch, seed_user, 1)
    assert post_chat(client, key="key-0").status_code == 202
    response = post_chat(client, key="key-0", body=chat_body(message="plan eggs"))

    assert response.status_code == 409


def test_a_plan_job_does_not_move_the_chat_count(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user, 1)
    create_job(session, 1, "agent", "plan-key", {"operation": "plan"})
    create_job(session, 1, "sync", "chat:sync-key", {"operation": "plan"})

    assert post_chat(client, key="key-0").status_code == 202
    assert post_chat(client, key="key-1").status_code == 429


def test_a_job_older_than_the_window_does_not_count(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    seed_user: UserSeeder,
) -> None:
    prepare(monkeypatch, seed_user, 2)
    for index in range(2):
        assert post_chat(client, key=f"key-{index}").status_code == 202
    assert post_chat(client, key="key-2").status_code == 429
    old = datetime.now(UTC) - timedelta(seconds=120)
    for job in session.scalars(select(Job)):
        job.created_at = old
    session.flush()

    assert post_chat(client, key="key-2").status_code == 202


def test_the_429_body_holds_no_job_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_user: UserSeeder
) -> None:
    prepare(monkeypatch, seed_user, 1)
    first = post_chat(client, key="key-0")
    response = post_chat(client, key="key-1")

    assert response.status_code == 429
    assert "job_id" not in response.text
    assert UUID_TEXT.search(response.text) is None
    assert first.json()["job_id"] not in response.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 20),
        ("", 20),
        ("0", 20),
        ("1", 1),
        ("1000", 1000),
        ("1001", 20),
        ("abc", 20),
        ("5.5", 20),
        (" 7 ", 7),
    ],
)
def test_chat_jobs_per_minute_reads_a_plain_integer(
    value: str | None, expected: int
) -> None:
    assert chat_jobs_per_minute(value) == expected


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
