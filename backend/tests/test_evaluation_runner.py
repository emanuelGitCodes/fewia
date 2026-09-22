from __future__ import annotations

import copy
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
EXISTING_SCORED = frozenset(
    {
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "M01",
        "M02",
        "M03",
        "M04",
        "M05",
        "M06",
        "M07",
        "F03",
        "X01",
        "P01",
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
    assert result["version"] == "grocery-eval-v1"
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


def test_p03_slot_is_scored_with_bounded_failure() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    scored = [item for item in slots if item["case_id"] == "P03"]
    assert len(scored) == 3
    for slot in scored:
        assert slot["group"] == "provider"
        assert slot["status"] == "scored"
        report = _mapping(slot["report"], "report")
        observed = _mapping(report["observed"], "observed")
        checks = _mapping(report["checks"], "checks")
        assert report["evidence_class"] == "deterministic_fake_provider"
        assert observed["outcome"] == "bounded_failure"
        assert observed["model_calls"] == 1
        assert checks["outcome"] is True
        assert checks["accepted"] is True
        assert checks["fake_answer_forbidden"] is True
        assert checks["max_model_turns"] is True


def test_scored_count_is_forty_eight() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    scored_ids = {slot["case_id"] for slot in slots if slot["status"] == "scored"}
    unassessed = [slot for slot in slots if slot["status"] == "unassessed"]
    scored = [slot for slot in slots if slot["status"] == "scored"]
    assert len(slots) == 90
    assert len(scored) == 48
    assert len(unassessed) == 42
    assert scored_ids == EXISTING_SCORED | {"P03"}


def test_existing_scored_reports_keep_status() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    for case_id in EXISTING_SCORED:
        matches = [item for item in slots if item["case_id"] == case_id]
        assert len(matches) == 3
        for slot in matches:
            assert slot["status"] == "scored"
            assert slot["report"] is not None


def test_other_provider_cases_stay_unassessed() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    for case_id in ("P02", "P04", "P05"):
        matches = [item for item in slots if item["case_id"] == case_id]
        assert len(matches) == 3
        for slot in matches:
            assert slot["status"] == "unassessed"
            assert slot["report"] is None


def _rewrite_p03(corpus: dict[str, object], **changes: object) -> None:
    rows = corpus["scenarios"]
    assert isinstance(rows, list)
    found = False
    for item in rows:
        case = _mapping(item, "case")
        if case.get("id") != "P03":
            continue
        found = True
        if "requires_model" in changes:
            case["requires_model"] = changes["requires_model"]
        if "kind" in changes or "provider" in changes:
            behavior = _mapping(case["fixture_behavior"], "fixture_behavior")
            if "kind" in changes:
                behavior["kind"] = changes["kind"]
            if "provider" in changes:
                behavior["provider"] = changes["provider"]
            case["fixture_behavior"] = behavior
    assert found


def test_unsupported_kind_is_not_dispatched() -> None:
    corpus = copy.deepcopy(load_corpus())
    _rewrite_p03(corpus, kind="plaid_refresh_failure")
    slots = _slots(run_evaluation(corpus))
    matches = [item for item in slots if item["case_id"] == "P03"]
    assert len(matches) == 3
    for slot in matches:
        assert slot["status"] == "unassessed"
        assert slot["report"] is None


def test_requires_model_true_is_not_dispatched() -> None:
    corpus = copy.deepcopy(load_corpus())
    _rewrite_p03(corpus, requires_model=True)
    slots = _slots(run_evaluation(corpus))
    matches = [item for item in slots if item["case_id"] == "P03"]
    assert len(matches) == 3
    for slot in matches:
        assert slot["status"] == "unassessed"
        assert slot["report"] is None


def test_fake_provider_variant_without_fake_flag_stays_unassessed() -> None:
    corpus = copy.deepcopy(load_corpus())
    _rewrite_p03(corpus, provider="bedrock")
    slots = _slots(run_evaluation(corpus))
    matches = [item for item in slots if item["case_id"] == "P03"]
    assert len(matches) == 3
    for slot in matches:
        assert slot["status"] == "unassessed"
        assert slot["report"] is None


def test_p01_slot_is_scored_with_nonempty_passing_checks() -> None:
    slots = _slots(run_evaluation(load_corpus()))
    scored = [item for item in slots if item["case_id"] == "P01"]
    assert len(scored) == 3
    for slot in scored:
        assert slot["group"] == "provider"
        assert slot["status"] == "scored"
        report = _mapping(slot["report"], "report")
        checks = _mapping(report["checks"], "checks")
        assert checks
        for value in checks.values():
            assert value is True
        assert report["evidence_class"] == "deterministic_fake_provider"
        observed = _mapping(report["observed"], "observed")
        assert observed["evidence_class"] == "deterministic_fake_provider"


def test_p04_stays_unassessed_with_controlled_fake_report() -> None:
    corpus = load_corpus()
    rows = corpus["scenarios"]
    assert isinstance(rows, list)
    case = next(_mapping(item, "case") for item in rows if item.get("id") == "P04")
    assert case["requires_model"] is True
    slots = _slots(run_evaluation(corpus))
    matches = [item for item in slots if item["case_id"] == "P04"]
    assert len(matches) == 3
    forbidden = FORBIDDEN_SCORE_KEYS | {
        "p50_latency",
        "p95_latency",
        "token_use",
        "estimated_cost",
        "model_calls",
        "success_rate",
    }
    for slot in matches:
        assert slot["status"] == "unassessed"
        assert slot["report"] is None
        report = _mapping(slot["controlled_report"], "controlled_report")
        assert report["case_id"] == "P04"
        assert report["evidence_class"] == "deterministic_fake_provider"
        assert report["target_evidence_class"] == "real_bedrock"
        checks = _mapping(report["checks"], "checks")
        assert checks
        for value in checks.values():
            assert value is True
        keys = {str(key).lower() for key in report}
        assert keys.isdisjoint(forbidden)
        for item in _walk(report):
            if not isinstance(item, dict):
                continue
            nested = {str(key).lower() for key in item}
            assert nested.isdisjoint(FORBIDDEN_SCORE_KEYS)
