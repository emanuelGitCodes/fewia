from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import cast

from app.agent.planning_tool import execute_plan
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_comparison import compare_reference
from app.evaluation_reference import observe_reference_case

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
PERIOD = date(2026, 9, 1)
SUPPORTED = ("F01", "F02", "F05", "X04", "A01")
CANONICAL = {
    "case_id",
    "scope",
    "condition",
    "status",
    "passed",
    "checks",
    "metrics_status",
    "evidence_class",
    "scope_note",
}
FAKE_FIELDS = (
    "answer",
    "messages",
    "evidence_id",
    "evidence_ids",
    "evidence_revision_id",
    "tokens",
    "input_tokens",
    "output_tokens",
    "latency",
    "elapsed_seconds",
    "usage",
    "cost",
    "estimated_cost",
    "model_quality",
    "prompt",
)
SCOPE_NOTE = (
    "The reference uses structured inputs. "
    "It compares the final result only. "
    "It does not measure language understanding, earlier-turn quality, "
    "or persisted evidence."
)


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
        "answer": "provider text MUST stay out of the report",
        "evidence_id": planned.get("evidence_id"),
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
                "status": "clarification",
                "plan": {},
                "request": {},
                "budget": {},
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


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def _compare_case(case_id: str) -> dict[str, object]:
    case = _load_case(case_id)
    return compare_reference(case, _observation(case, _wrap(_planned(case))))


def test_all_five_cases_pass_including_followup_and_reject() -> None:
    for case_id in SUPPORTED:
        report = _compare_case(case_id)
        assert report["case_id"] == case_id
        assert report["scope"] == "deterministic_reference_final_plan"
        assert report["condition"] == "deterministic_structured_input"
        assert report["status"] == "passed"
        assert report["passed"] is True
        assert report["metrics_status"] == "unassessed"
        assert report["scope_note"] == SCOPE_NOTE
        assert report["evidence_class"] == "deterministic_fake_provider"
        checks = _checks(report)
        assert checks["supported_case"] is True
        assert checks["turns_complete"] is True
        assert checks["plan_accepted"] is True
        assert checks["final_status"] is True
        assert checks["plan_notice"] is True
        assert checks["plan_lines"] is True


def test_f05_followup_uses_final_four_servings() -> None:
    case = _load_case("F05")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    assert request["meals"] == [{"recipe_id": "chicken_tacos", "servings": 4}]
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_meals"] is True
    assert checks["final_status"] is True
    assert report["passed"] is True


def test_a01_reject_needs_revision_and_cap() -> None:
    case = _load_case("A01")
    result = _wrap(_planned(case))
    request = result["request"]
    plan = result["plan"]
    assert isinstance(request, dict)
    assert isinstance(plan, dict)
    assert request["plan_cap_cents"] == 1
    assert plan["accepted"] is False
    assert result["status"] == "needs_revision"
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_plan_cap"] is True
    assert checks["plan_accepted"] is True
    assert checks["final_status"] is True
    assert report["passed"] is True


def test_reference_observation_matches_execute_plan() -> None:
    case = _load_case("X04")
    ref = observe_reference_case(case)
    planned = _planned(case)
    wrapped = _wrap(planned)
    report = compare_reference(case, _observation(case, wrapped))
    assert ref["status"] == "completed"
    assert wrapped["request"] == ref["request"]
    assert wrapped["plan"] == ref["plan"]
    assert wrapped["budget"] == ref["budget"]
    assert report["passed"] is True


def test_a01_none_cap_fails() -> None:
    case = _load_case("A01")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    request["plan_cap_cents"] = None
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_plan_cap"] is False
    assert report["passed"] is False
    assert report["status"] == "failed"


def test_missing_none_cap_field_fails() -> None:
    case = _load_case("F02")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    assert request["plan_cap_cents"] is None
    del request["plan_cap_cents"]
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_plan_cap"] is False
    assert report["passed"] is False


def test_pantry_drop_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    request = result["request"]
    assert isinstance(request, dict)
    request["pantry_ingredients"] = []
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["request_pantry"] is False
    assert report["passed"] is False


def test_quantity_mismatch_fails_lines() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    rows = plan["lines"]
    assert isinstance(rows, list)
    line = rows[0]
    assert isinstance(line, dict)
    quantity = line["quantity"]
    assert type(quantity) is int
    line["quantity"] = quantity + 1
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_lines"] is False
    assert report["passed"] is False


def test_total_mismatch_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    plan["total_cents"] = 1
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_total_cents"] is False
    assert report["passed"] is False


def test_stale_mismatch_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    budget = result["budget"]
    assert isinstance(budget, dict)
    budget["stale"] = True
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["budget_stale"] is False
    assert report["passed"] is False


def test_notice_mismatch_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    plan["notice"] = "verified checkout price"
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_notice"] is False
    assert report["passed"] is False


def test_bool_int_mismatch_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    plan["accepted"] = 1
    rows = plan["lines"]
    assert isinstance(rows, list)
    line = rows[0]
    assert isinstance(line, dict)
    line["from_pantry"] = 1 if line["from_pantry"] is True else 0
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_accepted"] is False
    assert checks["plan_lines"] is False
    assert report["passed"] is False


def test_duplicate_ingredients_fail() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    plan = result["plan"]
    assert isinstance(plan, dict)
    rows = plan["lines"]
    assert isinstance(rows, list)
    rows.append(copy.deepcopy(rows[0]))
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_lines"] is False
    assert report["passed"] is False


