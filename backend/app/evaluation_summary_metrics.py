from typing import cast

from app.evaluation_metric_counts import (
    sum_binary_metrics,
    sum_claim_counts,
    summarize_assessment_statuses,
)
from app.evaluation_summary_check_records import failure_record, validate_checks

_STATUSES = ("passed", "failed", "unassessed", "not_applicable")
_TOOLS = (
    "valid_calls",
    "expected_tool_selection",
    "expected_arguments",
    "unnecessary_calls",
)
_CLAIMS = tuple(key for key in sum_claim_counts([]) if key.endswith("_count"))
AssessmentRows = list[dict[str, object]]


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid evaluation metrics")


def _map(value: object) -> dict[str, object]:
    _require(type(value) is dict and all(type(key) is str for key in value))
    return cast(dict[str, object], value)


def _status(row: dict[str, object]) -> str:
    status = row.get("status", "unassessed")
    _require(type(status) is str and status in _STATUSES)
    return cast(str, status)


def _aggregate(rows: AssessmentRows, fields: tuple[str, ...] = ()) -> dict[str, object]:
    statuses = summarize_assessment_statuses([_status(row) for row in rows])
    summer = sum_claim_counts if fields == _CLAIMS else sum_binary_metrics
    measured: AssessmentRows = []
    for row in rows if fields else []:
        status = _status(row)
        if status not in ("passed", "failed") and not any(key in row for key in fields):
            continue
        try:
            summer([row])
        except ValueError:
            raise ValueError("invalid evaluation metrics") from None
        if status == "not_applicable":
            if fields != _CLAIMS:
                continue
            row = {**row, **dict.fromkeys(_CLAIMS[:-1], 0)}
        measured.append(row)
    totals = summer(measured) if fields else {}
    return {
        "status_counts": {key: statuses[key] for key in _STATUSES},
        "denominator": statuses["denominator"],
        "pass_rate": statuses["pass_rate"],
        "counts": {key: totals[key] for key in fields},
        **{key: value for key, value in totals.items() if key not in fields},
    }


def summarize_metrics(slots: list[dict[str, object]]) -> dict[str, object]:
    _require(type(slots) is list)
    rows: dict[str, AssessmentRows] = {
        name: [] for name in ("tools", "plan", "outcome", "claims", "fixture")
    }
    tools: dict[str, AssessmentRows] = {key: [] for key in _TOOLS}
    checks: dict[str, dict[str, AssessmentRows]] = {name: {} for name in rows}
    clarification: AssessmentRows = []
    failures: list[dict[str, object]] = []
    for slot in slots:
        slot = _map(slot)
        driver = slot.get("driver")
        raw = _map(slot.get("assessments", {}))
        for name in rows:
            relevant = driver in ("model", "no_tool") and name != "fixture"
            relevant &= name != "tools" or driver == "model"
            relevant |= name == "plan" and driver == "reference"
            relevant |= name == "fixture" and slot.get("condition") in (
                "deterministic_fixture",
                "controlled_fixture",
            )
            data = _map(raw.get(name, {}) if relevant else {"status": "not_applicable"})
            rows[name].append(data)
            relevant &= _status(data) != "not_applicable"
            try:
                named = validate_checks(data.get("checks", {})) if relevant else {}
            except ValueError:
                raise ValueError("invalid evaluation metrics") from None
            if name == "fixture" and relevant and data.get("status") == "passed":
                _require(bool(named))
            failed_checks = [key for key, passed in named.items() if not passed]
            for key, passed in named.items():
                check_status = "passed" if passed else "failed"
                checks[name].setdefault(key, []).append({"status": check_status})
            if name == "tools":
                for key in tools:
                    metric = _map(data.get(key, {}))
                    _status(metric)
                    if not relevant:
                        metric = {**metric, "status": "not_applicable"}
                    tools[key].append(metric)
                    if metric.get("status") == "failed":
                        failed_checks.append(key)
            _require(data.get("status") != "passed" or not failed_checks)
            if data.get("status") == "failed" or failed_checks:
                try:
                    failure = failure_record(
                        cast(str, slot.get("case_id")),
                        cast(int, slot.get("repeat")),
                        name,
                        failed_checks,
                    )
                except ValueError:
                    raise ValueError("invalid evaluation metrics") from None
                failures.append(failure)
            if name == "claims" and relevant and data:
                _require(data.get("scope") == "public_output_only")
            if name == "outcome":
                required = data.get("clarification_required")
                correct = data.get("clarification_correct")
                for value in (required, correct):
                    _require(value is None or type(value) is bool)
                status = "unassessed"
                if not relevant or required is False:
                    status = "not_applicable"
                if relevant and required is True and correct is not None:
                    status = "passed" if correct else "failed"
                clarification.append({"status": status})
    result = {name: _aggregate(items) for name, items in rows.items()}
    result["claims"] = _aggregate(rows["claims"], _CLAIMS)
    tool_metrics = {
        key: _aggregate(items, ("numerator", "denominator"))
        for key, items in tools.items()
    }
    tool_metrics["unnecessary_calls"]["direction"] = "lower_is_better"
    return {
        "assessments": result,
        "tool_metrics": tool_metrics,
        "plan_checks": {
            key: _aggregate(items) for key, items in checks["plan"].items()
        },
        "fixture_checks": {
            key: _aggregate(items) for key, items in checks["fixture"].items()
        },
        "clarification_correctness": _aggregate(clarification),
        "known_failures": failures,
    }
