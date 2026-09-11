from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from app.evaluation_missing import evaluate_missing_case

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"


def _missing_case() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "X01":
            return row
    raise AssertionError("X01 missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def test_x01_accepted_check_true() -> None:
    report = evaluate_missing_case(_missing_case())
    assert report["case_id"] == "X01"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["accepted"] is False
    assert checks["accepted"] is True


def test_x01_incomplete_estimate_outcome() -> None:
    report = evaluate_missing_case(_missing_case())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["outcome"] == "incomplete_estimate"
    assert checks["outcome"] is True


def test_x01_omits_null_total_cents_check() -> None:
    report = evaluate_missing_case(_missing_case())
    checks = _mapping(report["checks"], "checks")
    assert "total_cents" not in checks


def test_x01_unassessed_includes_model_quality() -> None:
    report = evaluate_missing_case(_missing_case())
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    assert "model_quality" in unassessed


def test_x01_report_omits_success_score() -> None:
    report = evaluate_missing_case(_missing_case())
    assert "success_score" not in report
