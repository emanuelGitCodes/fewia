from __future__ import annotations

from typing import cast

import pytest

from app.evaluation_summary_task_assessments import assessment_status, combine_statuses

_KINDS = ("fixture", "tools", "plan", "outcome", "claims")
_METRICS = (
    "valid_calls",
    "expected_tool_selection",
    "expected_arguments",
    "unnecessary_calls",
)
_COUNTS = (
    "assessed_count",
    "supported_count",
    "unsupported_count",
    "unknown_count",
    "supported_refusal_count",
)


class DictSubclass(dict[str, object]):
    pass


class StrSubclass(str):
    pass


class IntSubclass(int):
    pass


def _assessment(kind: str) -> dict[str, object]:
    record: dict[str, object] = {"status": "passed"}
    if kind == "fixture":
        record["checks"] = {"matches": True}
    elif kind == "tools":
        record.update(
            {
                name: {"status": "passed", "numerator": 0, "denominator": 0}
                for name in _METRICS
            }
        )
    elif kind == "plan":
        record.update(scope="final_plan", constraint_violations=[])
    elif kind == "outcome":
        record.update(
            scope="final_turn", clarification_required=False, clarification_correct=None
        )
    else:
        record.update({field: 0 for field in _COUNTS})
        record["scope"] = "public_output_only"
    return record


def _not_applicable_tools(status: object = "unassessed") -> dict[str, object]:
    return {
        "status": status,
        **{name: {"status": "not_applicable"} for name in _METRICS},
    }


@pytest.mark.parametrize("kind", _KINDS)
def test_public_assessment_api_passes_valid_evidence(kind: str) -> None:
    assert assessment_status(_assessment(kind), kind) == "passed"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("value", [None, [], "passed", DictSubclass(status="passed")])
def test_assessments_require_exact_mappings(kind: str, value: object) -> None:
    assert assessment_status(value, kind) == "unassessed"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("status", [None, [], True, "unknown", StrSubclass("passed")])
def test_malformed_status_never_passes(kind: str, status: object) -> None:
    record = _assessment(kind)
    record["status"] = status
    assert assessment_status(record, kind) == "unassessed"


@pytest.mark.parametrize("kind", _KINDS)
def test_known_failed_status_overrides_missing_evidence(kind: str) -> None:
    assert assessment_status({"status": "failed", "checks": []}, kind) == "failed"


@pytest.mark.parametrize("kind", ["private model output", "", "PLAN"])
def test_unknown_kind_raises_only_fixed_safe_message(kind: str) -> None:
    with pytest.raises(ValueError) as error:
        assessment_status({"error": "private error text"}, kind)
    assert str(error.value) == "unknown assessment kind"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    "checks",
    [None, [], {"ok": 1}, {7: True}, {StrSubclass("ok"): True}, DictSubclass(ok=True)],
)
def test_present_checks_require_exact_types(kind: str, checks: object) -> None:
    record = _assessment(kind)
    record["checks"] = checks
    assert assessment_status(record, kind) == "unassessed"


@pytest.mark.parametrize("kind", _KINDS)
def test_false_checks_override_malformed_fields_and_keys(kind: str) -> None:
    record: dict[object, object] = {"checks": {7: False, "bad": "false"}, 9: None}
    assert assessment_status(record, kind) == "failed"


@pytest.mark.parametrize("kind", _KINDS)
def test_non_string_assessment_keys_cannot_pass(kind: str) -> None:
    record = cast(dict[object, object], _assessment(kind))
    record[7] = True
    assert assessment_status(record, kind) == "unassessed"
    record["status"] = "failed"
    assert assessment_status(record, kind) == "failed"


@pytest.mark.parametrize("kind", _KINDS)
def test_optional_checks_depend_on_kind(kind: str) -> None:
    record = _assessment(kind)
    record.pop("checks", None)
    expected = "unassessed" if kind == "fixture" else "passed"
    assert assessment_status(record, kind) == expected
    record["checks"] = {}
    assert assessment_status(record, kind) == expected
    record["checks"] = {"ok": True}
    assert assessment_status(record, kind) == "passed"


@pytest.mark.parametrize(
    "kind,scope", [("plan", "final_plan"), ("claims", "public_output_only")]
)
def test_not_applicable_plan_and_claims_require_scope(kind: str, scope: str) -> None:
    record: dict[str, object] = {"status": "not_applicable", "scope": scope}
    assert assessment_status(record, kind) == "not_applicable"
    record["checks"] = {"ok": True}
    assert assessment_status(record, kind) == "not_applicable"
    record["scope"] = "wrong"
    assert assessment_status(record, kind) == "unassessed"
    record["checks"] = {"ok": False}
    assert assessment_status(record, kind) == "failed"


