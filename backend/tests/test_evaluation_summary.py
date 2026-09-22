from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from types import MappingProxyType
from typing import cast

import pytest

from app.evaluation_summary import (
    FAKE,
    INVALID,
    QUALITY_NOTE,
    REAL,
    UNKNOWN,
    summarize_evaluation,
)

SECRET = "do-not-echo-raw-input"
FORBIDDEN_SCORE_KEYS = frozenset(
    {
        "accuracy",
        "fake_score",
        "pass_rate",
        "success_rate",
        "success_score",
    }
)
MARKERS = (
    SECRET,
    "P04",
    "F01",
    "B01",
    "plan_accepted",
    "unknown_tool_rejected",
    "MARKER_ANSWER",
    "0%",
    "100%",
)


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _walk(value: object) -> Iterator[object]:
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _fixture_slot() -> dict[str, object]:
    return {
        "status": "scored",
        "report": {
            "checks": {"accepted": True},
            "evidence_class": FAKE,
        },
    }


def _plan_body(ok: bool, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "scope": "structural_plan",
        "status": "passed" if ok else "failed",
        "passed": ok,
        "checks": {"plan_accepted": ok, "final_status": True},
        "evidence_class": FAKE,
        "metrics_status": "unassessed",
    }
    body.update(overrides)
    return body


def _observed_slot(
    *,
    evidence: str = FAKE,
    plan: dict[str, object] | None = None,
    batch_label: str | None = None,
) -> dict[str, object]:
    slot: dict[str, object] = {
        "status": "observed",
        "report": None,
        "observation": {"evidence_class": evidence},
    }
    if plan is not None:
        slot["structural_assessment"] = plan
    if batch_label is not None:
        slot["evidence_class"] = batch_label
    return slot


def _controlled_slot() -> dict[str, object]:
    return {
        "status": "unassessed",
        "report": None,
        "reason": "unsupported_scenario",
        "case_id": "P04",
        "answer": SECRET,
        "metadata": {"id": "P04", "answer": "MARKER_ANSWER"},
        "controlled_report": {
            "case_id": "P04",
            "checks": {
                "accepted": True,
                "outcome": True,
                "unknown_tool_rejected": True,
            },
            "evidence_class": FAKE,
            "target_evidence_class": REAL,
            "answer": "MARKER_ANSWER",
        },
    }


def _unassessed_slot() -> dict[str, object]:
    return {
        "status": "unassessed",
        "report": None,
        "reason": "unsupported_scenario",
        "case_id": "A02",
    }


def _mixture() -> list[dict[str, object]]:
    slots: list[dict[str, object]] = [_fixture_slot() for _ in range(48)]
    slots.extend(_observed_slot(plan=_plan_body(True)) for _ in range(12))
    slots.extend(_observed_slot(plan=_plan_body(False)) for _ in range(3))
    slots.extend(_observed_slot() for _ in range(9))
    slots.extend(_controlled_slot() for _ in range(3))
    slots.extend(_unassessed_slot() for _ in range(15))
    assert len(slots) == 90
    return slots


def _assert_honest(result: dict[str, object]) -> None:
    blob = json.dumps(result, default=str)
    for marker in MARKERS:
        assert marker not in blob
    for item in _walk(result):
        if not isinstance(item, dict):
            continue
        keys = {str(key).lower() for key in item}
        assert keys.isdisjoint(FORBIDDEN_SCORE_KEYS)


def test_empty_input_is_zero_and_unassessed() -> None:
    result = summarize_evaluation([])
    assert result["total_slots"] == 0
    assert result["execution_counts"] == {
        "scored": 0,
        "observed": 0,
        "failed": 0,
        "unassessed": 0,
        "invalid": 0,
    }
    zeros = {
        "assessed": 0,
        "passed": 0,
        "failed": 0,
        "invalid": 0,
        "outside_scope": 0,
    }
    assert result["fixture_checks"] == zeros
    assert result["controlled_checks"] == zeros
    assert result["final_plan_checks"] == zeros
    assert result["evidence_breakdown"] == {
        "observation": {FAKE: 0, REAL: 0, UNKNOWN: 0},
    }
    assert result["metrics_status"] == "unassessed"
    assert result["quality_note"] == QUALITY_NOTE
    _assert_honest(result)


