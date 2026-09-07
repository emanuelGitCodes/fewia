from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from app.domain.budget import BudgetResult, SpendingSnapshot, StaleSpendingError
from app.evaluation_budget import evaluate_budget_case, fixture_budget

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
BUDGET_IDS = ("B01", "B02", "B03", "B04", "B05")
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
INPUT_KEYS = (
    "now",
    "budget_period",
    "spending_period",
    "monthly_limit_cents",
    "posted_cents",
    "pending_cents",
    "plan_cap_cents",
    "spending_refreshed_at",
)
UNASSESSED_MARKERS = (
    "tool_selection",
    "tool_arguments",
    "unnecessary_calls",
    "claim_support",
    "ingredient_coverage",
    "constraint_violations",
    "completion",
    "recovery",
    "cost",
    "latency",
    "p50_latency",
    "p95_latency",
    "token_use",
    "estimated_cost",
    "provider_calls",
    "model_quality",
    "live_providers",
    "local_postgresql",
    "plaid_sandbox",
    "live_instacart_development",
    "real_bedrock",
    "deployed_aws",
    "local_react_typescript_chat",
    "fastapi",
    "worker",
    "floci_sqs",
    "floci_s3",
    "plan_acceptance",
    "plan_rows",
    "hidden_reasoning",
)


def _budget_cases() -> dict[str, dict[str, object]]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    found: dict[str, dict[str, object]] = {}
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        case_id = row.get("id")
        if case_id in BUDGET_IDS:
            found[str(case_id)] = row
    return found


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _variants(case: dict[str, object]) -> list[dict[str, object]]:
    rows = case["variants"]
    assert isinstance(rows, list)
    return [_mapping(item, "variant") for item in rows]


def _inputs(
    case: dict[str, object], variant: dict[str, object] | None = None
) -> dict[str, object]:
    merged = dict(_mapping(case["inputs"], "inputs"))
    if variant is None:
        return merged
    for key in INPUT_KEYS:
        if key in variant:
            merged[key] = variant[key]
    return merged


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def _wrong_budget(
    monthly_limit_cents: int,
    spending: SpendingSnapshot,
    *,
    now: datetime,
    plan_cap_cents: int | None = None,
) -> BudgetResult:
    del monthly_limit_cents, spending, now, plan_cap_cents
    return BudgetResult(1, 2, True, ())


def _secret_error(
    monthly_limit_cents: int,
    spending: SpendingSnapshot,
    *,
    now: datetime,
    plan_cap_cents: int | None = None,
) -> BudgetResult:
    del monthly_limit_cents, spending, now, plan_cap_cents
    raise RuntimeError(f"{SECRET_MARKER} access_token")


def test_corpus_loads_five_budget_cases() -> None:
    cases = _budget_cases()
    assert set(cases) == set(BUDGET_IDS)
    assert len(cases) == 5


def test_evaluate_b01_b02_compare_observed_to_gold() -> None:
    for case_id in ("B01", "B02"):
        report = evaluate_budget_case(_budget_cases()[case_id])
        assert report["case_id"] == case_id
        assert report["evidence_class"] == "deterministic_fake_provider"
        checks = _mapping(report["checks"], "checks")
        assert set(checks) == {
            "available_cents",
            "pending_cents",
            "stale",
            "outcome",
        }
        assert all(value is True for value in checks.values())
        observed = _mapping(report["observed"], "observed")
        gold = _mapping(_budget_cases()[case_id]["expected"], "expected")
        assert observed["available_cents"] == gold["available_cents"]
        assert observed["pending_cents"] == gold["pending_cents"]
        assert observed["stale"] is False
        assert observed["outcome"] == "accept_budget"


def test_b03_scores_zero_floor_and_leaves_plan_rows() -> None:
    report = evaluate_budget_case(_budget_cases()["B03"])
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    assert checks == {
        "available_cents": True,
        "pending_cents": True,
        "stale": True,
    }
    assert observed["available_cents"] == 0
    assert "outcome" not in checks
    assert "accepted" not in checks
    assert "total_cents" not in observed
    assert unassessed == list(UNASSESSED_MARKERS)
    for marker in UNASSESSED_MARKERS:
        assert marker in unassessed


def test_b04_variants_stay_on_one_case() -> None:
    case = _budget_cases()["B04"]
    report = evaluate_budget_case(case)
    assert report["case_id"] == "B04"
    assert report["evidence_class"] == "deterministic_fake_provider"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert checks["B04a.available_cents"] is True
    assert checks["B04a.outcome"] is True
    assert checks["B04b.outcome"] is True
    assert observed["B04a.available_cents"] == 10000
    assert observed["B04a.outcome"] == "accept_budget"
    assert observed["B04b.outcome"] == "period_mismatch"
    assert "available_cents" not in observed
    assert fixture_budget(_inputs(case, _variants(case)[0])).available_cents == 10000
    with pytest.raises(ValueError, match="current New York month"):
        fixture_budget(_inputs(case, _variants(case)[1]))


