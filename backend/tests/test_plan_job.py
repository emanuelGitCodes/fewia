import json
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.services import plan_job as plan_job_module

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def payload(**overrides: object) -> dict[str, object]:
    spending: dict[str, object] = {
        "period": date(2026, 9, 1),
        "posted_cents": 2_500,
        "pending_cents": 400,
        "refreshed_at": NOW - timedelta(hours=1),
    }
    result: dict[str, object] = {
        "request": {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": date(2026, 9, 1),
        },
        "monthly_limit_cents": 10_000,
        "spending": spending,
        "spending_source": "fixture",
    }
    result.update(overrides)
    return result


def test_plan_job_returns_json_plan_and_calls_heartbeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    heartbeats: list[str] = []

    result = plan_job_module.plan_job(payload(), lambda: heartbeats.append("beat"))

    assert heartbeats == ["beat", "beat"]
    assert result["spending_source"] == "fixture"
    assert json.loads(json.dumps(result)) == result
    plan = result["plan"]
    assert isinstance(plan, dict)
    assert plan["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert isinstance(plan["lines"], list)


def test_plan_job_preserves_budget_warnings_and_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    stale_payload = payload(
        spending={
            "period": date(2026, 9, 1),
            "posted_cents": 2_500,
            "pending_cents": 400,
            "refreshed_at": NOW - timedelta(hours=25),
        },
        spending_source="plaid_sandbox",
        request={
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": date(2026, 9, 1),
            "plan_cap_cents": 100,
        },
    )

    result = plan_job_module.plan_job(stale_payload, lambda: None)

    assert result["spending_source"] == "plaid_sandbox"
    budget = result["budget"]
    plan = result["plan"]
    assert isinstance(budget, dict)
    assert isinstance(plan, dict)
    assert budget["warnings"]
    assert budget["warnings"] == plan["warnings"][:1]
    assert plan["notice"] == SAMPLE_ESTIMATE_NOTICE


def test_plan_job_rejects_period_mismatch() -> None:
    with pytest.raises(ValueError, match="budget_period.*spending.period"):
        plan_job_module.plan_job(
            payload(
                request={
                    "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
                    "budget_period": date(2026, 8, 1),
                }
            ),
            lambda: None,
        )


@pytest.mark.parametrize("value", [-1, True, 1.5, "100"])
def test_plan_job_requires_strict_nonnegative_monthly_limit(value: object) -> None:
    with pytest.raises(ValidationError):
        plan_job_module.plan_job(payload(monthly_limit_cents=value), lambda: None)


@pytest.mark.parametrize("field", ["posted_cents", "pending_cents"])
@pytest.mark.parametrize("value", [True, 1.5, "100"])
def test_plan_job_requires_strict_spending_cents(field: str, value: object) -> None:
    spending = {
        "period": date(2026, 9, 1),
        "posted_cents": 2_500,
        "pending_cents": 400,
        "refreshed_at": NOW - timedelta(hours=1),
    }
    spending[field] = value

    with pytest.raises(ValidationError):
        plan_job_module.plan_job(payload(spending=spending), lambda: None)


def test_plan_job_rejects_invalid_diet_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        plan_job_module.plan_job(
            payload(
                request={
                    "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
                    "budget_period": date(2026, 9, 1),
                    "diet": "pescatarian",
                }
            ),
            lambda: None,
        )
    with pytest.raises(ValidationError):
        plan_job_module.plan_job(payload(unexpected="value"), lambda: None)
