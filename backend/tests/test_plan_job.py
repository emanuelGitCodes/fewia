import json
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agent.planning_tool import execute_plan
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.services import plan_job as plan_job_module

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
_REV = "ab" * 32


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


def expected_plan(body: dict[str, object]) -> dict[str, object]:
    parsed = plan_job_module.PlanJobInput.model_validate(body)
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        SpendingSnapshot(
            parsed.spending.period,
            parsed.spending.posted_cents,
            parsed.spending.pending_cents,
            parsed.spending.refreshed_at,
        ),
        now=NOW,
        plan_cap_cents=parsed.request.plan_cap_cents,
    )
    return execute_plan(
        parsed.request.model_dump(mode="json"),
        budget,
        parsed.spending.period,
        user_id=1,
        spending_source=parsed.spending_source,
    )


def test_plan_job_returns_json_plan_and_calls_heartbeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    heartbeats: list[str] = []
    body = payload()
    expected = expected_plan(body)

    result = plan_job_module.plan_job(body, lambda: heartbeats.append("beat"))

    assert heartbeats == ["beat", "beat"]
    assert result["spending_source"] == "fixture"
    assert json.loads(json.dumps(result)) == result
    assert result["request"] == expected["request"]
    assert result["plan"] == expected["plan"]
    assert result["budget"] == expected["budget"]
    assert result["meal_nutrition"] == expected["meal_nutrition"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert "evidence_revision_id" not in result
    plan = result["plan"]
    assert isinstance(plan, dict)
    assert plan["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert isinstance(plan["lines"], list)
    assert "supermarket_estimate" not in result


def test_plan_job_stores_no_supermarket_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    result = plan_job_module.plan_job(payload(), lambda: None)
    assert "supermarket_estimate" not in result


def test_plan_job_records_catalog_without_supermarket_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    body = payload()
    expected = expected_plan(body)
    captured: list[dict[str, object]] = []

    def record(
        planning: dict[str, object],
        parsed: plan_job_module.PlanJobInput,
        clock: datetime,
    ) -> str:
        captured.append(dict(planning))
        del parsed, clock
        assert "supermarket_estimate" not in planning
        return _REV

    result = plan_job_module.plan_job(
        body,
        lambda: None,
        record_evidence=record,
    )

    assert len(captured) == 1
    planning = captured[0]
    assert "supermarket_estimate" not in planning
    assert planning == expected
    assert "supermarket_estimate" not in result
    assert result["evidence_revision_id"] == _REV
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["plan"] == expected["plan"]


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
    expected = expected_plan(stale_payload)

    result = plan_job_module.plan_job(stale_payload, lambda: None)

    assert result["spending_source"] == "plaid_sandbox"
    budget = result["budget"]
    plan = result["plan"]
    assert isinstance(budget, dict)
    assert isinstance(plan, dict)
    assert budget["warnings"]
    assert budget["warnings"] == plan["warnings"][:1]
    assert plan["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert result["request"] == expected["request"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["budget"] == expected["budget"]


def test_plan_job_manual_source_uses_full_monthly_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    body = payload(
        monthly_limit_cents=10_000,
        spending={
            "period": date(2026, 9, 1),
            "posted_cents": 0,
            "pending_cents": 0,
            "refreshed_at": NOW - timedelta(hours=1),
        },
        spending_source="manual",
    )
    result = plan_job_module.plan_job(body, lambda: None)
    budget = result["budget"]

    assert result["spending_source"] == "manual"
    assert isinstance(budget, dict)
    assert budget["available_cents"] == 10_000


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


def test_plan_job_passes_frozen_clock_and_parsed_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_calls: list[datetime] = []

    def frozen() -> datetime:
        now_calls.append(NOW)
        return NOW

    monkeypatch.setattr(plan_job_module, "_utc_now", frozen)
    body = payload()
    expected = expected_plan(body)
    captured: list[
        tuple[dict[str, object], plan_job_module.PlanJobInput, datetime]
    ] = []

    def record(
        planning: dict[str, object],
        parsed: plan_job_module.PlanJobInput,
        clock: datetime,
    ) -> str:
        captured.append((dict(planning), parsed, clock))
        assert "evidence_revision_id" not in planning
        return _REV

    result = plan_job_module.plan_job(body, lambda: None, record_evidence=record)

    assert now_calls == [NOW]
    assert len(captured) == 1
    planning, parsed, clock = captured[0]
    assert clock is NOW
    assert parsed == plan_job_module.PlanJobInput.model_validate(body)
    assert planning == expected
    assert result["evidence_revision_id"] == _REV
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["request"] == expected["request"]


def test_plan_job_callback_failure_does_not_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)

    def record(
        planning: dict[str, object],
        parsed: plan_job_module.PlanJobInput,
        clock: datetime,
    ) -> str:
        del planning, parsed, clock
        raise RuntimeError("store-failed")

    with pytest.raises(RuntimeError, match="store-failed") as caught:
        plan_job_module.plan_job(payload(), lambda: None, record_evidence=record)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("value", ["NOT-HEX", "A" * 64, "g" * 64, "ab" * 31, "ab" * 33])
def test_plan_job_malformed_revision_id_fails_closed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)

    def record(
        planning: dict[str, object],
        parsed: plan_job_module.PlanJobInput,
        clock: datetime,
    ) -> str:
        del planning, parsed, clock
        return value

    with pytest.raises(ValueError, match="evidence revision id is invalid") as caught:
        plan_job_module.plan_job(payload(), lambda: None, record_evidence=record)
    assert value not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