@pytest.mark.parametrize("kind", ["fixture", "tools", "outcome"])
def test_numeric_tools_fixture_and_outcome_reject_not_applicable(kind: str) -> None:
    record = _assessment(kind)
    record["status"] = "not_applicable"
    assert assessment_status(record, kind) == "unassessed"


@pytest.mark.parametrize("violations", [None, (), [1], [StrSubclass("violation")]])
def test_plan_requires_exact_list_of_strings(violations: object) -> None:
    record = _assessment("plan")
    record["constraint_violations"] = violations
    assert assessment_status(record, "plan") == "unassessed"


def test_constraint_failure_overrides_bad_scope_and_checks() -> None:
    record = _assessment("plan")
    record.update(constraint_violations=["budget"], scope=None, checks=[])
    assert assessment_status(record, "plan") == "failed"
    record["status"] = "unassessed"
    assert assessment_status(record, "plan") == "failed"


@pytest.mark.parametrize(
    "required,correct,expected",
    [
        (True, True, "passed"),
        (True, False, "failed"),
        (True, None, "failed"),
        (True, 1, "failed"),
        (False, False, "passed"),
        (False, 1, "unassessed"),
        (1, True, "unassessed"),
    ],
)
def test_outcome_clarification_types_and_behavior(
    required: object, correct: object, expected: str
) -> None:
    record = _assessment("outcome")
    record.update(clarification_required=required, clarification_correct=correct)
    assert assessment_status(record, "outcome") == expected


def test_missing_clarification_evidence_and_failure_precedence() -> None:
    record = _assessment("outcome")
    del record["clarification_correct"]
    assert assessment_status(record, "outcome") == "unassessed"
    record.update(clarification_required=True, scope=None, checks=[])
    assert assessment_status(record, "outcome") == "failed"


@pytest.mark.parametrize("kind", ["plan", "outcome", "claims"])
@pytest.mark.parametrize("scope", [None, "wrong", StrSubclass("final_plan")])
def test_scoped_assessments_reject_invalid_scope(kind: str, scope: object) -> None:
    record = _assessment(kind)
    record["scope"] = scope
    assert assessment_status(record, kind) == "unassessed"


@pytest.mark.parametrize("field", _COUNTS)
@pytest.mark.parametrize("value", [None, -1, True, "0", 0.0, IntSubclass(0)])
def test_claim_counts_require_exact_nonnegative_integers(
    field: str, value: object
) -> None:
    record = _assessment("claims")
    record[field] = value
    assert assessment_status(record, "claims") == "unassessed"


@pytest.mark.parametrize("field", _COUNTS)
def test_claim_count_aliases_do_not_supply_evidence(field: str) -> None:
    record = _assessment("claims")
    record[field.removesuffix("_count")] = record.pop(field)
    assert assessment_status(record, "claims") == "unassessed"


def test_claim_count_coherence_unknown_and_supported_refusals() -> None:
    record = _assessment("claims")
    record["supported_refusal_count"] = 7
    assert assessment_status(record, "claims") == "passed"
    record.update(assessed_count=2, supported_count=2, supported_refusal_count=7)
    assert assessment_status(record, "claims") == "passed"
    record["unknown_count"] = 1
    assert assessment_status(record, "claims") == "unassessed"
    record.update(unknown_count=0, assessed_count=3)
    assert assessment_status(record, "claims") == "unassessed"


def test_unsupported_claim_overrides_other_malformed_counts_and_scope() -> None:
    record: dict[str, object] = {
        "unsupported_count": 1,
        "assessed_count": "private model output",
        "scope": "wrong",
        "checks": [],
    }
    assert assessment_status(record, "claims") == "failed"


@pytest.mark.parametrize(
    "checks,expected",
    [({}, "passed"), ({"ok": False}, "failed"), ({7: True}, "unassessed")],
)
def test_tools_include_top_level_checks(checks: object, expected: str) -> None:
    record = _assessment("tools")
    record["checks"] = checks
    assert assessment_status(record, "tools") == expected


def test_zero_zero_tool_metrics_pass() -> None:
    assert assessment_status(_assessment("tools"), "tools") == "passed"


def test_positive_tool_counts_pass_with_no_unnecessary_calls() -> None:
    record = _assessment("tools")
    record.update(
        {
            name: {
                "status": "passed",
                "numerator": 0 if name == "unnecessary_calls" else 3,
                "denominator": 3,
            }
            for name in _METRICS
        }
    )
    assert assessment_status(record, "tools") == "passed"


