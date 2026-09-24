from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from app import evaluation_protocol as protocol
from app.agent import chat_loop
from app.domain.budget import BudgetResult
from app.evaluation_budget import UNASSESSED
from app.evaluation_protocol import evaluate_protocol_case
from app.evaluation_protocol_observer import observe_variant as real_observe

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _protocol_case() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "P04":
            return row
    raise AssertionError("P04 is missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def _checks(report: dict[str, object]) -> dict[str, object]:
    return _mapping(report["checks"], "checks")


def test_p04_baseline_scores_all_variants() -> None:
    case = _protocol_case()
    report = evaluate_protocol_case(case)
    assert report["case_id"] == "P04"
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["target_evidence_class"] == "real_bedrock"
    assert report["unassessed"] == list(UNASSESSED)
    for marker in (
        "model_quality",
        "live_providers",
        "real_bedrock",
        "hidden_reasoning",
        "plaid_sandbox",
        "live_instacart_development",
        "deployed_aws",
    ):
        assert marker in report["unassessed"]
    checks = _checks(report)
    assert checks == {
        "accepted": True,
        "outcome": True,
        "unknown_tool_rejected": True,
        "max_model_turns": True,
        "max_planner_revisions": True,
    }
    observed = _mapping(report["observed"], "observed")
    unknown = _mapping(observed["unknown_tool"], "unknown_tool")
    malformed = _mapping(observed["malformed"], "malformed")
    planner = _mapping(observed["planner_limit"], "planner_limit")
    assert unknown["outcome"] == "unknown_tool_reject"
    assert unknown["accepted"] is False
    assert unknown["unknown_tool_rejected"] is True
    assert unknown["model_calls"] == 8
    assert unknown["unsupported_results"] == 7
    assert unknown["trace_tools"] == ["unsupported"] * 8
    assert malformed["outcome"] == "malformed_tool_reject"
    assert malformed["accepted"] is False
    assert malformed["protocol_static"] is True
    assert malformed["model_calls"] == 1
    assert planner["outcome"] == "planner_limit"
    assert planner["accepted"] is False
    assert planner["planner_revisions"] == 3
    assert planner["model_calls"] == 4
    assert planner["trace_tools"] == ["plan_groceries"] * 3
    blob = _blob(report)
    prompt = case["prompt"]
    assert isinstance(prompt, str)
    assert prompt not in blob
    assert "not_a_registered_tool" not in blob
    assert "messages" not in report
    assert "fixture_behavior" not in report
    assert "path_classes" not in report
    assert "credentials" not in blob
    assert case.get("messages") is not None


def test_inputs_and_gold_are_read_only() -> None:
    case = copy.deepcopy(_protocol_case())
    inputs = copy.deepcopy(_mapping(case["inputs"], "inputs"))
    gold = copy.deepcopy(_mapping(case["expected"], "expected"))
    first = evaluate_protocol_case(case)
    assert case["inputs"] == inputs
    assert case["expected"] == gold
    observed = copy.deepcopy(first["observed"])
    mutated = _mapping(case["expected"], "expected")
    mutated["accepted"] = True
    mutated["allowed_outcomes"] = ["secret_outcome"]
    mutated["max_model_turns"] = 1
    mutated["max_planner_revisions"] = 1
    second = evaluate_protocol_case(case)
    assert second["observed"] == observed
    assert case["inputs"] == inputs
    checks = _checks(second)
    assert checks["accepted"] is False
    assert checks["outcome"] is False
    assert checks["max_model_turns"] is False
    assert checks["max_planner_revisions"] is False


def test_gold_mutation_flips_checks() -> None:
    case = copy.deepcopy(_protocol_case())
    gold = _mapping(case["expected"], "expected")
    constraints = _mapping(gold["constraint_results"], "constraint_results")
    gold["accepted"] = True
    report = evaluate_protocol_case(case)
    assert _checks(report)["accepted"] is False
    gold["accepted"] = False
    gold["allowed_outcomes"] = ["planner_limit"]
    report = evaluate_protocol_case(case)
    assert _checks(report)["outcome"] is False
    gold["allowed_outcomes"] = ["unknown_tool_reject", "malformed_tool_reject"]
    constraints["unknown_tool_rejected"] = False
    report = evaluate_protocol_case(case)
    assert _checks(report)["unknown_tool_rejected"] is False
    constraints["unknown_tool_rejected"] = True
    gold["max_model_turns"] = 7
    report = evaluate_protocol_case(case)
    assert _checks(report)["max_model_turns"] is False
    gold["max_model_turns"] = 8
    constraints["turn_bound"] = 7
    report = evaluate_protocol_case(case)
    assert _checks(report)["max_model_turns"] is False
    constraints["turn_bound"] = 8
    constraints["planner_bound"] = 2
    report = evaluate_protocol_case(case)
    assert _checks(report)["max_planner_revisions"] is False
    constraints["planner_bound"] = 3
    gold["max_planner_revisions"] = 4
    report = evaluate_protocol_case(case)
    assert _checks(report)["max_planner_revisions"] is False
    gold["accepted"] = 0
    report = evaluate_protocol_case(case)
    assert _checks(report)["accepted"] is False


def test_changed_chat_loop_bounds_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_loop, "MAX_MODEL_TURNS", 5)
    monkeypatch.setattr(chat_loop, "MAX_PLANNER_REVISIONS", 1)
    report = evaluate_protocol_case(_protocol_case())
    checks = _checks(report)
    assert checks["max_model_turns"] is False
    assert checks["max_planner_revisions"] is False
    observed = _mapping(report["observed"], "observed")
    unknown = _mapping(observed["unknown_tool"], "unknown_tool")
    planner = _mapping(observed["planner_limit"], "planner_limit")
    assert unknown["model_calls"] == 5
    assert planner["planner_revisions"] == 1
    assert planner["model_calls"] == 2


