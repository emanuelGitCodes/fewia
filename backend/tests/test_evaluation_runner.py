from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from app.evaluation_runner import run_evaluation

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
FORBIDDEN_SCORE_KEYS = frozenset(
    {
        "accuracy",
        "fake_score",
        "pass_rate",
        "success_rate",
        "success_score",
    }
)


def load_corpus() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _slots(result: dict[str, object]) -> list[dict[str, object]]:
    rows = result["slots"]
    assert isinstance(rows, list)
    return [_mapping(item, "slot") for item in rows]


def _walk(value: object) -> Iterator[object]:
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def test_slot_count_is_ninety_with_three_repeats_per_case() -> None:
    result = run_evaluation(load_corpus())
    assert result["slot_count"] == 90
    slots = _slots(result)
    assert len(slots) == 90
    repeats: dict[str, set[int]] = defaultdict(set)
    for slot in slots:
        case_id = slot["case_id"]
        assert type(case_id) is str
        repeat = slot["repeat"]
        assert type(repeat) is int
        repeats[case_id].add(repeat)
    assert len(repeats) == 30
    for values in repeats.values():
        assert values == {1, 2, 3}


def test_budget_b01_slot_is_scored_with_checks() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    slot = next(item for item in slots if item["case_id"] == "B01")
    assert slot["group"] == "budget"
    assert slot["status"] == "scored"
    report = _mapping(slot["report"], "report")
    checks = _mapping(report["checks"], "checks")
    assert checks


def test_meals_m01_slot_is_scored_with_accepted_true() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    slot = next(item for item in slots if item["case_id"] == "M01")
    assert slot["group"] == "meals"
    assert slot["status"] == "scored"
    report = _mapping(slot["report"], "report")
    checks = _mapping(report["checks"], "checks")
    assert checks["accepted"] is True


def test_followup_slot_is_unassessed_without_report() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    slot = next(item for item in slots if item["case_id"] == "F01")
    assert slot["status"] == "unassessed"
    assert slot["report"] is None


def test_followup_f03_slot_is_scored_with_exclusion_reject() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    slot = next(item for item in slots if item["case_id"] == "F03")
    assert slot["status"] == "scored"
    report = _mapping(slot["report"], "report")
    observed = _mapping(report["observed"], "observed")
    assert observed["outcome"] == "exclusion_reject"


def test_missing_x01_slot_is_scored_with_incomplete_estimate() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    slot = next(item for item in slots if item["case_id"] == "X01")
    assert slot["group"] == "missing"
    assert slot["status"] == "scored"
    report = _mapping(slot["report"], "report")
    observed = _mapping(report["observed"], "observed")
    assert observed["outcome"] == "incomplete_estimate"


def test_missing_x02_slot_is_unassessed_without_report() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    slot = next(item for item in slots if item["case_id"] == "X02")
    assert slot["group"] == "missing"
    assert slot["status"] == "unassessed"
    assert slot["report"] is None


def test_return_omits_aggregate_scores() -> None:
    result = run_evaluation(load_corpus())
    for item in _walk(result):
        if not isinstance(item, dict):
            continue
        keys = {str(key).lower() for key in item}
        assert keys.isdisjoint(FORBIDDEN_SCORE_KEYS)


def test_metrics_status_is_unassessed() -> None:
    result = run_evaluation(load_corpus())
    assert result["metrics_status"] == "unassessed"
    assert result["version"] == "grocery-eval-v1.1"
    assert result["repeats"] == 3


def test_empty_or_non_list_scenarios_yield_zero_slots() -> None:
    empty = run_evaluation({"scenarios": [], "metrics_status": "unassessed"})
    assert empty["slot_count"] == 0
    assert empty["metrics_status"] == "unassessed"
    assert empty["slots"] == []
    missing = run_evaluation({"scenarios": "not-a-list", "metrics_status": "scored"})
    assert missing["slot_count"] == 0
    assert missing["metrics_status"] == "unassessed"
    assert missing["slots"] == []
    absent = run_evaluation({})
    assert absent["slot_count"] == 0
    assert absent["metrics_status"] == "unassessed"
    assert absent["version"] == "invalid_version"