def test_b05_stale_and_dst_variants() -> None:
    case = _budget_cases()["B05"]
    report = evaluate_budget_case(case)
    assert report["case_id"] == "B05"
    assert report["evidence_class"] == "deterministic_fake_provider"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert checks["B05a.outcome"] is True
    assert checks["B05b.available_cents"] is True
    assert checks["B05b.stale"] is True
    assert checks["B05b.outcome"] is True
    assert checks["B05c.outcome"] is True
    assert observed["B05a.outcome"] == "stale_reject"
    assert observed["B05b.available_cents"] == 2000
    assert observed["B05b.stale"] is True
    assert observed["B05b.outcome"] == "stale_cap_accept"
    assert observed["B05c.outcome"] == "stale_reject"
    variants = _variants(case)
    with pytest.raises(StaleSpendingError):
        fixture_budget(_inputs(case, variants[0]))
    capped = fixture_budget(_inputs(case, variants[1]))
    assert capped.available_cents == 2000
    assert capped.stale is True
    with pytest.raises(StaleSpendingError):
        fixture_budget(_inputs(case, variants[2]))


def test_malformed_inputs_fail_without_echoing_strings() -> None:
    case = copy.deepcopy(_budget_cases()["B01"])
    marker = f"{SECRET_MARKER}-malformed-limit"
    case["inputs"] = {
        "monthly_limit_cents": marker,
        "now": "not-a-clock",
        "budget_period": "bad",
    }
    report = evaluate_budget_case(case)
    blob = _blob(report)
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["outcome"] == "unexpected_error"
    assert checks["available_cents"] is False
    assert checks["outcome"] is False
    assert marker not in blob
    assert "not-a-clock" not in blob
    prompt = case["prompt"]
    assert isinstance(prompt, str)
    assert prompt not in blob


def test_wrong_budget_output_fails_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _budget_cases()["B01"]
    gold = _mapping(case["expected"], "expected")
    monkeypatch.setattr("app.evaluation_budget_inputs.calculate_budget", _wrong_budget)
    report = evaluate_budget_case(case)
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["available_cents"] == 1
    assert observed["pending_cents"] == 2
    assert observed["stale"] is True
    assert observed["available_cents"] != gold["available_cents"]
    assert checks["available_cents"] is False
    assert checks["pending_cents"] is False
    assert checks["stale"] is False
    assert checks["outcome"] is False


def test_secret_error_fails_without_leak_or_false_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.evaluation_budget_inputs.calculate_budget", _secret_error)
    for case_id in ("B01", "B04", "B05"):
        report = evaluate_budget_case(_budget_cases()[case_id])
        blob = _blob(report).lower()
        assert SECRET_MARKER.lower() not in blob
        assert "access_token" not in blob
        observed = _mapping(report["observed"], "observed")
        checks = _mapping(report["checks"], "checks")
        for key, value in observed.items():
            if key.endswith("outcome") or key == "outcome":
                assert value == "unexpected_error"
        assert all(value is False for value in checks.values())
        assert "period_mismatch" not in observed.values()
        assert "stale_reject" not in observed.values()


def test_bool_int_type_mismatch_fails_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _zero_as_false(inputs: dict[str, object]) -> dict[str, object]:
        del inputs
        return {
            "available_cents": False,
            "pending_cents": False,
            "stale": 0,
            "outcome": "accept_budget",
        }

    monkeypatch.setattr("app.evaluation_budget._observe", _zero_as_false)
    zero_report = evaluate_budget_case(_budget_cases()["B03"])
    zero_checks = _mapping(zero_report["checks"], "checks")
    zero_observed = _mapping(zero_report["observed"], "observed")
    assert zero_observed["available_cents"] is False
    assert zero_observed["pending_cents"] is False
    assert zero_observed["stale"] == 0
    assert zero_checks["available_cents"] is False
    assert zero_checks["pending_cents"] is False
    assert zero_checks["stale"] is False

    def _true_as_one(inputs: dict[str, object]) -> dict[str, object]:
        del inputs
        return {
            "available_cents": 2000,
            "pending_cents": 0,
            "stale": 1,
            "outcome": "stale_cap_accept",
        }

    monkeypatch.setattr("app.evaluation_budget._observe", _true_as_one)
    stale_report = evaluate_budget_case(_budget_cases()["B05"])
    stale_checks = _mapping(stale_report["checks"], "checks")
    stale_observed = _mapping(stale_report["observed"], "observed")
    assert stale_observed["B05b.stale"] == 1
    assert stale_checks["B05b.stale"] is False
    assert stale_checks["B05b.available_cents"] is True
