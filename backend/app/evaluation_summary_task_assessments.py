from __future__ import annotations

from typing import cast

from app.evaluation_metric_counts import sum_claim_counts

_STATUSES = ("passed", "failed", "unassessed", "not_applicable")
_KINDS = ("fixture", "tools", "plan", "outcome", "claims")
_CLAIM_FIELDS = (
    "assessed_count",
    "supported_count",
    "unsupported_count",
    "unknown_count",
    "supported_refusal_count",
)
_METRICS = (
    "valid_calls",
    "expected_tool_selection",
    "expected_arguments",
    "unnecessary_calls",
)


def _status(value: object) -> str:
    return value if type(value) is str and value in _STATUSES else "unassessed"


def combine_statuses(statuses: list[str]) -> str:
    if type(statuses) is not list:
        return "unassessed"
    normalized = [_status(status) for status in statuses]
    if "failed" in normalized:
        return "failed"
    if not normalized or "unassessed" in normalized:
        return "unassessed"
    return "passed" if "passed" in normalized else "not_applicable"


def _checks(value: object) -> str:
    if type(value) is not dict:
        return "unassessed"
    checks = cast(dict[object, object], value)
    if any(check is False for check in checks.values()):
        return "failed"
    valid = all(
        type(key) is str and type(check) is bool for key, check in checks.items()
    )
    return "passed" if valid else "unassessed"


def _metric(value: object, name: str) -> str:
    if type(value) is not dict:
        return "unassessed"
    metric = cast(dict[str, object], value)
    status = _status(metric.get("status"))
    if status == "failed":
        return "failed"
    numerator, denominator = metric.get("numerator"), metric.get("denominator")
    valid = (
        type(numerator) is int
        and type(denominator) is int
        and 0 <= numerator <= denominator
    )
    if valid and numerator != (0 if name == "unnecessary_calls" else denominator):
        return "failed"
    if any(type(key) is not str for key in metric):
        return "unassessed"
    if status == "not_applicable":
        if valid or not ("numerator" in metric or "denominator" in metric):
            return status
    return "passed" if valid and status == "passed" else "unassessed"


def _claims(record: dict[str, object], status: str) -> str:
    unsupported = record.get("unsupported_count")
    if type(unsupported) is int and unsupported > 0:
        return "failed"
    if status == "not_applicable" and not any(key in record for key in _CLAIM_FIELDS):
        return "passed"
    try:
        counts = sum_claim_counts([record])
    except ValueError:
        return "unassessed"
    return "unassessed" if counts["unknown_count"] != 0 else "passed"


def assessment_status(value: object, kind: str) -> str:
    if type(kind) is not str or kind not in _KINDS:
        raise ValueError("unknown assessment kind")
    if type(value) is not dict:
        return "unassessed"
    record = cast(dict[str, object], value)
    status = _status(record.get("status"))
    results = [status]
    if any(type(key) is not str for key in record):
        results.append("unassessed")
    if "checks" in record:
        results.append(_checks(record["checks"]))
    if kind == "fixture":
        if type(record.get("checks")) is not dict or not record["checks"]:
            results.append("unassessed")
    elif kind == "tools":
        metrics = [_metric(record.get(name), name) for name in _METRICS]
        if (
            type(record.get("status")) is str
            and record.get("status") in ("unassessed", "not_applicable")
            and metrics == ["not_applicable"] * len(_METRICS)
        ):
            results[0] = "not_applicable"
        else:
            if status == "not_applicable":
                results[0] = "unassessed"
            metrics = ["unassessed" if m == "not_applicable" else m for m in metrics]
        results.extend(metrics)
    elif kind == "plan":
        violations = record.get("constraint_violations")
        if type(violations) is list and all(
            type(item) is str for item in cast(list[object], violations)
        ):
            results.append("failed" if violations else "passed")
        elif not (status == "not_applicable" and "constraint_violations" not in record):
            results.append("unassessed")
    elif kind == "outcome":
        required = record.get("clarification_required")
        correct = record.get("clarification_correct")
        if required is True and correct is not True:
            results.append("failed")
        elif (
            type(required) is not bool
            or "clarification_correct" not in record
            or (correct is not None and type(correct) is not bool)
        ):
            results.append("unassessed")
    else:
        results.append(_claims(record, status))
    scopes = {
        "plan": "final_plan",
        "outcome": "final_turn",
        "claims": "public_output_only",
    }
    if kind in scopes:
        scope = record.get("scope")
        if type(scope) is not str or scope != scopes[kind]:
            results.append("unassessed")
    if status == "not_applicable" and kind not in ("tools", "plan", "claims"):
        results.append("unassessed")
    combined = combine_statuses(results)
    if combined == "passed" and results[0] == "not_applicable":
        return "not_applicable"
    return combined