@pytest.mark.parametrize("status", ["passed", "unassessed", "not_applicable"])
def test_nested_tool_metrics_cannot_supply_evidence(status: str) -> None:
    flat = _assessment("tools") if status == "passed" else _not_applicable_tools()
    flat.pop("status")
    record: dict[str, object] = {"status": status, "metrics": flat}
    assert assessment_status(record, "tools") == "unassessed"
    flat["valid_calls"] = {"status": "failed"}
    assert assessment_status(record, "tools") == "unassessed"
    record["checks"] = {"ok": False}
    assert assessment_status(record, "tools") == "failed"


def test_non_string_metric_keys_preserve_known_failure() -> None:
    record = _assessment("tools")
    metric = cast(dict[object, object], record["valid_calls"])
    metric[7] = True
    assert assessment_status(record, "tools") == "unassessed"
    metric["status"] = "failed"
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize("name", _METRICS)
@pytest.mark.parametrize(
    "metric,expected",
    [
        (None, "unassessed"),
        (DictSubclass(status="passed", numerator=0, denominator=0), "unassessed"),
        ({"status": "failed"}, "failed"),
        ({"status": "passed", "numerator": True, "denominator": 1}, "unassessed"),
        (
            {"status": "passed", "numerator": IntSubclass(0), "denominator": 0},
            "unassessed",
        ),
        ({"status": "passed", "numerator": 2, "denominator": 1}, "unassessed"),
        ({"status": "passed", "numerator": -1, "denominator": 1}, "unassessed"),
        ({"status": "passed", "numerator": 0, "denominator": "0"}, "unassessed"),
        ({"status": "unknown", "numerator": 0, "denominator": 0}, "unassessed"),
        ({"status": "not_applicable", "numerator": 0, "denominator": 0}, "unassessed"),
        ({"status": "passed", "numerator": 0, "denominator": 0, 7: True}, "unassessed"),
    ],
)
def test_invalid_and_failed_tool_metrics(
    name: str, metric: object, expected: str
) -> None:
    record = _assessment("tools")
    record[name] = metric
    assert assessment_status(record, "tools") == expected


@pytest.mark.parametrize("name", _METRICS)
def test_tool_metric_failure_overrides_missing_and_malformed_evidence(
    name: str,
) -> None:
    numerator = 1 if name == "unnecessary_calls" else 0
    record: dict[str, object] = {
        "status": "unknown",
        "checks": [],
        name: {"status": "passed", "numerator": numerator, "denominator": 1},
    }
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize("name", _METRICS)
def test_tools_require_every_named_metric(name: str) -> None:
    record = _assessment("tools")
    del record[name]
    assert assessment_status(record, "tools") == "unassessed"
    record["valid_calls"] = {"status": "failed"}
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize("status", ["unassessed", "not_applicable"])
@pytest.mark.parametrize(
    "checks",
    [
        {},
        {"ok": True},
        {"case_id": True, "turns_complete": True, "call_shapes": True},
    ],
)
def test_flat_not_applicable_tools_accept_valid_or_absent_checks(
    status: str, checks: object
) -> None:
    record = _not_applicable_tools(status)
    record["checks"] = checks
    assert assessment_status(record, "tools") == "not_applicable"
    del record["checks"]
    assert assessment_status(record, "tools") == "not_applicable"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("passed", "unassessed"),
        ("failed", "failed"),
        (None, "unassessed"),
        ([], "unassessed"),
        (True, "unassessed"),
        ("unknown", "unassessed"),
        (StrSubclass("unassessed"), "unassessed"),
        (StrSubclass("not_applicable"), "unassessed"),
    ],
)
def test_not_applicable_tools_require_valid_top_level_status(
    status: object, expected: str
) -> None:
    record = _not_applicable_tools(status)
    assert assessment_status(record, "tools") == expected
    record["checks"] = {"ok": False}
    assert assessment_status(record, "tools") == "failed"


def test_not_applicable_tools_require_status_and_string_keys() -> None:
    record = _not_applicable_tools()
    del record["status"]
    assert assessment_status(record, "tools") == "unassessed"
    record["status"] = "unassessed"
    malformed = cast(dict[object, object], record)
    malformed[7] = True
    assert assessment_status(malformed, "tools") == "unassessed"


