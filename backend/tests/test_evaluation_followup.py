from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

from app.evaluation_followup import evaluate_followup_case

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _followup_case() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "F03":
            return row
    raise AssertionError("F03 missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def test_f03_accepted_and_exclusion_reject() -> None:
    report = evaluate_followup_case(_followup_case())
    assert report["case_id"] == "F03"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["accepted"] is False
    assert checks["accepted"] is True
    assert observed["outcome"] == "exclusion_reject"
    assert checks["outcome"] is True


def test_f03_omits_null_total_cents_check() -> None:
    report = evaluate_followup_case(_followup_case())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert "total_cents" not in checks
    assert "total_cents" not in observed


def test_f03_unassessed_includes_model_quality() -> None:
    report = evaluate_followup_case(_followup_case())
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    assert "model_quality" in unassessed


def test_f03_report_omits_success_score() -> None:
    report = evaluate_followup_case(_followup_case())
    assert "success_score" not in report
    assert "metrics_status" not in report


def test_empty_meals_unexpected_error_omits_secret() -> None:
    case = copy.deepcopy(_followup_case())
    marker = f"{SECRET_MARKER}-not-a-clock"
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["meals"] = []
    inputs["now"] = marker
    case["inputs"] = inputs
    report = evaluate_followup_case(case)
    observed = _mapping(report["observed"], "observed")
    assert observed["outcome"] == "unexpected_error"
    case_id = report["case_id"]
    assert isinstance(case_id, str)
    assert marker not in case_id
    checks = _mapping(report["checks"], "checks")
    for key in checks:
        assert marker not in key
    for value in observed.values():
        assert marker not in str(value)
