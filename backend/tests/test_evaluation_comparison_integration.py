from __future__ import annotations

import json
import re
from typing import cast

import pytest

from app.agent.provider import LLMProvider
from app.evaluation_markdown import render_evaluation_markdown
from app.evaluation_report_values import INVALID as REPORT_INVALID
from app.evaluation_summary import FAKE, REAL, summarize_evaluation
from tests.test_evaluation_batch import (
    EVIDENCE,
    OBSERVED_COUNT,
    PLAN_IDS,
    SCORED_COUNT,
    UNASSESSED_COUNT,
    ScriptedProvider,
    _factory,
    _mapping,
    _run,
    _slots,
    load_corpus,
)
from tests.test_evaluation_markdown import _checks, _render, _summary, _telemetry

SECRET = "do-not-echo-raw-input"
SCOPE = "deterministic_reference_final_plan"
CONDITION = "deterministic_structured_input"
REFERENCE_NOTE = (
    "Structured-reference checks use structured inputs. "
    "They compare the final result only. "
    "They do not measure language understanding or earlier-turn quality."
)
ZEROS = {
    "assessed": 0,
    "passed": 0,
    "failed": 0,
    "invalid": 0,
    "outside_scope": 0,
}


def _ref(ok: bool, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "scope": SCOPE,
        "condition": CONDITION,
        "status": "passed" if ok else "failed",
        "passed": ok,
        "checks": {"plan_accepted": ok, "final_status": True},
        "evidence_class": FAKE,
        "metrics_status": "unassessed",
    }
    body.update(overrides)
    return body


def _slot(
    *,
    status: str = "observed",
    comparison: dict[str, object] | None = None,
    missing: bool = False,
    evidence: str = FAKE,
) -> dict[str, object]:
    slot: dict[str, object] = {
        "status": status,
        "report": None,
        "observation": {"evidence_class": evidence},
    }
    if not missing:
        slot["reference_comparison"] = _ref(True) if comparison is None else comparison
    return slot


def test_observed_batch_attaches_reference_without_extra_calls() -> None:
    providers, factory = _factory()
    events: list[dict[str, object]] = []
    result = _run(load_corpus(), factory, on_slot=events.append)
    slots = _slots(result)
    scored = [slot for slot in slots if slot["status"] == "scored"]
    observed = [slot for slot in slots if slot["status"] == "observed"]
    unassessed = [slot for slot in slots if slot["status"] == "unassessed"]
    assert len(slots) == 90
    assert len(events) == 90
    assert len(scored) == SCORED_COUNT
    assert len(observed) == OBSERVED_COUNT
    assert len(unassessed) == UNASSESSED_COUNT
    assert len(providers) == OBSERVED_COUNT
    assert len({id(item) for item in providers}) == OBSERVED_COUNT
    planned = 0
    for slot, event in zip(slots, events, strict=True):
        case_id = slot["case_id"]
        if slot["status"] == "scored":
            assert "observation" not in slot
            assert "reference_comparison" not in slot
            assert "reference_comparison" not in event
            continue
        if slot["status"] == "unassessed":
            assert "observation" not in slot
            assert "reference_comparison" not in slot
            continue
        if case_id not in PLAN_IDS:
            assert "reference_comparison" not in slot
            assert "reference_comparison" not in event
            continue
        planned += 1
        report = _mapping(slot["reference_comparison"], "reference_comparison")
        assert report == event["reference_comparison"]
        assert report["scope"] == SCOPE
        assert report["condition"] == CONDITION
        assert report["metrics_status"] == "unassessed"
        assert report["evidence_class"] == EVIDENCE
        assert type(report["passed"]) is bool
        assert "structural_assessment" in slot
    assert planned == 15
    summary = summarize_evaluation(slots)
    assert summary["execution_counts"]["scored"] == SCORED_COUNT
    assert summary["reference_checks"]["assessed"] == 15
    assert summary["reference_checks"]["outside_scope"] == 75
    assert summary["metrics_status"] == "unassessed"


