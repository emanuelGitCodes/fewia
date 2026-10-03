from __future__ import annotations

_STATUSES = ("passed", "failed", "unassessed", "not_applicable")
_STATUS_ERROR = (
    "assessment status MUST be passed, failed, unassessed, or not_applicable"
)
_COUNT_ERROR = "metric counts MUST be nonnegative integers with coherent totals"
_CLAIM_FIELDS = (
    "supported_count",
    "assessed_count",
    "unsupported_count",
    "unknown_count",
    "supported_refusal_count",
)


def _count(record: dict[str, object], field: str) -> int:
    if type(record) is not dict:
        raise ValueError(_COUNT_ERROR)
    value = record.get(field)
    if type(value) is not int or value < 0:
        raise ValueError(_COUNT_ERROR)
    return value


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize_assessment_statuses(statuses: list[object]) -> dict[str, object]:
    """Count supplied assessment statuses and return the assessed pass rate."""
    counts = dict.fromkeys(_STATUSES, 0)
    for status in statuses:
        if type(status) is not str or status not in _STATUSES:
            raise ValueError(_STATUS_ERROR)
        counts[status] += 1
    numerator = counts["passed"]
    denominator = numerator + counts["failed"]
    return {
        **counts,
        "numerator": numerator,
        "denominator": denominator,
        "pass_rate": _rate(numerator, denominator),
    }


def sum_binary_metrics(metrics: list[dict[str, object]]) -> dict[str, object]:
    """Sum validated counts and return their combined rate."""
    numerator = 0
    denominator = 0
    for metric in metrics:
        record_numerator = _count(metric, "numerator")
        record_denominator = _count(metric, "denominator")
        if record_numerator > record_denominator:
            raise ValueError(_COUNT_ERROR)
        numerator += record_numerator
        denominator += record_denominator
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": _rate(numerator, denominator),
    }


def sum_claim_counts(claims: list[dict[str, object]]) -> dict[str, object]:
    """Sum public factual counts and keep supported refusals separate."""
    totals = dict.fromkeys(_CLAIM_FIELDS, 0)
    for claim in claims:
        counts = {field: _count(claim, field) for field in _CLAIM_FIELDS}
        scope = claim.get("scope")
        if type(scope) is not str or scope != "public_output_only":
            raise ValueError(_COUNT_ERROR)
        if (
            counts["supported_count"] + counts["unsupported_count"]
            != counts["assessed_count"]
        ):
            raise ValueError(_COUNT_ERROR)
        for field in _CLAIM_FIELDS:
            totals[field] += counts[field]
    supported = totals["supported_count"]
    assessed = totals["assessed_count"]
    return {
        **totals,
        "scope": "public_output_only",
        "support_rate": _rate(supported, assessed),
        "conservative_support_rate": _rate(
            supported, assessed + totals["unknown_count"]
        ),
    }
