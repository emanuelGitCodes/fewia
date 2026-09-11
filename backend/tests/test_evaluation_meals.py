from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

from app.evaluation_meals import evaluate_meal_case

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
MEAL_IDS = ("M01", "M02", "M06")
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _meal_cases() -> dict[str, dict[str, object]]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    found: dict[str, dict[str, object]] = {}
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        case_id = row.get("id")
        if case_id in MEAL_IDS:
            found[str(case_id)] = row
    return found


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def test_m01_accepted_and_total_cents_pass() -> None:
    report = evaluate_meal_case(_meal_cases()["M01"])
    assert report["case_id"] == "M01"
    checks = _mapping(report["checks"], "checks")
    assert checks["accepted"] is True
    assert checks["total_cents"] is True
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    assert "model_quality" in unassessed


def test_m02_total_cents_matches_gold() -> None:
    report = evaluate_meal_case(_meal_cases()["M02"])
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["total_cents"] == 2860
    assert checks["total_cents"] is True


def test_m06_variants_score_accept_and_diet_conflict() -> None:
    report = evaluate_meal_case(_meal_cases()["M06"])
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert checks["M06a.accepted"] is True
    assert checks["M06a.total_cents"] is True
    assert "M06b.total_cents" not in checks
    assert checks["M06b.outcome"] is True
    assert observed["M06b.outcome"] == "diet_conflict"


def test_wrong_total_cents_gold_fails() -> None:
    case = copy.deepcopy(_meal_cases()["M01"])
    expected = _mapping(case["expected"], "expected")
    expected["total_cents"] = 0
    case["expected"] = expected
    report = evaluate_meal_case(case)
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["total_cents"] != 0
    assert checks["total_cents"] is False


def test_malformed_clock_secret_stays_out_of_report() -> None:
    case = copy.deepcopy(_meal_cases()["M01"])
    marker = f"{SECRET_MARKER}-not-a-clock"
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["now"] = marker
    case["inputs"] = inputs
    report = evaluate_meal_case(case)
    case_id = report["case_id"]
    assert isinstance(case_id, str)
    assert marker not in case_id
    checks = _mapping(report["checks"], "checks")
    for key in checks:
        assert marker not in key
    observed = _mapping(report["observed"], "observed")
    for value in observed.values():
        assert marker not in str(value)


def test_report_omits_success_score_and_metrics_status() -> None:
    report = evaluate_meal_case(_meal_cases()["M01"])
    assert "success_score" not in report
    assert "metrics_status" not in report
    assert "pass_rate" not in report
