"""Tests for grocery chat HTTP routes and provider capabilities."""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from conftest import UserSeeder
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_deps import (
    PLAN_RESULT,
    FixedEstimator,
    ForbiddenEstimator,
    clear_estimator_override,
    override_estimator,
)

from app.api import chat as chat_api
from app.api.chat_models import CreateChatJobBody
from app.api.grocery import (
    CONFLICT_MESSAGE,
    DEMO_NOT_READY_MESSAGE,
    INPUT_INVALID_MESSAGE,
    JOB_UNAVAILABLE_MESSAGE,
)
from app.deps import get_supermarket_estimator
from app.domain.budget import NEW_YORK, SpendingSnapshot
from app.job_models import Job
from app.provider_settings import GroceryProviderSettings
from app.services.chat_job import ChatJobInput
from app.services.grocery_context import (
    FIXTURE_PENDING_CENTS,
    FIXTURE_POSTED_CENTS,
    SpendingUnavailable,
)
from app.services import job_submission
from app.services.job_submission import create_job

FIXED_NY = datetime(2026, 9, 6, 12, 0, tzinfo=NEW_YORK)
NEXT_NY_DAY = datetime(2026, 9, 7, 9, 0, tzinfo=NEW_YORK)
PARENT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INTERNAL_JOB_FIELDS = (
    "payload",
    "lease_token",
    "lease_expires_at",
    "request_key",
    "user_id",
    "attempts",
    "kind",
)
CHAT_BODY: dict[str, object] = {
    "message": "plan chicken tacos",
    "monthly_limit_cents": 40000,
}


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


def chat_body(**overrides: object) -> dict[str, object]:
    body = dict(CHAT_BODY)
    body.update(overrides)
    return body


def post_chat(
    client: TestClient,
    *,
    key: str = "chat-1",
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    request_headers = {} if headers is None else dict(headers)
    names = {name.lower() for name in request_headers}
    if "idempotency-key" not in names:
        request_headers["Idempotency-Key"] = key
    return client.post(
        "/grocery/chat/jobs", json=body or chat_body(), headers=request_headers
    )


def enable_chat(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source: Literal["fixture", "plaid_sandbox"] = "fixture",
    model: str | None = "anthropic.model",
) -> None:
    def loaded() -> GroceryProviderSettings:
        return GroceryProviderSettings(
            bedrock_model_id=model,
            spending_source=source,
        )

    monkeypatch.setattr("app.deps.load_provider_settings", loaded)


def forbid_provider_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("HTTP submission MUST NOT construct providers")

    monkeypatch.setattr("app.provider_runtime.build_bedrock", boom)
    monkeypatch.setattr("app.provider_runtime.build_plaid", boom)
    monkeypatch.setattr("app.provider_runtime.build_instacart", boom)
    monkeypatch.setattr("app.provider_runtime.read_secret_file", boom)
    monkeypatch.setattr("app.services.chat_job.chat_job", boom)
    monkeypatch.setattr("app.agent.chat_loop.run_chat", boom)


def stored_chat_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "operation": "chat",
        "message": "plan chicken tacos",
        "monthly_limit_cents": 40000,
        "plan_cap_cents": None,
        "previous_job_id": None,
        "history": [],
        "previous_request": None,
        "spending": {
            "period": "2026-09-01",
            "posted_cents": FIXTURE_POSTED_CENTS,
            "pending_cents": FIXTURE_PENDING_CENTS,
            "refreshed_at": FIXED_NY.astimezone(UTC),
        },
        "spending_source": "fixture",
    }
    values.update(overrides)
    return cast(
        dict[str, object],
        ChatJobInput.model_validate(values).model_dump(mode="json"),
    )


def miss_first_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    lookups = {"count": 0}
    real = job_submission.find_job

    def lookup(
        session: Session, user_id: int, kind: Literal["sync", "agent"], request_key: str
    ) -> Job | None:
        lookups["count"] += 1
        if lookups["count"] == 1:
            return None
        return real(session, user_id, kind, request_key)

    monkeypatch.setattr(job_submission, "find_job", lookup)


def add_parent(
    session: Session,
    *,
    user_id: int = 1,
    payload: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    status: str = "succeeded",
    kind: str = "agent",
) -> Job:
    job = Job(
        id=str(PARENT_ID),
        user_id=user_id,
        kind=kind,
        request_key=str(uuid4()),
        payload=payload
        or {
            "operation": "chat",
            "message": "plan chicken tacos",
            "monthly_limit_cents": 40000,
            "history": [],
        },
        result=result
        or {
            "answer": "Here is a labeled estimate.",
            "request": {
                "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
                "budget_period": "2026-09-01",
            },
        },
        status=status,
    )
    session.add(job)
    session.flush()
    return job


