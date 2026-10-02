"""Tests for the read-only grocery template suggestion route."""

import os
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from conftest import UserSeeder
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_plan_templates import TWO_SERVING_IDS, TWO_SERVING_RECIPES, TWO_SERVING_TOTALS

from app.api import grocery as grocery_api
from app.api import plan_templates as plan_templates_api
from app.domain.budget import (
    NEW_YORK,
    STALE_SPENDING_ERROR,
    STALE_SPENDING_WARNING,
)
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.job_models import Job, JobOutbox
from app.provider_settings import GroceryProviderSettings
from app.services.grocery_context import (
    FIXTURE_PENDING_CENTS,
    FIXTURE_POSTED_CENTS,
    SpendingUnavailable,
)
from app.services.plan_job import SpendingInput

FIXED_NY = datetime(2026, 9, 6, 12, 0, tzinfo=NEW_YORK)
OCTOBER_NY = datetime(2026, 10, 2, 12, 0, tzinfo=NEW_YORK)
RESPONSE_FIELDS = {
    "budget_period",
    "spending_source",
    "budget",
    "catalog_version",
    "notice",
    "suggestions",
}
SUGGESTION_FIELDS = {
    "template_id",
    "recipe_ids",
    "servings",
    "total_cents",
    "catalog_version",
    "notice",
}


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def freeze_new_york_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_templates_api, "_ny_now", lambda: FIXED_NY)


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


def template_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "budget_period": "2026-09-01",
        "monthly_limit_cents": 10000,
        "plan_cap_cents": 3000,
    }
    body.update(overrides)
    return body


def post_templates(
    client: TestClient, body: dict[str, object] | None = None
) -> Response:
    return client.post("/grocery/templates", json=body or template_body())


def use_settings(
    monkeypatch: pytest.MonkeyPatch, settings: GroceryProviderSettings
) -> None:
    monkeypatch.setattr("app.deps.load_provider_settings", lambda: settings)


def suggestion_ids(payload: dict[str, object]) -> tuple[str, ...]:
    items = payload["suggestions"]
    assert isinstance(items, list)
    return tuple(cast(dict[str, object], item)["template_id"] for item in items)


def test_manual_hundred_with_thirty_cap_returns_fitting_templates(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    response = post_templates(client)
    body = response.json()
    expected_ids = TWO_SERVING_IDS[:2] + TWO_SERVING_IDS[3:]

    assert response.status_code == 200
    assert set(body) == RESPONSE_FIELDS
    assert body["budget_period"] == "2026-09-01"
    assert body["spending_source"] == "manual"
    assert body["catalog_version"] == CATALOG_VERSION == "sample-prices-v2"
    assert body["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert body["budget"] == {
        "available_cents": 3000,
        "pending_cents": 0,
        "stale": False,
        "warnings": [],
    }
    assert suggestion_ids(body) == expected_ids
    for item, recipe_ids, total in zip(
        body["suggestions"],
        (TWO_SERVING_RECIPES[0], TWO_SERVING_RECIPES[1], *TWO_SERVING_RECIPES[3:]),
        (TWO_SERVING_TOTALS[0], TWO_SERVING_TOTALS[1], *TWO_SERVING_TOTALS[3:]),
        strict=True,
    ):
        assert set(item) == SUGGESTION_FIELDS
        assert item["recipe_ids"] == list(recipe_ids)
        assert item["servings"] == 2
        assert item["total_cents"] == total
        assert item["catalog_version"] == "sample-prices-v2"
        assert item["notice"] == SAMPLE_ESTIMATE_NOTICE
        assert item["total_cents"] <= 3000


def test_complete_fits_use_catalog_version_two(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    response = post_templates(client, template_body(plan_cap_cents=None))
    body = response.json()

    assert response.status_code == 200
    assert suggestion_ids(body) == TWO_SERVING_IDS
    assert [item["total_cents"] for item in body["suggestions"]] == list(
        TWO_SERVING_TOTALS
    )
    assert body["budget"]["available_cents"] == 10000
    assert body["catalog_version"] == "sample-prices-v2"
    assert all(
        item["catalog_version"] == "sample-prices-v2" for item in body["suggestions"]
    )


def test_server_selects_spending_source(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    rejected = post_templates(
        client, template_body(spending_source="fixture", source="fixture")
    )
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="fixture"))
    accepted = post_templates(client, template_body(plan_cap_cents=None))
    body = accepted.json()

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    assert body["spending_source"] == "fixture"
    assert body["budget"]["available_cents"] == 0
    assert body["budget"]["pending_cents"] == FIXTURE_PENDING_CENTS
    assert suggestion_ids(body) == ()


def test_fixture_spending_budget_and_zero_cap(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="fixture"))
    room = post_templates(
        client, template_body(monthly_limit_cents=40000, plan_cap_cents=None)
    )
    zero = post_templates(
        client, template_body(monthly_limit_cents=40000, plan_cap_cents=0)
    )
    lower = post_templates(
        client, template_body(monthly_limit_cents=40000, plan_cap_cents=2000)
    )

    assert room.status_code == 200
    assert room.json()["budget"]["available_cents"] == 22000
    assert room.json()["budget"]["pending_cents"] == FIXTURE_PENDING_CENTS
    assert suggestion_ids(room.json()) == TWO_SERVING_IDS
    assert zero.status_code == 200
    assert zero.json()["budget"]["available_cents"] == 0
    assert suggestion_ids(zero.json()) == ()
    assert lower.status_code == 200
    assert lower.json()["budget"]["available_cents"] == 2000
    assert suggestion_ids(lower.json()) == ("pasta_lentil_soup", "overnight_oats")
    assert FIXTURE_POSTED_CENTS == 18000


