from copy import deepcopy
from typing import cast

import pytest
from test_evaluation_markdown_data import _assess, _slot

from app.evaluation_markdown_format import cell
from app.evaluation_markdown_sections import render_quality
from app.evaluation_summary import summarize_evaluation
from app.evaluation_summary_metrics import summarize_metrics

_ERROR = "^Invalid evaluation quality section input$"


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _groups(summary: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], summary["groups"])


def _summary(slots: list[dict[str, object]]) -> dict[str, object]:
    return summarize_evaluation(slots)


def _row(*values: object) -> str:
    return "| " + " | ".join(cell(value) for value in values) + " |"


def test_helper_groups_keep_conditions_and_evidence_separate() -> None:
    slots = [
        _slot(),
        _slot(evidence="deterministic_fake_provider", repeat=2),
        _slot(condition="no_tool"),
    ]
    _assess(slots[2])
    original = deepcopy(slots)
    summary = _summary(slots)
    original_summary = deepcopy(summary)
    output = render_quality(summary)
    assert output.count("### ") == 3
    for group in _groups(summary):
        heading = f"### {cell(group['condition'])} / {cell(group['evidence_class'])}"
        assert heading in output
        quality = _map(_map(group["tasks"])["quality"])
        assert cell(quality["scope"]) in output
    assert _row("1/1", "1/1", 0, 0, 0) in output
    assert slots == original
    assert summary == original_summary


def test_task_conservative_and_assessed_fractions_show_exact_counts() -> None:
    slots = [_slot(condition="no_tool", repeat=index) for index in (1, 2, 3)]
    for slot in slots[:2]:
        _assess(slot)
    _map(_map(slots[1]["assessments"])["outcome"])["status"] = "failed"
    output = render_quality(_summary(slots))
    assert _row("1/3", "1/2", 1, 1, 0) in output
    assert _row("Plan", "2/2", 1) in output
    assert _row("Outcome", "1/2", 1) in output
    assert _row("Fixture", "0/0 (unassessed)", 0) in output


def test_tools_and_public_claims_show_measured_counts_and_unknowns() -> None:
    measured, missing = _slot(), _slot(repeat=2)
    _assess(measured)
    assessments = _map(measured["assessments"])
    tools: dict[str, object] = {"status": "failed"}
    for key, numerator, denominator in (
        ("valid_calls", 4, 4),
        ("expected_tool_selection", 1, 2),
        ("expected_arguments", 3, 3),
        ("unnecessary_calls", 1, 5),
    ):
        tools[key] = {
            "status": "passed" if numerator == denominator else "failed",
            "numerator": numerator,
            "denominator": denominator,
        }
    assessments["tools"] = tools
    _map(assessments["claims"]).update(
        status="failed",
        supported_count=2,
        assessed_count=3,
        unsupported_count=1,
        unknown_count=4,
        supported_refusal_count=2,
    )
    output = render_quality(_summary([measured, missing]))
    assert _row("Valid calls", "4/4", 1) in output
    assert _row("Expected tool selection", "1/2", 1) in output
    assert _row("Expected arguments", "3/3", 1) in output
    assert _row("Unnecessary calls (lower is better)", "1/5", 1) in output
    assert _row("2/3", "2/7", 4, 1, 2) in output


def test_clarification_correctness_has_assessed_and_unassessed_counts() -> None:
    slots = [_slot(condition="no_tool", repeat=index) for index in (1, 2, 3)]
    for slot, correct in zip(slots, (True, False, None), strict=True):
        _assess(slot)
        status = "unassessed" if correct is None else "passed" if correct else "failed"
        _map(_map(slot["assessments"])["outcome"]).update(
            clarification_required=True,
            clarification_correct=correct,
            status=status,
        )
    output = render_quality(_summary(slots))
    assert _row("Clarification correctness", "1/2", 1) in output


def test_fixture_assessment_counts_use_the_metrics_helper() -> None:
    summary = _summary(
        [
            _slot(evidence="deterministic_fake_provider", repeat=index)
            for index in (1, 2)
        ]
    )
    fixture_slots: list[dict[str, object]] = [
        {
            "driver": "fixture",
            "condition": "deterministic_fixture",
            "case_id": "A02",
            "repeat": index,
            "assessments": {"fixture": {"status": status}},
        }
        for index, status in ((1, "failed"), (2, "unassessed"))
    ]
    fixture = _map(summarize_metrics(fixture_slots)["assessments"])["fixture"]
    metrics = _map(_groups(summary)[0]["metrics"])
    _map(metrics["assessments"])["fixture"] = fixture
    assert _row("Fixture", "0/1", 1) in render_quality(summary)