@pytest.mark.parametrize("status", ["unassessed", "not_applicable"])
@pytest.mark.parametrize(
    "checks,expected",
    [
        (None, "unassessed"),
        ([], "unassessed"),
        ({"ok": 1}, "unassessed"),
        ({7: True}, "unassessed"),
        ({StrSubclass("ok"): True}, "unassessed"),
        (DictSubclass(ok=True), "unassessed"),
        ({"ok": False}, "failed"),
        ({7: False, "bad": "false"}, "failed"),
    ],
)
def test_not_applicable_tools_preserve_check_validation_and_failure(
    status: str, checks: object, expected: str
) -> None:
    record = _not_applicable_tools(status)
    record["checks"] = checks
    assert assessment_status(record, "tools") == expected


@pytest.mark.parametrize("name", _METRICS)
def test_not_applicable_tools_require_all_four_flat_metrics(name: str) -> None:
    record = _not_applicable_tools()
    del record[name]
    assert assessment_status(record, "tools") == "unassessed"
    record["valid_calls"] = {"status": "failed"}
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize("status", ["passed", "unassessed", "not_applicable"])
@pytest.mark.parametrize("name", _METRICS)
def test_mixed_not_applicable_and_numeric_tools_are_unassessed(
    status: str, name: str
) -> None:
    record = _not_applicable_tools(status)
    record[name] = {"status": "passed", "numerator": 0, "denominator": 0}
    assert assessment_status(record, "tools") == "unassessed"
    record[name] = {"status": "failed"}
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize("name", _METRICS)
@pytest.mark.parametrize("denominator", [None, 0, 3])
@pytest.mark.parametrize(
    "status,expected",
    [
        ("unassessed", "not_applicable"),
        ("not_applicable", "not_applicable"),
        ("unknown", "unassessed"),
    ],
)
def test_not_applicable_tools_validate_raw_status_and_optional_counts(
    name: str, denominator: int | None, status: str, expected: str
) -> None:
    record = _not_applicable_tools(status)
    metric: dict[str, object] = {"status": "not_applicable", "rate": None}
    if denominator is not None:
        metric.update(
            numerator=0 if name == "unnecessary_calls" else denominator,
            denominator=denominator,
        )
    record[name] = metric
    assert assessment_status(record, "tools") == expected


@pytest.mark.parametrize("name", _METRICS)
@pytest.mark.parametrize("status", ["unassessed", "not_applicable"])
@pytest.mark.parametrize(
    "counts",
    [
        {"numerator": 0},
        {"denominator": 0},
        {"numerator": None, "denominator": 0},
        {"numerator": 0, "denominator": None},
        {"numerator": True, "denominator": 1},
        {"numerator": 0, "denominator": True},
        {"numerator": "0", "denominator": 0},
        {"numerator": 0, "denominator": "0"},
        {"numerator": 0.0, "denominator": 0},
        {"numerator": 0, "denominator": 0.0},
        {"numerator": IntSubclass(0), "denominator": 0},
        {"numerator": 0, "denominator": IntSubclass(0)},
        {"numerator": -1, "denominator": 0},
        {"numerator": 0, "denominator": -1},
        {"numerator": 2, "denominator": 1},
    ],
)
def test_not_applicable_tools_reject_malformed_counts_unless_failed(
    name: str, status: str, counts: dict[str, object]
) -> None:
    record = _not_applicable_tools(status)
    metric: dict[str, object] = {"status": "not_applicable", **counts}
    record[name] = metric
    assert assessment_status(record, "tools") == "unassessed"
    metric["status"] = "failed"
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize("name", _METRICS)
@pytest.mark.parametrize("status", ["unassessed", "not_applicable", None, "unknown"])
def test_not_applicable_metrics_preserve_known_count_failures(
    name: str, status: object
) -> None:
    record = _not_applicable_tools()
    numerator = 1 if name == "unnecessary_calls" else 0
    record[name] = {
        "status": "not_applicable",
        "numerator": numerator,
        "denominator": 1,
    }
    record.update(status=status, checks=[])
    assert assessment_status(record, "tools") == "failed"


@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([], "unassessed"),
        (["passed"], "passed"),
        (["not_applicable", "not_applicable"], "not_applicable"),
        (["not_applicable", "passed"], "passed"),
        (["unassessed", "passed"], "unassessed"),
        (["unknown", "passed"], "unassessed"),
        ([None, "passed"], "unassessed"),
        ([[], "passed"], "unassessed"),
        ([StrSubclass("passed")], "unassessed"),
        ([None, "failed", "unassessed"], "failed"),
    ],
)
def test_combine_statuses(statuses: list[object], expected: str) -> None:
    assert combine_statuses(cast(list[str], statuses)) == expected
