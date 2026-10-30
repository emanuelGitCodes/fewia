"""Tests for the fixture grocery HTTP routes."""

import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from conftest import UserSeeder
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.api.grocery_models import CreateGroceryJobBody, PlanJobView
from app.domain.budget import NEW_YORK, SpendingSnapshot, calculate_budget
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS
from app.job_models import Job, JobOutbox
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
)
from app.services import job_submission
from app.services.grocery_context import (
    FIXTURE_PENDING_CENTS,
    FIXTURE_POSTED_CENTS,
    SpendingUnavailable,
)
from app.services.job_submission import create_job
from app.services.plan_job import PlanJobInput

FIXED_NY = datetime(2026, 9, 6, 12, 0, tzinfo=NEW_YORK)
NEXT_NY_DAY = datetime(2026, 9, 7, 9, 0, tzinfo=NEW_YORK)
OCTOBER_NY = datetime(2026, 10, 2, 12, 0, tzinfo=NEW_YORK)
FALL_BACK_LATE = datetime(2026, 11, 1, 23, 30, tzinfo=NEW_YORK)
STALE_REFRESH = datetime(2026, 9, 5, 16, 0, tzinfo=UTC)
INTERNAL_JOB_FIELDS = (
    "payload",
    "lease_token",
    "lease_expires_at",
    "request_key",
    "user_id",
    "attempts",
    "kind",
)


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def freeze_new_york_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    def now() -> datetime:
        return FIXED_NY

    monkeypatch.setattr(grocery_api, "_ny_now", now)


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


def job_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "request": {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": "2026-09-01",
        },
        "monthly_limit_cents": 40000,
    }
    body.update(overrides)
    return body


def post_job(
    client: TestClient,
    *,
    key: str = "plan-1",
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    request_headers = {} if headers is None else dict(headers)
    if "Idempotency-Key" not in request_headers and "idempotency-key" not in {
        name.lower() for name in request_headers
    }:
        request_headers["Idempotency-Key"] = key
    return client.post(
        "/grocery/jobs", json=body or job_body(), headers=request_headers
    )


def set_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(grocery_api, "_ny_now", lambda: moment)


def parse_refreshed_at(payload: dict[str, object]) -> datetime:
    spending = payload["spending"]
    assert isinstance(spending, dict)
    raw_refreshed = spending["refreshed_at"]
    assert isinstance(raw_refreshed, str)
    return datetime.fromisoformat(raw_refreshed.replace("Z", "+00:00"))


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


def stored_plan_payload(
    *,
    monthly_limit_cents: int = 40000,
    refreshed_at: datetime | None = None,
) -> dict[str, object]:
    moment = STALE_REFRESH if refreshed_at is None else refreshed_at
    return cast(
        dict[str, object],
        PlanJobInput.model_validate(
            {
                "request": job_body()["request"],
                "monthly_limit_cents": monthly_limit_cents,
                "spending": {
                    "period": "2026-09-01",
                    "posted_cents": FIXTURE_POSTED_CENTS,
                    "pending_cents": FIXTURE_PENDING_CENTS,
                    "refreshed_at": moment,
                },
                "spending_source": "fixture",
            }
        ).model_dump(mode="json"),
    )


def test_config_returns_manual_values_and_catalog_names(
    client: TestClient,
) -> None:
    response = client.get("/grocery/config")
    body = response.json()
    text = str(body).lower()
    catalog = body["recipes"] + body["ingredients"]

    assert response.status_code == 200
    assert body["budget_period"] == "2026-09-01"
    assert body["source"] == "manual"
    assert body["posted_cents"] == 0
    assert body["pending_cents"] == 0
    assert body["catalog_version"] == CATALOG_VERSION
    refreshed = datetime.fromisoformat(
        str(body["spending_refreshed_at"]).replace("Z", "+00:00")
    )
    assert refreshed == FIXED_NY.astimezone(UTC)
    assert body["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert [item["id"] for item in body["recipes"]] == list(SUPPORTED_RECIPE_IDS)
    assert body["recipes"][0]["name"] == "chicken tacos"
    assert {item["id"] for item in body["ingredients"]} == set(INGREDIENTS)
    assert {item["name"] for item in body["ingredients"]} == {
        item.name for item in INGREDIENTS.values()
    }
    assert "plaid" not in text
    assert "bedrock" not in text
    assert "connected" not in text
    for item in catalog:
        assert set(item) == {"id", "name"}
        assert "price" not in item


def test_config_returns_fixture_posted_and_pending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="fixture"))
    response = client.get("/grocery/config")
    body = response.json()

    assert response.status_code == 200
    assert body["source"] == "fixture"
    assert body["posted_cents"] == FIXTURE_POSTED_CENTS
    assert body["pending_cents"] == FIXTURE_PENDING_CENTS
    assert body["posted_cents"] == 18000
    assert body["pending_cents"] == 1200