def test_zero_denominators_and_empty_groups_never_claim_success() -> None:
    output = render_quality(_summary([_slot()]))
    assert cell("0/0 (unassessed)") in output
    assert _row("Valid calls", "0/0 (unassessed)", 1) in output
    assert _row("0/0 (unassessed)", "0/0 (unassessed)", 0, 0, 0) in output
    assert "100%" not in output
    assert "target" not in output.lower()
    assert render_quality(None) == "## Quality\n\nMetrics unavailable."
    empty = render_quality(summarize_evaluation([]))
    assert empty == "## Quality\n\nMetrics unassessed."


def test_zero_claim_denominators_preserve_supported_refusals() -> None:
    slot = _slot(condition="no_tool")
    _assess(slot)
    _map(_map(slot["assessments"])["claims"]).update(
        supported_count=0, assessed_count=0, supported_refusal_count=2
    )
    output = render_quality(_summary([slot]))
    assert _row("0/0 (unassessed)", "0/0 (unassessed)", 0, 0, 2) in output


def test_dynamic_labels_are_escaped_bounded_and_other_fields_are_ignored() -> None:
    summary = _summary([_slot()])
    group = _groups(summary)[0]
    label = "|<script>[link](https://example.org)\n\u202e" + "x" * 400
    group.update(condition=label, evidence_class=label, answer=object())
    quality = _map(_map(group["tasks"])["quality"])
    quality["scope"] = label
    metrics = _map(group["metrics"])
    metrics.update(known_failures=object(), reasons=object(), telemetry=object())
    summary.update(metadata=object(), cost=object(), failures=object())
    output = render_quality(summary)
    assert output.count(cell(label)) == 3
    assert len(cell(label)) <= 256
    assert "<script>" not in output
    assert "\u202e" not in output
    assert "x" * 300 not in output
    assert "object at" not in output


@pytest.mark.parametrize("value", [True, [], "PRIVATE_INPUT", 3])
def test_invalid_summary_types_use_static_errors(value: object) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        render_quality(cast(dict[str, object], value))


@pytest.mark.parametrize(
    "path",
    [
        ("groups",),
        ("total_slots",),
        ("groups", 0, "condition"),
        ("groups", 0, "slot_count"),
        ("groups", 0, "tasks", "quality", "scope"),
        ("groups", 0, "tasks", "quality", "passed"),
        ("groups", 0, "metrics", "tool_metrics", "valid_calls", "counts", "numerator"),
        ("groups", 0, "metrics", "assessments", "claims", "counts", "unknown_count"),
        ("groups", 0, "metrics", "assessments", "plan", "status_counts", "passed"),
        ("groups", 0, "metrics", "clarification_correctness", "denominator"),
    ],
)
@pytest.mark.parametrize("value", [None, True, -1, {}])
def test_malformed_sections_use_static_errors_without_mutation(
    path: tuple[str | int, ...], value: object
) -> None:
    summary = _summary([_slot()])
    parent: object = summary
    for key in path[:-1]:
        if isinstance(key, int):
            parent = cast(list[object], parent)[key]
        else:
            parent = _map(parent)[key]
    _map(parent)[cast(str, path[-1])] = value
    original = deepcopy(summary)
    with pytest.raises(ValueError, match=_ERROR):
        render_quality(summary)
    assert summary == original


def test_inconsistent_counts_and_missing_fields_use_static_errors() -> None:
    for key in ("all_applicable", "assessed_denominator", "passed"):
        summary = _summary([_slot()])
        quality = _map(_map(_groups(summary)[0]["tasks"])["quality"])
        quality[key] = 99
        with pytest.raises(ValueError, match=_ERROR):
            render_quality(summary)
    summary = _summary([_slot()])
    del _map(_groups(summary)[0]["metrics"])["tool_metrics"]
    with pytest.raises(ValueError, match=_ERROR):
        render_quality(summary)


def test_raw_count_strings_are_rejected_with_static_errors() -> None:
    summary = _summary([_slot()])
    quality = _map(_map(_groups(summary)[0]["tasks"])["quality"])
    quality["passed"] = "PRIVATE_COUNT"
    original = deepcopy(summary)
    with pytest.raises(ValueError, match=_ERROR):
        render_quality(summary)
    assert summary == original