def test_unexpected_accepted_mocked_observer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutated(
        case: dict[str, object],
        kind: str,
        prompt: str,
        budget: BudgetResult,
        clock: date,
    ) -> dict[str, object]:
        row = dict(real_observe(case, kind, prompt, budget, clock))
        if kind == "planner":
            row["accepted"] = True
        return row

    monkeypatch.setattr(protocol, "observe_variant", mutated)
    report = evaluate_protocol_case(_protocol_case())
    assert _checks(report)["accepted"] is False
    observed = _mapping(report["observed"], "observed")
    planner = _mapping(observed["planner_limit"], "planner_limit")
    assert planner["accepted"] is True
    assert planner["outcome"] == "planner_limit"


def test_malformed_count_mutation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def mutated(
        case: dict[str, object],
        kind: str,
        prompt: str,
        budget: BudgetResult,
        clock: date,
    ) -> dict[str, object]:
        row = dict(real_observe(case, kind, prompt, budget, clock))
        if kind == "malformed":
            row["model_calls"] = 2
        return row

    monkeypatch.setattr(protocol, "observe_variant", mutated)
    report = evaluate_protocol_case(_protocol_case())
    assert _checks(report)["outcome"] is False
    observed = _mapping(report["observed"], "observed")
    malformed = _mapping(observed["malformed"], "malformed")
    assert malformed["model_calls"] == 2
    assert malformed["protocol_static"] is True
    assert malformed["outcome"] == "malformed_tool_reject"


def test_static_invalid_input_and_secret_marker_no_leakage() -> None:
    case = copy.deepcopy(_protocol_case())
    marker = f"{SECRET_MARKER}-access_token"
    case["prompt"] = marker
    case["inputs"] = {
        "monthly_limit_cents": marker,
        "now": marker,
        "budget_period": marker,
        "credentials": marker,
    }
    case["fixture_behavior"] = {
        "kind": "malformed_or_unknown_tool",
        "unknown_tool_name": marker,
        "secret": marker,
    }
    case["metadata"] = marker
    case["expected"] = copy.deepcopy(_mapping(case["expected"], "expected"))
    gold = _mapping(case["expected"], "expected")
    gold["evidence_class"] = marker
    report = evaluate_protocol_case(case)
    blob = _blob(report)
    assert marker not in blob
    assert SECRET_MARKER not in blob
    assert "access_token" not in blob
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert "target_evidence_class" not in report
    assert "metadata" not in report
    assert "secret" not in blob
    checks = _checks(report)
    assert checks["outcome"] is False
    assert checks["unknown_tool_rejected"] is False
    assert checks["max_model_turns"] is False
    assert checks["max_planner_revisions"] is False
    observed = _mapping(report["observed"], "observed")
    for key in ("unknown_tool", "malformed", "planner_limit"):
        row = _mapping(observed[key], key)
        assert row["outcome"] == "unexpected_error"
        assert row["accepted"] is False
    missing = evaluate_protocol_case({})
    assert missing["case_id"] == "invalid_case"
    assert "target_evidence_class" not in missing
    missing_blob = _blob(missing)
    assert "prompt" not in missing_blob
    assert SECRET_MARKER not in missing_blob
    for key in ("unknown_tool", "malformed", "planner_limit"):
        row = _mapping(_mapping(missing["observed"], "observed")[key], key)
        assert row == {"outcome": "unexpected_error", "accepted": False}


def test_case_id_allowlist_rejects_marker_and_non_p04() -> None:
    case = copy.deepcopy(_protocol_case())
    marker = f"{SECRET_MARKER}-case"
    case["id"] = marker
    report = evaluate_protocol_case(case)
    blob = _blob(report)
    assert report["case_id"] == "invalid_case"
    assert marker not in blob
    assert SECRET_MARKER not in blob
    other = copy.deepcopy(_protocol_case())
    other["id"] = "P01"
    other_report = evaluate_protocol_case(other)
    assert other_report["case_id"] == "invalid_case"
    assert other_report["case_id"] != "P01"