def test_known_mixture_keeps_execution_and_checks_separate() -> None:
    slots = _mixture()
    snapshot = copy.deepcopy(slots)
    result = summarize_evaluation(slots)
    assert slots == snapshot
    assert result["total_slots"] == 90
    assert result["execution_counts"] == {
        "scored": 48,
        "observed": 24,
        "failed": 0,
        "unassessed": 18,
        "invalid": 0,
    }
    assert result["fixture_checks"] == {
        "assessed": 48,
        "passed": 48,
        "failed": 0,
        "invalid": 0,
        "outside_scope": 42,
    }
    assert result["controlled_checks"] == {
        "assessed": 3,
        "passed": 3,
        "failed": 0,
        "invalid": 0,
        "outside_scope": 87,
    }
    assert result["final_plan_checks"] == {
        "assessed": 15,
        "passed": 12,
        "failed": 3,
        "invalid": 0,
        "outside_scope": 75,
    }
    observation = _mapping(
        _mapping(result["evidence_breakdown"], "evidence")["observation"],
        "observation",
    )
    assert observation == {FAKE: 24, REAL: 0, UNKNOWN: 0}
    assert result["metrics_status"] == "unassessed"
    assert result["quality_note"] == QUALITY_NOTE
    _assert_honest(result)
    result["execution_counts"] = {"scored": 99}
    again = summarize_evaluation(slots)
    assert again["execution_counts"]["scored"] == 48


def test_observation_evidence_ignores_batch_and_fixture_labels() -> None:
    slots = [
        _observed_slot(evidence=FAKE, batch_label=REAL),
        _observed_slot(evidence=REAL, batch_label=REAL),
        _observed_slot(evidence=REAL, batch_label=REAL),
        _fixture_slot(),
        {
            "status": "failed",
            "observation": {"evidence_class": REAL},
            "evidence_class": REAL,
            "report": None,
        },
    ]
    result = summarize_evaluation(slots)
    observation = _mapping(
        _mapping(result["evidence_breakdown"], "evidence")["observation"],
        "observation",
    )
    assert observation == {FAKE: 1, REAL: 3, UNKNOWN: 0}
    assert result["execution_counts"]["scored"] == 1
    assert result["execution_counts"]["observed"] == 3
    assert result["execution_counts"]["failed"] == 1
    assert result["fixture_checks"]["passed"] == 1
    assert result["metrics_status"] == "unassessed"


def test_missing_and_empty_checks_are_not_pass() -> None:
    missing = {"status": "scored"}
    empty = {
        "status": "scored",
        "report": {"checks": {}, "evidence_class": FAKE},
    }
    result = summarize_evaluation([missing, empty])
    assert result["execution_counts"]["scored"] == 2
    assert result["fixture_checks"] == {
        "assessed": 0,
        "passed": 0,
        "failed": 0,
        "invalid": 1,
        "outside_scope": 1,
    }
    assert result["metrics_status"] == "unassessed"


def test_bool_one_is_invalid_not_pass() -> None:
    slot = {
        "status": "scored",
        "report": {"checks": {"accepted": 1}, "evidence_class": FAKE},
    }
    mixed = {
        "status": "scored",
        "report": {
            "checks": {"accepted": True, "outcome": 1},
            "evidence_class": FAKE,
        },
    }
    failed = {
        "status": "scored",
        "report": {
            "checks": {"accepted": False},
            "evidence_class": FAKE,
        },
    }
    result = summarize_evaluation([slot, mixed, failed])
    assert result["fixture_checks"]["invalid"] == 2
    assert result["fixture_checks"]["passed"] == 0
    assert result["fixture_checks"]["failed"] == 1
    assert result["execution_counts"]["scored"] == 3