def test_providers_reports_capabilities_without_construction(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    forbid_provider_construction(monkeypatch)
    response = client.get("/grocery/providers")
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "chat_configured": False,
        "plaid_configured": False,
        "instacart_configured": False,
        "spending_source": "manual",
    }
    assert "token" not in str(body).lower()
    assert "secret" not in str(body).lower()


def test_providers_does_not_read_secret_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "plaid.secret"
    tokens = tmp_path / "plaid.tokens.json"
    key = tmp_path / "instacart.key"
    forbid_provider_construction(monkeypatch)
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            bedrock_model_id="anthropic.model",
            spending_source="plaid_sandbox",
            plaid_client_id=SecretStr("client-marker"),
            plaid_secret_file=secret,
            plaid_tokens_file=tokens,
            instacart_key_file=key,
        ),
    )
    response = client.get("/grocery/providers")
    body = response.json()

    assert response.status_code == 200
    assert body["chat_configured"] is True
    assert body["plaid_configured"] is True
    assert body["instacart_configured"] is True
    assert body["spending_source"] == "plaid_sandbox"
    assert "client-marker" not in str(body)


def test_post_chat_stores_fixture_context(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    forbid_provider_construction(monkeypatch)
    response = post_chat(client)
    job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert job is not None
    assert job.request_key == "chat:chat-1"
    assert job.user_id == 1
    assert job.kind == "agent"
    payload = job.payload
    assert payload["operation"] == "chat"
    assert payload["message"] == "plan chicken tacos"
    assert payload["monthly_limit_cents"] == 40000
    assert payload["plan_cap_cents"] is None
    assert payload["previous_job_id"] is None
    assert payload["history"] == []
    assert payload["previous_request"] is None
    assert payload["spending_source"] == "fixture"
    assert payload["spending"]["period"] == "2026-09-01"
    assert payload["spending"]["posted_cents"] == FIXTURE_POSTED_CENTS
    assert payload["spending"]["pending_cents"] == FIXTURE_PENDING_CENTS
    assert "user_id" not in payload
    ChatJobInput.model_validate(payload)


def test_post_chat_uses_sandbox_spending(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch, source="plaid_sandbox")
    snapshot = SpendingSnapshot(
        period=date(2026, 9, 1),
        posted_cents=900,
        pending_cents=10,
        refreshed_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "app.services.grocery_context.load_spending",
        lambda *_args, **_kwargs: snapshot,
    )
    response = post_chat(client, key="sandbox-chat")
    job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert job is not None
    assert job.payload["spending_source"] == "plaid_sandbox"
    assert job.payload["spending"]["posted_cents"] == 900
    assert job.payload["spending"]["pending_cents"] == 10


def test_sandbox_missing_spending_does_not_fall_back(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch, source="plaid_sandbox")

    def missing(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise SpendingUnavailable()

    monkeypatch.setattr("app.services.grocery_context.load_spending", missing)
    response = post_chat(client, key="sandbox-miss")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Spending is unavailable"
    assert session.scalars(select(Job)).all() == []


def test_disabled_chat_replays_existing_job(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    payload = stored_chat_payload()
    winner, _created = create_job(session, 1, "agent", "chat:replay", payload)
    session.flush()
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(),
    )
    forbid_provider_construction(monkeypatch)
    response = post_chat(client, key="replay")
    stored = session.get(Job, winner.id)

    assert response.status_code == 202
    assert response.json()["job_id"] == winner.id
    assert stored is not None
    assert stored.payload == payload


def test_disabled_chat_rejects_new_job(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(),
    )
    response = post_chat(client, key="new-disabled")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": chat_api.CHAT_UNAVAILABLE_MESSAGE,
        }
    }