def test_repeated_identical_request_reuses_job_and_outbox(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    commit_without_ending_the_test_transaction: list[str],
) -> None:
    seed_user()
    first = post_job(client)
    second = post_job(client)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()
    assert first.json()["status"] == "queued"
    job_id = first.json()["job_id"]
    jobs = session.scalars(select(Job).where(Job.id == job_id)).all()
    outboxes = session.scalars(
        select(JobOutbox).where(JobOutbox.job_id == job_id)
    ).all()
    assert len(jobs) == 1
    assert len(outboxes) == 1
    assert outboxes[0].published_at is None
    assert commit_without_ending_the_test_transaction


def test_changed_monthly_limit_conflicts(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    first = post_job(client)
    second = post_job(client, body=job_body(monthly_limit_cents=1))

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["message"] == (
        "request_key already identifies different content"
    )


def test_same_key_reuses_job_on_next_new_york_day(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    first = post_job(client)
    job_id = first.json()["job_id"]
    original = session.get(Job, job_id)
    assert original is not None
    snapshot = json.loads(json.dumps(original.payload))
    set_clock(monkeypatch, NEXT_NY_DAY)
    second = post_job(client)
    stored = session.get(Job, job_id)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert stored is not None
    assert stored.payload == snapshot


def test_same_key_changed_body_conflicts_on_next_day(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    first = post_job(client)
    job_id = first.json()["job_id"]
    original = session.get(Job, job_id)
    assert original is not None
    snapshot = json.loads(json.dumps(original.payload))
    set_clock(monkeypatch, NEXT_NY_DAY)
    second = post_job(client, body=job_body(monthly_limit_cents=1))
    stored = session.get(Job, job_id)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["message"] == (
        "request_key already identifies different content"
    )
    assert stored is not None
    assert stored.payload == snapshot


def test_month_rollover_replays_original_job(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    first = post_job(client)
    job_id = first.json()["job_id"]
    original = session.get(Job, job_id)
    assert original is not None
    snapshot = json.loads(json.dumps(original.payload))
    set_clock(monkeypatch, OCTOBER_NY)
    second = post_job(client)
    stored = session.get(Job, job_id)
    request = stored.payload["request"] if stored is not None else None

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert stored is not None
    assert stored.payload == snapshot
    assert isinstance(request, dict)
    assert request["budget_period"] == "2026-09-01"


def test_new_job_rejects_wrong_period_after_rollover(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    set_clock(monkeypatch, OCTOBER_NY)
    response = post_job(client, key="new-october")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "unprocessable_entity",
            "message": grocery_api.PERIOD_MISMATCH_MESSAGE,
        }
    }


def test_new_job_uses_actual_time_late_on_fall_back_day(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    set_clock(monkeypatch, FALL_BACK_LATE)
    body = job_body()
    request = cast(dict[str, object], body["request"])
    request["budget_period"] = "2026-11-01"
    response = post_job(client, body=body, key="fall-back")
    job = session.get(Job, response.json()["job_id"])
    midnight = datetime(2026, 11, 1, 0, 0, tzinfo=NEW_YORK)

    assert response.status_code == 202
    assert job is not None
    parsed = parse_refreshed_at(job.payload)
    assert parsed == FALL_BACK_LATE.astimezone(UTC)
    assert FALL_BACK_LATE.astimezone(UTC) - parsed <= timedelta(hours=24)
    assert FALL_BACK_LATE.astimezone(UTC) - midnight.astimezone(UTC) > timedelta(
        hours=24
    )


def test_insert_race_same_fields_keeps_winner_snapshot(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    payload = stored_plan_payload()
    winner, _created = create_job(session, 1, "agent", "race-same", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    response = post_job(client, key="race-same")
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

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise IntegrityError("INSERT", {"token": "secret"}, RuntimeError("constraint"))

    monkeypatch.setattr(job_submission, "create_job", boom)
    response = post_job(client, key="no-winner")
    body = response.json()

    assert response.status_code == 503
    assert body == {
        "error": {
            "code": "service_unavailable",
            "message": grocery_api.JOB_UNAVAILABLE_MESSAGE,
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

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise ValueError("request_key secret token constraint")

    monkeypatch.setattr(job_submission, "create_job", boom)
    response = post_job(client, key="value-error")
    body = response.json()

    assert response.status_code == 422
    assert body == {
        "error": {
            "code": "unprocessable_entity",
            "message": grocery_api.INPUT_INVALID_MESSAGE,
        }
    }
    assert "constraint" not in str(body).lower()
    assert "token" not in str(body).lower()
    assert "secret" not in str(body).lower()
    assert session.scalars(select(Job)).all() == []


def test_integrity_error_route_exception_has_no_context(
    session: Session, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise IntegrityError("INSERT", {"token": "secret"}, RuntimeError("constraint"))

    monkeypatch.setattr(job_submission, "create_job", boom)
    body = CreateGroceryJobBody.model_validate(job_body())
    with pytest.raises(HTTPException) as caught:
        grocery_api.create_grocery_job(body, session, "no-winner-direct")
    error = caught.value
    rendered = str(error) + repr(error)

    assert error.status_code == 503
    assert error.detail == grocery_api.JOB_UNAVAILABLE_MESSAGE
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "constraint" not in rendered.lower()
    assert "token" not in rendered.lower()
    assert "secret" not in rendered.lower()


def test_value_error_route_exception_has_no_context(
    session: Session, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()

    def boom(*_args: object, **_kwargs: object) -> tuple[Job, bool]:
        raise ValueError("request_key secret token constraint")

    monkeypatch.setattr(job_submission, "create_job", boom)
    body = CreateGroceryJobBody.model_validate(job_body())
    with pytest.raises(HTTPException) as caught:
        grocery_api.create_grocery_job(body, session, "value-error-direct")
    error = caught.value
    rendered = str(error) + repr(error)

    assert error.status_code == 422
    assert error.detail == grocery_api.INPUT_INVALID_MESSAGE
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
    payload = stored_plan_payload(monthly_limit_cents=1)
    winner, _created = create_job(session, 1, "agent", "race-diff", payload)
    session.flush()
    miss_first_lookup(monkeypatch)
    response = post_job(client, key="race-diff")
    stored = session.get(Job, winner.id)

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "request_key already identifies different content"
    )
    assert stored is not None
    assert stored.payload == payload


def test_period_mismatch_uses_static_message(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    body = job_body()
    request = cast(dict[str, object], body["request"])
    request["budget_period"] = "2026-08-01"

    response = post_job(client, body=body)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "unprocessable_entity",
            "message": grocery_api.PERIOD_MISMATCH_MESSAGE,
        }
    }


def test_unknown_pantry_ingredient_returns_422_and_creates_no_job(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    body = job_body()
    request = cast(dict[str, object], body["request"])
    request["pantry_ingredients"] = ["white_rice"]
    response = post_job(client, body=body)

    assert response.status_code == 422
    assert session.scalars(select(Job)).all() == []


@pytest.mark.parametrize("value", [-1, True, 1.5, "100"])
def test_monthly_limit_rejects_invalid_types(
    client: TestClient, seed_user: UserSeeder, value: object
) -> None:
    seed_user()
    response = post_job(client, body=job_body(monthly_limit_cents=value))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_caller_cannot_inject_spending_or_user(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    spending = {
        "period": "2026-09-01",
        "posted_cents": 1,
        "pending_cents": 1,
        "refreshed_at": "2026-09-06T16:00:00Z",
    }
    extra_user = post_job(client, body=job_body(user_id=9), key="user-inject")
    extra_spending = post_job(
        client, body=job_body(spending=spending), key="spend-inject"
    )
    accepted = post_job(client, key="fixture-spend")
    job = session.get(Job, accepted.json()["job_id"])
    assert extra_user.status_code == 422
    assert extra_spending.status_code == 422
    assert accepted.status_code == 202
    assert job is not None
    payload = job.payload
    assert payload["spending_source"] == "manual"
    assert payload["spending"]["posted_cents"] == 0
    assert payload["spending"]["pending_cents"] == 0
    parsed = parse_refreshed_at(payload)
    assert parsed == FIXED_NY.astimezone(UTC)
    PlanJobInput.model_validate(payload)


def test_manual_job_uses_full_monthly_limit(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    response = post_job(
        client, body=job_body(monthly_limit_cents=10000), key="manual-limit"
    )
    job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert job is not None
    parsed = PlanJobInput.model_validate(job.payload)
    assert parsed.spending_source == "manual"
    assert parsed.spending.posted_cents == 0
    assert parsed.spending.pending_cents == 0
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        SpendingSnapshot(
            parsed.spending.period,
            parsed.spending.posted_cents,
            parsed.spending.pending_cents,
            parsed.spending.refreshed_at,
        ),
        now=FIXED_NY,
        plan_cap_cents=parsed.request.plan_cap_cents,
    )
    assert budget.available_cents == 10000


def test_invalid_idempotency_key_is_rejected(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    missing = client.post("/grocery/jobs", json=job_body())
    blank = post_job(client, headers={"Idempotency-Key": " "})
    too_long = post_job(client, headers={"Idempotency-Key": "x" * 129})

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert too_long.status_code == 422
    assert blank.json() == {
        "error": {
            "code": "unprocessable_entity",
            "message": grocery_api.INPUT_INVALID_MESSAGE,
        }
    }
    assert too_long.json() == blank.json()
    assert "request_key" not in str(blank.json())


def test_missing_demo_user_returns_static_service_error(client: TestClient) -> None:
    response = post_job(client)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Demo workspace is not ready.",
        }
    }
    assert client.get("/grocery/config").status_code == 200


def test_commit_runs_before_accepted_response(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    commit_without_ending_the_test_transaction: list[str],
) -> None:
    seed_user()
    commit_without_ending_the_test_transaction.clear()
    response = post_job(client)
    job_id = response.json()["job_id"]

    assert response.status_code == 202
    assert commit_without_ending_the_test_transaction == ["commit"]
    assert session.get(Job, job_id) is not None
    assert session.scalar(select(func.count()).select_from(JobOutbox)) == 1


def test_get_job_returns_public_fields_only(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    created = post_job(client)
    job_id = created.json()["job_id"]
    response = client.get(f"/grocery/jobs/{job_id}")
    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"id", "status", "result", "error_code", "error_detail"}
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["result"] is None
    assert body["error_code"] is None
    assert body["error_detail"] is None
    for field in INTERNAL_JOB_FIELDS:
        assert field not in body


def test_another_users_job_and_sync_job_are_not_found(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    seed_user(2, "Other user")
    other, _created = create_job(session, 2, "agent", "other-plan", {"marker": True})
    sync, _sync_created = create_job(session, 1, "sync", "sync-plan", {"marker": True})
    session.flush()
    missing = client.get(f"/grocery/jobs/{uuid4()}")
    other_response = client.get(f"/grocery/jobs/{other.id}")
    sync_response = client.get(f"/grocery/jobs/{sync.id}")
    invalid = client.get("/grocery/jobs/not-a-uuid")

    assert missing.status_code == 404
    assert other_response.status_code == 404
    assert sync_response.status_code == 404
    assert invalid.status_code == 422
    assert "payload" not in other_response.json()
    assert "lease_token" not in other_response.json()


def use_settings(
    monkeypatch: pytest.MonkeyPatch, settings: GroceryProviderSettings
) -> None:
    monkeypatch.setattr("app.deps.load_provider_settings", lambda: settings)


def test_sandbox_config_uses_ledger_snapshot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = SpendingSnapshot(
        period=date(2026, 9, 1),
        posted_cents=777,
        pending_cents=8,
        refreshed_at=STALE_REFRESH,
    )
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="plaid_sandbox"))
    monkeypatch.setattr(
        "app.services.grocery_context.load_spending",
        lambda *_args, **_kwargs: snapshot,
    )
    response = client.get("/grocery/config")
    body = response.json()

    assert response.status_code == 200
    assert body["source"] == "plaid_sandbox"
    assert body["posted_cents"] == 777
    assert body["pending_cents"] == 8
    assert body["catalog_version"] == CATALOG_VERSION
    refreshed = datetime.fromisoformat(
        str(body["spending_refreshed_at"]).replace("Z", "+00:00")
    )
    assert refreshed == STALE_REFRESH
    assert body["budget_period"] == "2026-09-01"


def test_sandbox_job_stores_ledger_spending(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    snapshot = SpendingSnapshot(
        period=date(2026, 9, 1),
        posted_cents=2500,
        pending_cents=50,
        refreshed_at=STALE_REFRESH,
    )
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="plaid_sandbox"))
    monkeypatch.setattr(
        "app.services.grocery_context.load_spending",
        lambda *_args, **_kwargs: snapshot,
    )
    response = post_job(client, key="sandbox-plan")
    job = session.get(Job, response.json()["job_id"])

    assert response.status_code == 202
    assert job is not None
    assert job.payload["spending_source"] == "plaid_sandbox"
    assert job.payload["spending"]["posted_cents"] == 2500
    assert job.payload["spending"]["pending_cents"] == 50
    assert parse_refreshed_at(job.payload) == STALE_REFRESH


def test_sandbox_missing_spending_is_static_and_does_not_fall_back(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="plaid_sandbox"))

    def missing(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise SpendingUnavailable()

    monkeypatch.setattr("app.services.grocery_context.load_spending", missing)
    config = client.get("/grocery/config")
    created = post_job(client, key="sandbox-missing")

    assert config.status_code == 503
    assert config.json() == {
        "error": {
            "code": "service_unavailable",
            "message": grocery_api.SPENDING_UNAVAILABLE_MESSAGE,
        }
    }
    assert created.status_code == 503
    assert created.json() == config.json()
    assert "18000" not in str(config.json())
    assert session.scalars(select(Job)).all() == []


def test_invalid_provider_settings_return_static_service_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid() -> GroceryProviderSettings:
        raise ProviderConfigurationError()

    monkeypatch.setattr("app.deps.load_provider_settings", invalid)
    response = client.get("/grocery/config")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Provider configuration is invalid",
        }
    }
    assert "token" not in str(response.json()).lower()


def test_existing_job_replays_without_new_sandbox_snapshot(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user()
    first = post_job(client)
    job_id = first.json()["job_id"]
    original = session.get(Job, job_id)
    assert original is not None
    snapshot = json.loads(json.dumps(original.payload))
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="plaid_sandbox"))

    def boom(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise AssertionError("replay MUST NOT take a new spending snapshot")

    monkeypatch.setattr("app.services.grocery_context.load_spending", boom)
    second = post_job(client)
    stored = session.get(Job, job_id)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert stored is not None
    assert stored.payload == snapshot
    assert stored.payload["spending_source"] == "manual"


def _seed_grocery_job(
    session: Session, *, key: str, status: str, result: dict[str, object] | None
) -> Job:
    job, _created = create_job(session, 1, "agent", key, stored_plan_payload())
    job.status = status
    job.result = result
    session.flush()
    return job


PLAN_RESULT: dict[str, object] = {
    "plan": {
        "lines": [
            {
                "ingredient_id": "chicken_breast",
                "unit": "g",
                "quantity": 100,
                "from_pantry": False,
            }
        ]
    }
}


@pytest.mark.parametrize("status", ["queued", "succeeded", "failed"])
def test_grocery_job_result_is_returned_as_stored(
    client: TestClient, session: Session, seed_user: UserSeeder, status: str
) -> None:
    seed_user()
    job = _seed_grocery_job(
        session, key=f"stored-{status}", status=status, result=dict(PLAN_RESULT)
    )
    response = client.get(f"/grocery/jobs/{job.id}")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == status
    assert body["result"] == (None if status == "failed" else PLAN_RESULT)
    assert body["error_detail"] is None


def test_failed_exclusion_job_exposes_detail_without_result(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    detail = {"recipe_id": "vegetable_pasta", "ingredient_id": "onion"}
    job = _seed_grocery_job(
        session,
        key="excluded-onion",
        status="failed",
        result={"error_detail": detail},
    )
    job.error_code = "exclusion_reject"
    session.flush()
    response = client.get(f"/grocery/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json() == {
        "id": job.id,
        "status": "failed",
        "result": None,
        "error_code": "exclusion_reject",
        "error_detail": detail,
    }


@pytest.mark.parametrize(
    "detail", [None, "onion", ["onion"], {"ingredient_id": 1}, {1: "onion"}]
)
def test_failed_job_ignores_invalid_error_detail(
    session: Session, seed_user: UserSeeder, detail: object
) -> None:
    seed_user()
    job = _seed_grocery_job(session, key="invalid-detail", status="failed", result=None)
    job.result = {"error_detail": detail}
    view = grocery_api.read_grocery_job(UUID(job.id), session)
    assert isinstance(view, PlanJobView)
    assert view.result is None
    assert view.error_detail is None


@pytest.mark.parametrize("status", ["queued", "running", "succeeded"])
def test_other_job_statuses_do_not_expose_error_detail(
    client: TestClient, session: Session, seed_user: UserSeeder, status: str
) -> None:
    seed_user()
    result: dict[str, object] = {"error_detail": {"ingredient_id": "onion"}}
    job = _seed_grocery_job(
        session, key=f"detail-{status}", status=status, result=result
    )
    response = client.get(f"/grocery/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json()["error_detail"] is None
    assert response.json()["result"] == result