def test_fixture_and_controlled_require_fake_evidence() -> None:
    fixture = {
        "status": "scored",
        "report": {"checks": {"accepted": True}, "evidence_class": REAL},
    }
    controlled = {
        "status": "unassessed",
        "controlled_report": {
            "checks": {"accepted": True},
            "evidence_class": REAL,
        },
    }
    result = summarize_evaluation([fixture, controlled])
    assert result["execution_counts"]["scored"] == 1
    assert result["execution_counts"]["unassessed"] == 1
    assert result["fixture_checks"]["invalid"] == 1
    assert result["fixture_checks"]["passed"] == 0
    assert result["controlled_checks"]["invalid"] == 1
    assert result["controlled_checks"]["passed"] == 0


def test_final_plan_allows_fake_or_real_and_rejects_other_classes() -> None:
    fake = _observed_slot(plan=_plan_body(True, evidence_class=FAKE))
    real = _observed_slot(
        evidence=REAL,
        plan=_plan_body(True, evidence_class=REAL),
    )
    other = _observed_slot(
        plan=_plan_body(True, evidence_class="deployed_aws"),
    )
    result = summarize_evaluation([fake, real, other])
    assert result["final_plan_checks"] == {
        "assessed": 2,
        "passed": 2,
        "failed": 0,
        "invalid": 1,
        "outside_scope": 0,
    }
    observation = _mapping(
        _mapping(result["evidence_breakdown"], "evidence")["observation"],
        "observation",
    )
    assert observation == {FAKE: 2, REAL: 1, UNKNOWN: 0}


def test_contradictory_declared_pass_is_invalid() -> None:
    contradictory = _observed_slot(
        plan=_plan_body(False, status="passed", passed=True),
    )
    mismatch_status = _observed_slot(
        plan=_plan_body(True, status="failed", passed=True),
    )
    consistent_fail = _observed_slot(plan=_plan_body(False))
    unassessed_pass = _observed_slot(
        plan=_plan_body(True, status="unassessed", passed=True),
    )
    result = summarize_evaluation(
        [contradictory, mismatch_status, consistent_fail, unassessed_pass]
    )
    assert result["final_plan_checks"] == {
        "assessed": 1,
        "passed": 0,
        "failed": 1,
        "invalid": 3,
        "outside_scope": 0,
    }


def test_malformed_slot_and_top_level_shape() -> None:
    result = summarize_evaluation(
        [_fixture_slot(), "bad", 1, {"status": 1, "report": "bad"}]
    )
    assert result["total_slots"] == 4
    assert result["execution_counts"]["scored"] == 1
    assert result["execution_counts"]["invalid"] == 3
    assert result["fixture_checks"]["passed"] == 1
    assert result["fixture_checks"]["invalid"] == 3
    with pytest.raises(ValueError, match="^evaluation input is invalid$") as err:
        summarize_evaluation({"answer": SECRET, "metadata": "P04"})
    assert str(err.value) == INVALID
    assert SECRET not in str(err.value)
    assert "P04" not in str(err.value)


def test_read_only_mapping_proxy_is_invalid_and_unmodified() -> None:
    checks = MappingProxyType({"accepted": True})
    report = MappingProxyType({"checks": checks, "evidence_class": FAKE})
    slot = MappingProxyType({"status": "scored", "report": report})
    slots = [cast(dict[str, object], slot)]
    result = summarize_evaluation(slots)
    assert result["execution_counts"]["invalid"] == 1
    assert result["fixture_checks"]["invalid"] == 1
    assert result["fixture_checks"]["passed"] == 0
    assert slot["status"] == "scored"
    assert report["evidence_class"] == FAKE
    assert report["checks"] is checks
    assert checks["accepted"] is True


def test_plain_dict_summary_leaves_input_unchanged() -> None:
    mutable = _fixture_slot()
    nested = _mapping(mutable["report"], "report")
    checks = _mapping(nested["checks"], "checks")
    before = copy.deepcopy(mutable)
    summary = summarize_evaluation([mutable])
    checks["accepted"] = False
    mutable["status"] = "failed"
    assert summary["execution_counts"]["scored"] == 1
    assert summary["fixture_checks"]["passed"] == 1
    assert before["status"] == "scored"
    assert mutable != before


