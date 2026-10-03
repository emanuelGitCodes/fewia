from typing import cast

from app.evaluation_markdown_format import cell, table
from app.evaluation_markdown_values import as_map, require, slots

_ERROR = "Invalid evaluation quality section input"
_STATUSES = "passed failed unassessed not_applicable"
_TOOLS = (
    ("valid_calls", "Valid calls"),
    ("expected_tool_selection", "Expected tool selection"),
    ("expected_arguments", "Expected arguments"),
    ("unnecessary_calls", "Unnecessary calls (lower is better)"),
)


def _count(source: dict[str, object], key: str) -> int:
    value = source[key]
    require(type(value) is int and value >= 0)
    return cast(int, value)


def _label(value: object) -> str:
    require(type(value) is str and bool(value))
    return cell(value)


def _fraction(numerator: int, denominator: int) -> str:
    require(numerator <= denominator)
    suffix = " (unassessed)" if denominator == 0 else ""
    return f"{numerator}/{denominator}{suffix}"


def _statuses(source: dict[str, object]) -> dict[str, int]:
    return {key: _count(source, key) for key in _STATUSES.split()}


def _assessment(label: str, value: object) -> tuple[object, ...]:
    assessment = as_map(value)
    counts = _statuses(as_map(assessment["status_counts"]))
    assessed = counts["passed"] + counts["failed"]
    require(_count(assessment, "denominator") == assessed)
    return label, _fraction(counts["passed"], assessed), counts["unassessed"]


def _group(group: dict[str, object]) -> str:
    condition = _label(group["condition"])
    evidence = _label(group["evidence_class"])
    quality = as_map(as_map(group["tasks"])["quality"])
    scope = quality["scope"]
    _label(scope)
    counts = _statuses(quality)
    require(sum(counts.values()) == _count(group, "slot_count"))
    applicable = _count(quality, "all_applicable")
    assessed = _count(quality, "assessed_denominator")
    require(applicable == counts["passed"] + counts["failed"] + counts["unassessed"])
    require(assessed == counts["passed"] + counts["failed"])
    task_table = table(
        (
            "Task passed/applicable",
            "Task passed/assessed",
            "Failed",
            "Unassessed",
            "Not applicable",
            "Quality scope",
        ),
        [
            (
                _fraction(counts["passed"], applicable),
                _fraction(counts["passed"], assessed),
                counts["failed"],
                counts["unassessed"],
                counts["not_applicable"],
                scope,
            )
        ],
    )
    metrics = as_map(group["metrics"])
    tools = as_map(metrics["tool_metrics"])
    tool_rows: list[tuple[object, ...]] = []
    for key, label in _TOOLS:
        metric = as_map(tools[key])
        measured = as_map(metric["counts"])
        unassessed = _statuses(as_map(metric["status_counts"]))["unassessed"]
        numerator = _count(measured, "numerator")
        denominator = _count(measured, "denominator")
        tool_rows.append((label, _fraction(numerator, denominator), unassessed))
    tool_table = table(
        ("Tool metric", "Numerator/denominator", "Unassessed"), tool_rows
    )
    assessments = as_map(metrics["assessments"])
    claims = as_map(as_map(assessments["claims"])["counts"])
    supported = _count(claims, "supported_count")
    claim_assessed = _count(claims, "assessed_count")
    unknown = _count(claims, "unknown_count")
    unsupported = _count(claims, "unsupported_count")
    require(supported + unsupported == claim_assessed)
    claim_table = table(
        (
            "Public claims supported/assessed",
            "Public claims supported/(assessed+unknown)",
            "Unknown",
            "Unsupported",
            "Supported refusals",
        ),
        [
            (
                _fraction(supported, claim_assessed),
                _fraction(supported, claim_assessed + unknown),
                unknown,
                unsupported,
                _count(claims, "supported_refusal_count"),
            )
        ],
    )
    assessment_rows = [
        _assessment(name.capitalize(), assessments[name])
        for name in ("plan", "outcome", "fixture")
    ]
    assessment_rows.append(
        _assessment("Clarification correctness", metrics["clarification_correctness"])
    )
    assessment_table = table(
        ("Assessment", "Passed/assessed", "Unassessed"), assessment_rows
    )
    return "\n\n".join(
        (
            f"### {condition} / {evidence}",
            task_table,
            tool_table,
            claim_table,
            assessment_table,
        )
    )


def render_quality(summary: dict[str, object] | None) -> str:
    if summary is None:
        return "## Quality\n\nMetrics unavailable."
    try:
        summary = as_map(summary)
        groups = slots(summary["groups"])
        total = sum(_count(group, "slot_count") for group in groups)
        require(total == _count(summary, "total_slots"))
        sections = [_group(group) for group in groups]
        return "## Quality\n\n" + "\n\n".join(sections or ["Metrics unassessed."])
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError(_ERROR) from None