def test_duplicate_key_reuses_job_on_next_day(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    first = post_chat(client)
    job_id = first.json()["job_id"]
    original = session.get(Job, job_id)
    assert original is not None
    snapshot = json.loads(json.dumps(original.payload))

    def later() -> datetime:
        return NEXT_NY_DAY

    monkeypatch.setattr(chat_api, "_ny_now", later)
    second = post_chat(client)
    stored = session.get(Job, job_id)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert stored is not None
    assert stored.payload == snapshot


def test_changed_body_conflicts(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    first = post_chat(client)
    second = post_chat(client, body=chat_body(monthly_limit_cents=1))

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["message"] == CONFLICT_MESSAGE


def test_insert_race_same_fields_keeps_winner(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    payload = stored_chat_payload()
    winner, _created = create_job(session, 1, "agent", "chat:race-same", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    response = post_chat(client, key="race-same")
    stored = session.get(Job, winner.id)

    assert response.status_code == 202
    assert response.json()["job_id"] == winner.id
    assert stored is not None
    assert stored.payload == payload


def test_insert_integrity_error_without_winner_is_static_unavailable(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise IntegrityError("INSERT", {"token": "secret"}, RuntimeError("constraint"))

    monkeypatch.setattr(job_submission, "create_job", boom)
    response = post_chat(client, key="no-winner")
    body = response.json()

    assert response.status_code == 503
    assert body == {
        "error": {
            "code": "service_unavailable",
            "message": JOB_UNAVAILABLE_MESSAGE,
        }
    }
    assert "constraint" not in str(body).lower()
    assert "token" not in str(body).lower()
    assert "secret" not in str(body).lower()
    assert session.scalars(select(Job)).all() == []


def test_create_job_value_error_is_static_unprocessable(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise ValueError("request_key secret token constraint")

    monkeypatch.setattr(job_submission, "create_job", boom)
    response = post_chat(client, key="value-error")
    body = response.json()

    assert response.status_code == 422
    assert body == {
        "error": {
            "code": "unprocessable_entity",
            "message": INPUT_INVALID_MESSAGE,
        }
    }
    assert "request_key" not in str(body)
    assert "constraint" not in str(body).lower()
    assert "token" not in str(body).lower()
    assert "secret" not in str(body).lower()
    assert session.scalars(select(Job)).all() == []


def test_integrity_error_route_exception_has_no_context(
    session: Session, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise IntegrityError("INSERT", {"token": "secret"}, RuntimeError("constraint"))

    monkeypatch.setattr(job_submission, "create_job", boom)
    body = CreateChatJobBody.model_validate(chat_body())
    with pytest.raises(HTTPException) as caught:
        chat_api.create_chat_job(body, session, "no-winner-direct")
    error = caught.value
    rendered = str(error) + repr(error)

    assert error.status_code == 503
    assert error.detail == JOB_UNAVAILABLE_MESSAGE
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "constraint" not in rendered.lower()
    assert "token" not in rendered.lower()
    assert "secret" not in rendered.lower()


def test_value_error_route_exception_has_no_context(
    session: Session, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise ValueError("request_key secret token constraint")

    monkeypatch.setattr(job_submission, "create_job", boom)
    body = CreateChatJobBody.model_validate(chat_body())
    with pytest.raises(HTTPException) as caught:
        chat_api.create_chat_job(body, session, "value-error-direct")
    error = caught.value
    rendered = str(error) + repr(error)

    assert error.status_code == 422
    assert error.detail == INPUT_INVALID_MESSAGE
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "constraint" not in rendered.lower()
    assert "token" not in rendered.lower()
    assert "secret" not in rendered.lower()


def test_insert_race_different_fields_keeps_conflict(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    payload = stored_chat_payload(monthly_limit_cents=1)
    winner, _created = create_job(session, 1, "agent", "chat:race-diff", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    response = post_chat(client, key="race-diff")
    stored = session.get(Job, winner.id)

    assert response.status_code == 409
    assert stored is not None
    assert stored.payload == payload


def test_parent_history_is_server_loaded(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    add_parent(session)
    response = post_chat(
        client,
        key="follow-up",
        body=chat_body(previous_job_id=str(PARENT_ID)),
    )
    job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert job is not None
    assert job.payload["previous_job_id"] == str(PARENT_ID)
    assert job.payload["history"] == [
        {"role": "user", "text": "plan chicken tacos"},
        {"role": "assistant", "text": "Here is a labeled estimate."},
    ]
    assert job.payload["previous_request"]["meals"][0]["recipe_id"] == ("chicken_tacos")


def test_foreign_parent_returns_static_conflict(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    seed_user(2, "Other user")
    enable_chat(monkeypatch)
    add_parent(session, user_id=2)
    response = post_chat(
        client,
        key="foreign-parent",
        body=chat_body(previous_job_id=str(PARENT_ID)),
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": chat_api.CHAT_CONTEXT_MESSAGE,
        }
    }
    stored = session.scalars(
        select(Job).where(Job.request_key == "chat:foreign-parent")
    ).all()
    assert stored == []


def test_invalid_parent_returns_static_conflict(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    response = post_chat(
        client,
        key="bad-parent",
        body=chat_body(previous_job_id=str(uuid4())),
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": chat_api.CHAT_CONTEXT_MESSAGE,
        }
    }


def test_forbidden_body_fields_are_rejected(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    history = post_chat(
        client, key="hist", body=chat_body(history=[{"role": "user", "text": "x"}])
    )
    owner = post_chat(client, key="owner", body=chat_body(user_id=9))
    spending = post_chat(
        client,
        key="spend",
        body=chat_body(spending={"posted_cents": 1}),
    )

    assert history.status_code == 422
    assert owner.status_code == 422
    assert spending.status_code == 422


def test_missing_demo_user_returns_static_service_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_chat(monkeypatch)
    response = post_chat(client)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": DEMO_NOT_READY_MESSAGE,
        }
    }


def test_get_chat_job_returns_public_fields_only(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    created = post_chat(client)
    job_id = created.json()["job_id"]
    response = client.get(f"/grocery/chat/jobs/{job_id}")
    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"id", "status", "result", "error_code"}
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["result"] is None
    for field in INTERNAL_JOB_FIELDS:
        assert field not in body


def test_get_chat_job_hides_foreign_plan_and_sync(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_user(2, "Other user")
    other, _created = create_job(
        session, 2, "agent", "chat:other", stored_chat_payload()
    )
    plan, _plan_created = create_job(
        session, 1, "agent", "plan-not-chat", {"request": {"meals": []}}
    )
    sync, _sync_created = create_job(
        session, 1, "sync", "chat:sync", stored_chat_payload()
    )
    session.flush()
    missing = client.get(f"/grocery/chat/jobs/{uuid4()}")
    other_response = client.get(f"/grocery/chat/jobs/{other.id}")
    plan_response = client.get(f"/grocery/chat/jobs/{plan.id}")
    sync_response = client.get(f"/grocery/chat/jobs/{sync.id}")

    assert missing.status_code == 404
    assert other_response.status_code == 404
    assert plan_response.status_code == 404
    assert sync_response.status_code == 404
    assert "payload" not in other_response.json()
    assert "lease_token" not in plan_response.json()


def test_idempotency_key_length_and_missing_are_rejected(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    missing = client.post("/grocery/chat/jobs", json=chat_body())
    too_long = post_chat(client, headers={"Idempotency-Key": "x" * 121})
    allowed = post_chat(client, key="k" * 120)

    assert missing.status_code == 422
    assert too_long.status_code == 422
    assert allowed.status_code == 202


def test_chat_and_plan_keys_do_not_collide(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    enable_chat(monkeypatch)
    plan, _created = create_job(
        session, 1, "agent", "shared", {"marker": True, "monthly_limit_cents": 1}
    )
    session.flush()
    response = post_chat(client, key="shared")
    chat_job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert chat_job is not None
    assert chat_job.id != plan.id
    assert chat_job.request_key == "chat:shared"


def _seed_chat_job(
    session: Session, *, key: str, status: str, result: dict[str, object] | None
) -> Job:
    job, _created = create_job(session, 1, "agent", key, stored_chat_payload())
    job.status = status
    job.result = result
    session.flush()
    return job


def test_succeeded_chat_job_attaches_overlay_without_storing(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    job = _seed_chat_job(
        session, key="chat:overlay-ok", status="succeeded", result=dict(PLAN_RESULT)
    )
    override_estimator(FixedEstimator())
    try:
        response = client.get(f"/grocery/chat/jobs/{job.id}")
    finally:
        clear_estimator_override()
    body = response.json()
    stored = session.get(Job, job.id)

    assert response.status_code == 200
    estimate = body["result"]["supermarket_estimate"]
    assert isinstance(estimate, dict)
    assert isinstance(estimate["lines"], list)
    assert estimate["lines"]
    assert stored is not None
    assert isinstance(stored.result, dict)
    assert "supermarket_estimate" not in stored.result


def test_succeeded_chat_job_keeps_stored_result_without_estimator(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    get_supermarket_estimator.cache_clear()
    stored_result = dict(PLAN_RESULT)
    job = _seed_chat_job(
        session, key="chat:overlay-none", status="succeeded", result=stored_result
    )
    response = client.get(f"/grocery/chat/jobs/{job.id}")
    body = response.json()

    assert response.status_code == 200
    assert body["result"] == stored_result
    assert "supermarket_estimate" not in body["result"]


@pytest.mark.parametrize("status", ["queued", "failed"])
def test_unfinished_chat_job_does_not_call_estimator(
    client: TestClient, session: Session, seed_user: UserSeeder, status: str
) -> None:
    seed_user()
    job = _seed_chat_job(
        session, key=f"chat:overlay-{status}", status=status, result=dict(PLAN_RESULT)
    )
    override_estimator(ForbiddenEstimator())
    try:
        response = client.get(f"/grocery/chat/jobs/{job.id}")
    finally:
        clear_estimator_override()
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == status
    assert body["result"] == PLAN_RESULT
    assert "supermarket_estimate" not in body["result"]
