from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import cast

from app.agent.planning_tool import execute_plan
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_model_score import score_model_plan

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
PERIOD = date(2026, 9, 1)
CANONICAL = {
    "case_id",
    "scope",
    "status",
    "passed",
    "checks",
    "metrics_status",
    "evidence_class",
}


def _load_case(case_id: str) -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == case_id:
            return copy.deepcopy(row)
    raise AssertionError(f"missing case {case_id}")


def _inputs(case: dict[str, object]) -> dict[str, object]:
    raw = case["inputs"]
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def _request_from_case(case: dict[str, object]) -> dict[str, object]:
    inputs = _inputs(case)
    meals_key = "followup_meals" if case["id"] == "F05" else "meals"
    return {
        "meals": copy.deepcopy(inputs[meals_key]),
        "budget_period": inputs["budget_period"],
        "plan_cap_cents": inputs["plan_cap_cents"],
        "diet": inputs["diet"],
        "pantry_ingredients": copy.deepcopy(inputs["pantry_ingredients"]),
        "ingredient_exclusions": copy.deepcopy(inputs["ingredient_exclusions"]),
    }


def _planned(
    case: dict[str, object], request: dict[str, object] | None = None
) -> dict[str, object]:
    payload = _request_from_case(case) if request is None else request
    return execute_plan(payload, fixture_budget(_inputs(case)), PERIOD)


def _wrap(planned: dict[str, object]) -> dict[str, object]:
    plan = planned["plan"]
    assert isinstance(plan, dict)
    accepted = plan["accepted"] is True
    return {
        "status": "planned" if accepted else "needs_revision",
        "plan": plan,
        "request": planned["request"],
        "budget": planned["budget"],
        "tool_trace": [{"tool": "plan_groceries", "outcome": "success"}],
        "model_turns": 2,
        "planner_revisions": 1,
    }