def test_stale_spending_without_cap_is_static_client_error(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()

    def stale(
        _session: Session, _user_id: int, _source: object, now: datetime
    ) -> SpendingInput:
        return SpendingInput(
            period=now.astimezone(NEW_YORK).date().replace(day=1),
            posted_cents=9000,
            pending_cents=400,
            refreshed_at=now.astimezone(UTC) - timedelta(hours=25),
        )

    monkeypatch.setattr(grocery_api, "spending_input", stale)
    response = post_templates(client, template_body(plan_cap_cents=None))
    body = response.json()

    assert response.status_code == 422
    assert body == {
        "error": {
            "code": "unprocessable_entity",
            "message": STALE_SPENDING_ERROR,
        }
    }
    assert "9000" not in str(body)
    assert "10000" not in str(body)
    assert "400" not in str(body)


def test_stale_spending_with_cap_keeps_warning(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()

    def stale(
        _session: Session, _user_id: int, _source: object, now: datetime
    ) -> SpendingInput:
        return SpendingInput(
            period=now.astimezone(NEW_YORK).date().replace(day=1),
            posted_cents=9000,
            pending_cents=400,
            refreshed_at=now.astimezone(UTC) - timedelta(hours=25),
        )

    monkeypatch.setattr(grocery_api, "spending_input", stale)
    response = post_templates(client)
    body = response.json()

    assert response.status_code == 200
    assert body["budget"] == {
        "available_cents": 3000,
        "pending_cents": 400,
        "stale": True,
        "warnings": [STALE_SPENDING_WARNING],
    }
    assert suggestion_ids(body) == TWO_SERVING_IDS[:2] + TWO_SERVING_IDS[3:]
    assert "9000" not in str(body)


def test_month_mismatch_uses_static_message(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    august = post_templates(client, template_body(budget_period="2026-08-01"))
    monkeypatch.setattr(plan_templates_api, "_ny_now", lambda: OCTOBER_NY)
    september = post_templates(client)

    assert august.status_code == 422
    assert september.status_code == 422
    assert august.json() == {
        "error": {
            "code": "unprocessable_entity",
            "message": grocery_api.PERIOD_MISMATCH_MESSAGE,
        }
    }
    assert september.json() == august.json()
    assert "2026-08-01" not in str(august.json()["error"]["message"])


def test_repeated_known_controls_match_unique_lists(
    client: TestClient, seed_user: UserSeeder
) -> None:
    seed_user()
    unique = post_templates(
        client,
        template_body(
            pantry_ingredients=["onion"],
            ingredient_exclusions=["rice"],
        ),
    )
    duplicate = post_templates(
        client,
        template_body(
            pantry_ingredients=["onion", "onion"],
            ingredient_exclusions=["rice", "rice"],
        ),
    )
    unique_body = unique.json()
    duplicate_body = duplicate.json()

    assert unique.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate_body["suggestions"] == unique_body["suggestions"]
    assert duplicate_body["budget"] == unique_body["budget"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pantry_ingredients", ["not_in_catalog"]),
        ("ingredient_exclusions", ["not_in_catalog"]),
        ("pantry_ingredients", ["onion"] * 23),
        ("servings", True),
        ("servings", 0),
        ("servings", 9),
        ("monthly_limit_cents", True),
        ("plan_cap_cents", True),
        ("diet", "keto"),
        ("user_id", 9),
        ("spending", {"posted_cents": 1}),
        ("source", "manual"),
    ],
)
def test_invalid_ids_servings_and_extra_fields_are_rejected(
    client: TestClient, seed_user: UserSeeder, field: str, value: object
) -> None:
    seed_user()
    response = post_templates(client, template_body(**{field: value}))
    body = response.json()

    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert "not_in_catalog" not in body["error"]["message"]
    assert "keto" not in body["error"]["message"]


def test_missing_demo_user_returns_static_service_error(client: TestClient) -> None:
    response = post_templates(client)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": grocery_api.DEMO_NOT_READY_MESSAGE,
        }
    }


def test_unavailable_spending_returns_static_service_error(
    client: TestClient, seed_user: UserSeeder, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()
    use_settings(monkeypatch, GroceryProviderSettings(spending_source="plaid_sandbox"))

    def missing(*_args: object, **_kwargs: object) -> SpendingInput:
        raise SpendingUnavailable()

    monkeypatch.setattr(grocery_api, "spending_input", missing)
    response = post_templates(client)
    body = response.json()

    assert response.status_code == 503
    assert body == {
        "error": {
            "code": "service_unavailable",
            "message": grocery_api.SPENDING_UNAVAILABLE_MESSAGE,
        }
    }
    assert "18000" not in str(body)


def test_route_creates_no_jobs_commits_or_provider_calls(
    client: TestClient,
    session: Session,
    seed_user: UserSeeder,
    monkeypatch: pytest.MonkeyPatch,
    commit_without_ending_the_test_transaction: list[str],
) -> None:
    seed_user()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("template route MUST NOT call jobs or providers")

    monkeypatch.setattr("app.services.job_submission.submit_job", boom)
    monkeypatch.setattr("app.agent.planning_tool.execute_plan", boom)
    monkeypatch.setattr("app.provider_runtime.build_spoonacular", boom)
    commit_without_ending_the_test_transaction.clear()
    response = post_templates(client, template_body(plan_cap_cents=None))

    assert response.status_code == 200
    assert suggestion_ids(response.json()) == TWO_SERVING_IDS
    assert commit_without_ending_the_test_transaction == []
    assert session.scalars(select(Job)).all() == []
    assert session.scalars(select(JobOutbox)).all() == []
    assert len(INGREDIENTS) == 22