def test_status_mismatch_fails() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    result["status"] = "clarification"
    report = compare_reference(case, _observation(case, result, status="partial"))
    checks = _checks(report)
    assert checks["observation_complete"] is False
    assert checks["final_status"] is False
    assert report["passed"] is False
    assert report["status"] == "failed"


def test_disallowed_evidence_fails_without_echo() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    report = compare_reference(
        case, _observation(case, result, evidence_class="plaid_sandbox")
    )
    blob = _blob(report)
    checks = _checks(report)
    assert checks["evidence_allowed"] is False
    assert report["passed"] is False
    assert "evidence_class" not in report
    assert "plaid_sandbox" not in blob


def test_missing_turns_fail() -> None:
    case = _load_case("F05")
    result = _wrap(_planned(case))
    missing = _observation(case, result)
    del missing["turns"]
    reports = (
        compare_reference(case, _observation(case, result, turns=[])),
        compare_reference(
            case,
            _observation(
                case,
                result,
                turns=[{"status": "completed", "result": result}],
            ),
        ),
        compare_reference(case, missing),
    )
    for report in reports:
        checks = _checks(report)
        assert checks["turns_complete"] is False
        assert report["passed"] is False


def test_gold_mutation_has_no_effect() -> None:
    case = _load_case("F01")
    obs = _observation(case, _wrap(_planned(case)))
    expected = case["expected"]
    assert isinstance(expected, dict)
    expected["total_cents"] = 1
    expected["accepted"] = False
    expected["lines"] = []
    expected["notice"] = "altered gold"
    report = compare_reference(case, obs)
    assert report["passed"] is True
    assert report["status"] == "passed"


def test_earlier_bad_final_correct_passes_final_only_scope() -> None:
    case = _load_case("F02")
    correct = _wrap(_planned(case))
    messages = case["messages"]
    assert isinstance(messages, list)
    bad: dict[str, object] = {
        "status": "completed",
        "result": {
            "status": "clarification",
            "plan": {"accepted": False, "total_cents": 1, "lines": []},
            "request": {"meals": [], "plan_cap_cents": 99},
            "budget": {"stale": True},
        },
    }
    turns = [copy.deepcopy(bad) for _ in range(len(messages) - 1)]
    turns.append({"status": "completed", "result": correct})
    report = compare_reference(case, _observation(case, correct, turns=turns))
    assert len(turns) == 3
    assert report["passed"] is True
    assert report["scope"] == "deterministic_reference_final_plan"
    assert "earlier-turn quality" in str(report["scope_note"])


def test_inputs_unmodified() -> None:
    case = _load_case("F05")
    before = copy.deepcopy(case)
    obs = _observation(case, _wrap(_planned(case)))
    obs_before = copy.deepcopy(obs)
    report = compare_reference(case, obs)
    assert report["passed"] is True
    assert case == before
    assert obs == obs_before


def test_unsupported_case_is_unassessed() -> None:
    case = _load_case("M01")
    obs: dict[str, object] = {
        "case_id": "M01",
        "status": "completed",
        "turns": [{"status": "completed", "result": {"status": "planned"}}],
        "evidence_class": "deterministic_fake_provider",
    }
    report = compare_reference(case, obs)
    blob = _blob(report)
    assert report["case_id"] == "invalid_case"
    assert report["status"] == "unassessed"
    assert report["passed"] is False
    assert report["metrics_status"] == "unassessed"
    assert _checks(report) == {"supported_case": False}
    assert "M01" not in blob


def test_malformed_reference_is_unassessed() -> None:
    case = _load_case("F01")
    inputs = _inputs(case)
    meals = inputs["meals"]
    assert isinstance(meals, list)
    meal = meals[0]
    assert isinstance(meal, dict)
    meal["recipe_id"] = "salmon_tacos"
    obs: dict[str, object] = {
        "case_id": "F01",
        "status": "completed",
        "turns": [
            {"status": "completed", "result": {"status": "planned"}},
            {"status": "completed", "result": {"status": "planned"}},
        ],
        "evidence_class": "real_bedrock",
    }
    report = compare_reference(case, obs)
    assert report["case_id"] == "F01"
    assert report["status"] == "unassessed"
    assert report["passed"] is False
    assert report["evidence_class"] == "real_bedrock"
    assert _checks(report) == {
        "supported_case": True,
        "reference_complete": False,
    }


def test_none_plan_maps_do_not_pass_lines() -> None:
    case = _load_case("F01")
    result = _wrap(_planned(case))
    result["plan"] = None
    report = compare_reference(case, _observation(case, result))
    checks = _checks(report)
    assert checks["plan_lines"] is False
    assert checks["plan_accepted"] is False
    assert report["passed"] is False


def test_report_omits_raw_payloads_and_fake_metrics() -> None:
    report = _compare_case("A01")
    blob = _blob(report)
    assert set(report) <= CANONICAL
    for field in FAKE_FIELDS:
        assert field not in report
        assert f'"{field}"' not in blob
    assert "provider text MUST stay out of the report" not in blob
    assert report["metrics_status"] == "unassessed"


def test_real_bedrock_label_is_allowed() -> None:
    case = _load_case("F05")
    report = compare_reference(
        case,
        _observation(case, _wrap(_planned(case)), evidence_class="real_bedrock"),
    )
    assert report["evidence_class"] == "real_bedrock"
    assert report["passed"] is True