def test_structural_plan_on_report_is_fixture_not_final_plan() -> None:
    slot = {
        "status": "observed",
        "observation": {"evidence_class": FAKE},
        "report": _plan_body(True),
    }
    result = summarize_evaluation([slot])
    assert result["fixture_checks"]["passed"] == 1
    assert result["fixture_checks"]["outside_scope"] == 0
    assert result["final_plan_checks"]["passed"] == 0
    assert result["final_plan_checks"]["outside_scope"] == 1
    assert result["execution_counts"]["observed"] == 1


def test_marker_fields_do_not_leak() -> None:
    slot = _controlled_slot()
    slot["structural_assessment"] = _plan_body(
        True,
        answer="MARKER_ANSWER",
        metadata={"case_id": "F01"},
        case_id="F01",
    )
    result = summarize_evaluation([slot, _fixture_slot()])
    _assert_honest(result)
    assert result["controlled_checks"]["passed"] == 1
    assert result["final_plan_checks"]["passed"] == 1
    assert "case_id" not in result
    assert "answer" not in result
    assert "metadata" not in result
    assert "checks" not in result


def test_structural_assessment_producer_slots() -> None:
    passed = _observed_slot(plan=_plan_body(True, case_id="F01"))
    failed = _observed_slot(plan=_plan_body(False, case_id="X04"))
    alias = {
        "status": "observed",
        "report": None,
        "observation": {"evidence_class": FAKE},
        "model_score": _plan_body(True, case_id="F02"),
    }
    result = summarize_evaluation([passed, failed, alias])
    assert result["final_plan_checks"] == {
        "assessed": 2,
        "passed": 1,
        "failed": 1,
        "invalid": 0,
        "outside_scope": 1,
    }
    assert result["fixture_checks"]["outside_scope"] == 3
    assert result["controlled_checks"]["outside_scope"] == 3
    observation = _mapping(
        _mapping(result["evidence_breakdown"], "evidence")["observation"],
        "observation",
    )
    assert observation == {FAKE: 3, REAL: 0, UNKNOWN: 0}


def test_unhashable_evidence_labels_do_not_raise() -> None:
    fixture_list = {
        "status": "scored",
        "report": {"checks": {"accepted": True}, "evidence_class": []},
    }
    fixture_map = {
        "status": "scored",
        "report": {"checks": {"accepted": True}, "evidence_class": {}},
    }
    observed_list = {
        "status": "observed",
        "observation": {"evidence_class": []},
    }
    observed_map = {
        "status": "observed",
        "observation": {"evidence_class": {}},
    }
    result = summarize_evaluation(
        [fixture_list, fixture_map, observed_list, observed_map]
    )
    assert result["fixture_checks"]["invalid"] == 2
    assert result["fixture_checks"]["passed"] == 0
    assert result["final_plan_checks"]["outside_scope"] == 4
    observation = _mapping(
        _mapping(result["evidence_breakdown"], "evidence")["observation"],
        "observation",
    )
    assert observation == {FAKE: 0, REAL: 0, UNKNOWN: 2}


def test_unassessed_structural_status_is_outside_scope() -> None:
    skipped = _observed_slot(
        plan=_plan_body(False, status="unassessed", passed=False),
    )
    result = summarize_evaluation([skipped])
    assert result["final_plan_checks"] == {
        "assessed": 0,
        "passed": 0,
        "failed": 0,
        "invalid": 0,
        "outside_scope": 1,
    }
    assert result["execution_counts"]["observed"] == 1


def test_unknown_observation_label_count() -> None:
    slots = [
        _fixture_slot(),
        _unassessed_slot(),
        _observed_slot(evidence=FAKE),
        {"status": "observed", "observation": {}},
        {
            "status": "observed",
            "observation": {"evidence_class": "deployed_aws"},
        },
        {"status": "failed", "observation": None},
    ]
    result = summarize_evaluation(slots)
    observation = _mapping(
        _mapping(result["evidence_breakdown"], "evidence")["observation"],
        "observation",
    )
    assert observation == {FAKE: 1, REAL: 0, UNKNOWN: 3}
    assert result["execution_counts"]["scored"] == 1
    assert result["execution_counts"]["unassessed"] == 1
    assert result["fixture_checks"]["passed"] == 1
    assert result["fixture_checks"]["outside_scope"] == 5