def _observation(
    case: dict[str, object],
    result: dict[str, object],
    *,
    evidence_class: str = "deterministic_fake_provider",
    status: str = "completed",
    turns: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    messages = case["messages"]
    assert isinstance(messages, list)
    if turns is None:
        prior: dict[str, object] = {
            "status": "completed",
            "result": {
                "status": "planned",
                "plan": {},
                "request": {},
                "budget": {},
                "tool_trace": [{"tool": "plan_groceries", "outcome": "success"}],
                "model_turns": 1,
                "planner_revisions": 1,
            },
        }
        turns = [copy.deepcopy(prior) for _ in range(max(len(messages) - 1, 0))]
        turns.append({"status": "completed", "result": result})
    return {
        "case_id": case["id"],
        "status": status,
        "turns": turns,
        "evidence_class": evidence_class,
    }


def _checks(report: dict[str, object]) -> dict[str, bool]:
    raw = report["checks"]
    assert isinstance(raw, dict)
    return cast(dict[str, bool], raw)


def _score_case(case_id: str) -> dict[str, object]:
    case = _load_case(case_id)
    return score_model_plan(case, _observation(case, _wrap(_planned(case))))


def test_accepted_fixture_plans_pass() -> None:
    for case_id in ("F01", "F02", "F05"):
        report = _score_case(case_id)
        assert report["case_id"] == case_id
        assert report["scope"] == "structural_plan"
        assert report["status"] == "passed"
        assert report["passed"] is True
        assert report["metrics_status"] == "unassessed"
        checks = _checks(report)
        assert checks["plan_accepted"] is True
        assert checks["final_status"] is True


def test_rejected_fixture_plans_pass() -> None:
    for case_id in ("X04", "A01"):
        report = _score_case(case_id)
        assert report["case_id"] == case_id
        assert report["status"] == "passed"
        assert report["passed"] is True
        checks = _checks(report)
        assert checks["plan_accepted"] is True
        assert checks["final_status"] is True


def test_f05_uses_followup_meals_and_skips_missing_available() -> None:
    report = _score_case("F05")
    checks = _checks(report)
    assert "budget_available_cents" not in checks
    assert checks["request_meals"] is True
    assert report["passed"] is True


def test_bool_int_nested_mismatch_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    plan["accepted"] = 1
    lines = plan["lines"]
    assert isinstance(lines, list)
    line = lines[0]
    assert isinstance(line, dict)
    line["from_pantry"] = 1 if line["from_pantry"] is True else 0
    report = score_model_plan(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_accepted"] is False
    assert checks["plan_lines"] is False
    assert report["passed"] is False


def test_pantry_drop_fails_request_pantry() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    request["pantry_ingredients"] = []
    report = score_model_plan(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_pantry"] is False
    assert checks["plan_accepted"] is True
    assert report["passed"] is False


def test_a01_none_cap_fails_request_cap() -> None:
    case = _load_case("A01")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    request["plan_cap_cents"] = None
    report = score_model_plan(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_plan_cap"] is False
    assert checks["plan_accepted"] is True
    assert checks["budget_available_cents"] is True
    assert report["passed"] is False


def test_wrong_servings_fail_request_meals() -> None:
    case = _load_case("F05")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    meals = request["meals"]
    assert isinstance(meals, list)
    meal = meals[0]
    assert isinstance(meal, dict)
    meal["servings"] = 2
    report = score_model_plan(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_meals"] is False
    assert report["passed"] is False


def test_partial_missing_and_zero_turns_fail() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    partial = [
        {"status": "completed", "result": result},
        {"status": "failed", "reason": "provider_unavailable"},
    ]
    missing = _observation(case, result)
    del missing["turns"]
    reports = (
        score_model_plan(case, _observation(case, result, turns=partial)),
        score_model_plan(case, missing),
        score_model_plan(case, _observation(case, result, turns=[])),
    )
    for report in reports:
        checks = _checks(report)
        assert checks["turns_complete"] is False
        assert report["passed"] is False


def test_duplicate_lines_fail() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    lines = plan["lines"]
    assert isinstance(lines, list)
    lines.append(copy.deepcopy(lines[0]))
    report = score_model_plan(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_lines"] is False
    assert report["passed"] is False


def test_gold_missing_total_fails() -> None:
    case = _load_case("F01")
    obs = _observation(case, _wrap(_planned(case)))
    expected = case["expected"]
    assert isinstance(expected, dict)
    expected.pop("total_cents")
    report = score_model_plan(case, obs)
    checks = _checks(report)
    assert checks["plan_total_cents"] is False
    assert report["passed"] is False


def test_gold_line_field_missing_fails() -> None:
    case = _load_case("F01")
    obs = _observation(case, _wrap(_planned(case)))
    expected = case["expected"]
    assert isinstance(expected, dict)
    lines = expected["lines"]
    assert isinstance(lines, list)
    line = lines[0]
    assert isinstance(line, dict)
    line.pop("cost_cents")
    report = score_model_plan(case, obs)
    checks = _checks(report)
    assert checks["plan_lines"] is False
    assert report["passed"] is False


def test_wrong_case_is_unassessed_with_fake_evidence() -> None:
    case = _load_case("M01")
    obs: dict[str, object] = {
        "case_id": "M01",
        "status": "completed",
        "turns": [{"status": "completed", "result": {"status": "planned"}}],
        "evidence_class": "deterministic_fake_provider",
    }
    report = score_model_plan(case, obs)
    assert report["case_id"] == "invalid_case"
    assert report["status"] == "unassessed"
    assert report["passed"] is False
    assert report["metrics_status"] == "unassessed"
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert _checks(report) == {"supported_case": False}


def test_fake_evidence_label_remains_fake() -> None:
    case = _load_case("F01")
    gold = case["expected"]
    assert isinstance(gold, dict)
    assert gold["evidence_class"] == "real_bedrock"
    report = score_model_plan(case, _observation(case, _wrap(_planned(case))))
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["passed"] is True


def test_gold_mutation_is_independent_of_observation() -> None:
    case = _load_case("F01")
    obs = _observation(case, _wrap(_planned(case)))
    valid = score_model_plan(case, obs)
    mutated = copy.deepcopy(case)
    expected = mutated["expected"]
    assert isinstance(expected, dict)
    expected["total_cents"] = 1
    broken = score_model_plan(mutated, obs)
    assert valid["passed"] is True
    assert broken["passed"] is False
    assert _checks(broken)["plan_total_cents"] is False
    assert score_model_plan(case, obs)["passed"] is True


def test_request_mutation_is_independent_of_gold() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    valid = score_model_plan(case, _observation(case, result))
    mutated = copy.deepcopy(result)
    request = mutated["request"]
    assert isinstance(request, dict)
    request["pantry_ingredients"] = []
    gold = case["expected"]
    assert isinstance(gold, dict)
    assert gold["total_cents"] == 1574
    broken = score_model_plan(case, _observation(case, mutated))
    assert valid["passed"] is True
    assert broken["passed"] is False
    assert _checks(broken)["request_pantry"] is False


def test_report_omits_raw_answer_and_metadata() -> None:
    report = _score_case("X04")
    assert set(report) <= CANONICAL
    assert "answer" not in report
    assert "model_id" not in report
    assert "prompt_hash" not in report
    assert "turns" not in report
    assert "metadata" not in report