def test_failed_observation_keeps_failed_status_and_comparison_must_not_pass() -> None:
    providers: list[ScriptedProvider] = []
    calls = 0
    events: list[dict[str, object]] = []

    def make() -> LLMProvider:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(SECRET)
        provider = ScriptedProvider()
        providers.append(provider)
        return provider

    result = _run(load_corpus(), make, on_slot=events.append)
    slots = _slots(result)
    failed = [slot for slot in slots if slot["status"] == "failed"]
    observed = [slot for slot in slots if slot["status"] == "observed"]
    assert calls == OBSERVED_COUNT
    assert len(providers) == OBSERVED_COUNT - 1
    assert len(failed) == 1
    assert len(observed) == OBSERVED_COUNT - 1
    assert len([slot for slot in slots if slot["status"] == "scored"]) == SCORED_COUNT
    first = failed[0]
    event = [item for item in events if item["status"] == "failed"][0]
    assert first["case_id"] == "F01"
    assert first["repeat"] == 1
    observation = _mapping(first["observation"], "observation")
    assert observation["status"] == "failed"
    report = _mapping(first["reference_comparison"], "reference_comparison")
    assert report == event["reference_comparison"]
    assert report["passed"] is False
    assert report["status"] != "passed"
    blob = json.dumps(result, default=str)
    assert SECRET not in blob


def test_summary_classifies_pass_fail_unassessed_missing_and_malformed() -> None:
    passed = _slot()
    failed = _slot(comparison=_ref(False))
    skipped = _slot(
        comparison=_ref(
            False,
            status="unassessed",
            passed=False,
            checks={"supported_case": False},
        )
    )
    missing = _slot(missing=True)
    bad_condition = _slot(comparison=_ref(True, condition="language_understanding"))
    missing_condition = _slot()
    del cast(dict[str, object], missing_condition["reference_comparison"])["condition"]
    bad_scope = _slot(comparison=_ref(True, scope="structural_plan"))
    bad_evidence = _slot(comparison=_ref(True, evidence_class="deployed_aws"))
    bad_checks = _slot(comparison=_ref(True, checks={"plan_accepted": 1}))
    real = _slot(comparison=_ref(True, evidence_class=REAL), evidence=REAL)
    result = summarize_evaluation(
        [
            passed,
            failed,
            skipped,
            missing,
            bad_condition,
            missing_condition,
            bad_scope,
            bad_evidence,
            bad_checks,
            real,
        ]
    )
    assert result["reference_checks"] == {
        "assessed": 3,
        "passed": 2,
        "failed": 1,
        "invalid": 5,
        "outside_scope": 2,
    }
    assert result["final_plan_checks"] == {
        **ZEROS,
        "outside_scope": 10,
    }
    assert result["metrics_status"] == "unassessed"
    assert "pass_rate" not in result
    assert "success_rate" not in result


def test_summary_malformed_slot_and_empty_input_count_reference_group() -> None:
    empty = summarize_evaluation([])
    assert empty["reference_checks"] == ZEROS
    result = summarize_evaluation([_slot(), "bad", 1])
    assert result["execution_counts"]["invalid"] == 2
    assert result["reference_checks"] == {
        "assessed": 1,
        "passed": 1,
        "failed": 0,
        "invalid": 2,
        "outside_scope": 0,
    }


def test_markdown_omits_structured_reference_without_group() -> None:
    text = _render()
    assert "| fixture | 0 | 0 | 0 | 0 | 0 |" in text
    assert "| control | 0 | 0 | 0 | 0 | 0 |" in text
    assert "| final-plan | 0 | 0 | 0 | 0 | 0 |" in text
    assert "structured-reference" not in text
    assert REFERENCE_NOTE not in text
    assert "FIXTURE_SECRET_MARKER" not in text
    assert "input_tokens: unknown" in text
    assert "Latency sums user-turn elapsed times for each observation." in text


def test_markdown_adds_structured_reference_row_and_static_note() -> None:
    injected = "language understanding score from scope_note"
    text = _render(
        _summary(
            reference_checks=_checks(assessed=3, passed=2, failed=1),
            scope_note=injected,
            compare=injected,
        )
    )
    assert "| structured-reference | 3 | 2 | 1 | 0 | 0 |" in text
    assert REFERENCE_NOTE in text
    assert injected not in text
    assert "FIXTURE_SECRET_MARKER" not in text
    assert "input_tokens: unknown" in text
    assert "p50: unknown" in text


def test_markdown_rejects_malformed_reference_group() -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(REPORT_INVALID)}$") as caught:
        render_evaluation_markdown(
            _summary(reference_checks={"assessed": 1, "passed": 1}),
            _telemetry(),
            revision="0123456789abcdef0123456789abcdef01234567",
            model_id="eval-fake-v1",
            source_region="us-east-1",
        )
    assert str(caught.value) == REPORT_INVALID
