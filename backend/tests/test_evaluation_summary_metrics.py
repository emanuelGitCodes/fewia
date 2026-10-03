from copy import deepcopy
from typing import cast

import pytest

from app.evaluation_summary_metrics import summarize_metrics


def slot(
    assessments: dict[str, object] | None = None,
    *,
    condition: str = "tool_enabled",
    driver: str = "model",
    evidence: str = "deterministic_fake_provider",
    repeat: int = 1,
) -> dict[str, object]:
    return {
        "case_id": "F01",
        "repeat": repeat,
        "condition": condition,
        "driver": driver,
        "elapsed_seconds": 0.5,
        "status": "completed",
        "observation": {"status": "completed", "evidence_class": evidence, "turns": []},
        "assessments": assessments or {},
        "report": None,
    }


def mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def assessment(summary: dict[str, object], name: str) -> dict[str, object]:
    return mapping(mapping(summary["assessments"])[name])


def metric(summary: dict[str, object], name: str) -> dict[str, object]:
    return mapping(mapping(summary["tool_metrics"])[name])


def tool(
    numerator: object, denominator: object, status: str = "passed"
) -> dict[str, object]:
    return {"status": status, "numerator": numerator, "denominator": denominator}


def claims(
    supported: int = 0,
    unsupported: int = 0,
    unknown: int = 0,
    refusals: int = 0,
) -> dict[str, object]:
    return {
        "status": "passed",
        "scope": "public_output_only",
        "supported_count": supported,
        "unsupported_count": unsupported,
        "assessed_count": supported + unsupported,
        "unknown_count": unknown,
        "supported_refusal_count": refusals,
    }


def test_literal_unequal_tool_denominators() -> None:
    summary = summarize_metrics(
        [
            slot({"tools": {"status": "failed", "valid_calls": tool(1, 2, "failed")}}),
            slot({"tools": {"status": "passed", "valid_calls": tool(8, 8)}}, repeat=2),
        ]
    )
    valid = metric(summary, "valid_calls")
    assert valid["counts"] == {"numerator": 9, "denominator": 10}
    assert valid["rate"] == 0.9
    assert valid["pass_rate"] == 0.5
    assert valid["status_counts"] == {
        "passed": 1,
        "failed": 1,
        "unassessed": 0,
        "not_applicable": 0,
    }
    assert metric(summary, "expected_arguments")["rate"] is None


def test_execution_completion_and_absent_status_do_not_imply_success() -> None:
    summary = summarize_metrics(
        [
            slot({"plan": {"scope": "final_plan", "checks": {"budget": True}}}),
            slot(
                {"plan": {"status": "passed", "scope": "final_plan", "checks": {}}},
                repeat=2,
            ),
            slot(repeat=3),
        ]
    )
    plan = assessment(summary, "plan")
    assert plan["status_counts"] == {
        "passed": 1,
        "failed": 0,
        "unassessed": 2,
        "not_applicable": 0,
    }
    assert plan["denominator"] == 1
    assert plan["pass_rate"] == 1.0
    assert assessment(summary, "outcome")["pass_rate"] is None
    assert assessment(summary, "fixture")["status_counts"] == {
        "passed": 0,
        "failed": 0,
        "unassessed": 0,
        "not_applicable": 3,
    }


@pytest.mark.parametrize(
    ("condition", "driver", "relevant"),
    [
        ("tool_enabled", "model", {"tools", "plan", "outcome", "claims"}),
        ("no_tool", "no_tool", {"plan", "outcome", "claims"}),
        ("deterministic", "reference", {"plan"}),
        ("deterministic_fixture", "budget", {"fixture"}),
        ("controlled_fixture", "protocol", {"fixture"}),
    ],
)
def test_driver_relevance(condition: str, driver: str, relevant: set[str]) -> None:
    summary = summarize_metrics([slot(condition=condition, driver=driver)])
    for name in ("tools", "plan", "outcome", "claims", "fixture"):
        counts = mapping(assessment(summary, name)["status_counts"])
        assert counts["unassessed"] == int(name in relevant)
        assert counts["not_applicable"] == int(name not in relevant)
        assert assessment(summary, name)["pass_rate"] is None


def test_caller_groups_fake_and_live_evidence_separately() -> None:
    slots = [
        slot({"claims": claims(2)}, evidence="deterministic_fake_provider"),
        slot({"claims": claims(0, 1)}, evidence="real_bedrock"),
        slot(condition="no_tool", driver="no_tool", evidence="real_bedrock"),
    ]
    groups: dict[tuple[object, object], list[dict[str, object]]] = {}
    for item in slots:
        key = (item["condition"], mapping(item["observation"])["evidence_class"])
        groups.setdefault(key, []).append(item)
    summaries = {key: summarize_metrics(items) for key, items in groups.items()}
    fake = summaries[("tool_enabled", "deterministic_fake_provider")]
    live = summaries[("tool_enabled", "real_bedrock")]
    no_tool = summaries[("no_tool", "real_bedrock")]
    assert assessment(fake, "claims")["support_rate"] == 1.0
    assert assessment(live, "claims")["support_rate"] == 0.0
    assert assessment(no_tool, "claims")["support_rate"] is None


def test_unnecessary_calls_count_violations_and_lower_is_better() -> None:
    summary = summarize_metrics(
        [
            slot(
                {
                    "tools": {
                        "status": "failed",
                        "unnecessary_calls": tool(1, 2, "failed"),
                    }
                }
            ),
            slot(
                {"tools": {"status": "passed", "unnecessary_calls": tool(0, 8)}},
                repeat=2,
            ),
        ]
    )
    unnecessary = metric(summary, "unnecessary_calls")
    assert unnecessary["counts"] == {"numerator": 1, "denominator": 10}
    assert unnecessary["rate"] == 0.1
    assert unnecessary["direction"] == "lower_is_better"


@pytest.mark.parametrize("field", ["numerator", "denominator"])
@pytest.mark.parametrize("invalid", [True, False, -1, 1.5, "1", None])
def test_tool_counts_require_exact_nonnegative_integers(
    field: str, invalid: object
) -> None:
    payload = tool(0, 1)
    payload[field] = invalid
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"tools": {"valid_calls": payload}})])


@pytest.mark.parametrize(
    "payload",
    [tool(2, 1), {"status": "passed", "numerator": 1}, {"denominator": 1}],
)
def test_impossible_or_incomplete_tool_counts_fail(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"tools": {"valid_calls": payload}})])


@pytest.mark.parametrize(
    "field",
    [
        "supported_count",
        "unsupported_count",
        "assessed_count",
        "unknown_count",
        "supported_refusal_count",
    ],
)
@pytest.mark.parametrize("invalid", [True, -1, 0.5, "0", None])
def test_claim_counts_require_exact_nonnegative_integers(
    field: str, invalid: object
) -> None:
    payload = claims()
    payload[field] = invalid
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"claims": payload})])


def test_incoherent_claim_counts_fail() -> None:
    payload = claims(1, 1)
    payload["assessed_count"] = 1
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"claims": payload})])


@pytest.mark.parametrize("status", ["passed", "not_applicable"])
def test_zero_factual_claims_keep_refusals_separate(status: str) -> None:
    payload = claims(refusals=2)
    payload["status"] = status
    summary = summarize_metrics([slot({"claims": payload})])
    factual = assessment(summary, "claims")
    assert factual["scope"] == "public_output_only"
    assert factual["support_rate"] is None
    assert factual["conservative_support_rate"] is None
    assert factual["counts"] == {
        "supported_count": 0,
        "unsupported_count": 0,
        "assessed_count": 0,
        "unknown_count": 0,
        "supported_refusal_count": 2,
    }
    assert mapping(factual["status_counts"])[status] == 1


def test_unknown_public_claims_have_conservative_denominator() -> None:
    summary = summarize_metrics(
        [
            slot({"claims": claims(2, 1, 2, 1)}),
            slot({"claims": claims(0, 0, 3)}, repeat=2),
        ]
    )
    factual = assessment(summary, "claims")
    assert factual["counts"] == {
        "supported_count": 2,
        "unsupported_count": 1,
        "assessed_count": 3,
        "unknown_count": 5,
        "supported_refusal_count": 1,
    }
    assert factual["support_rate"] == pytest.approx(2 / 3)
    assert factual["conservative_support_rate"] == 0.25


def test_unknown_only_claims_and_missing_status_remain_visible() -> None:
    payload = claims(unknown=3)
    payload.pop("status")
    factual = assessment(summarize_metrics([slot({"claims": payload})]), "claims")
    assert factual["support_rate"] is None
    assert factual["conservative_support_rate"] == 0.0
    assert mapping(factual["status_counts"])["unassessed"] == 1
    assert factual["denominator"] == 0


def test_zero_tool_calls_have_no_count_rate() -> None:
    summary = summarize_metrics(
        [
            slot({"tools": {"valid_calls": tool(0, 0, "unassessed")}}),
        ]
    )
    valid = metric(summary, "valid_calls")
    assert valid["rate"] is None
    assert valid["pass_rate"] is None
    assert valid["counts"] == {"numerator": 0, "denominator": 0}


def test_not_applicable_tools_may_omit_counts() -> None:
    summary = summarize_metrics(
        [
            slot({"tools": {"status": "not_applicable"}}),
        ]
    )
    for name in (
        "valid_calls",
        "expected_tool_selection",
        "expected_arguments",
        "unnecessary_calls",
    ):
        value = metric(summary, name)
        assert value["rate"] is None
        assert mapping(value["status_counts"])["not_applicable"] == 1


def test_named_checks_clarification_and_safe_failures() -> None:
    summary = summarize_metrics(
        [
            slot(
                {
                    "plan": {
                        "status": "failed",
                        "scope": "final_plan",
                        "checks": {"budget": False, "servings": True},
                        "constraint_violations": ["PRIVATE DETAILS"],
                    },
                    "outcome": {
                        "status": "failed",
                        "scope": "final_turn",
                        "checks": {"requested_clarification": False},
                        "clarification_required": True,
                        "clarification_correct": False,
                        "unassessed_reasons": [],
                    },
                }
            ),
            slot(
                {
                    "plan": {
                        "status": "passed",
                        "scope": "final_plan",
                        "checks": {"budget": True},
                    },
                    "outcome": {
                        "status": "passed",
                        "scope": "final_turn",
                        "checks": {},
                        "clarification_required": True,
                        "clarification_correct": True,
                        "unassessed_reasons": [],
                    },
                },
                repeat=2,
            ),
            slot(repeat=3),
        ]
    )
    budget = mapping(mapping(summary["plan_checks"])["budget"])
    assert budget["denominator"] == 2
    assert budget["pass_rate"] == 0.5
    servings = mapping(mapping(summary["plan_checks"])["servings"])
    assert servings["denominator"] == 1
    assert mapping(servings["status_counts"])["failed"] == 0
    clarity = mapping(summary["clarification_correctness"])
    assert clarity["denominator"] == 2
    assert clarity["pass_rate"] == 0.5
    assert mapping(clarity["status_counts"])["unassessed"] == 1
    assert summary["known_failures"] == [
        {"case_id": "F01", "repeat": 1, "assessment": "plan", "checks": ["budget"]},
        {
            "case_id": "F01",
            "repeat": 1,
            "assessment": "outcome",
            "checks": ["requested_clarification"],
        },
    ]
    assert "PRIVATE DETAILS" not in repr(summary)


def test_fixture_checks_are_separate_from_model_quality() -> None:
    summary = summarize_metrics(
        [
            slot(
                {"fixture": {"status": "passed", "checks": {"guard": True}}},
                condition="controlled_fixture",
                driver="refresh",
                evidence="local_postgresql",
            ),
            slot(
                {"fixture": {"status": "failed", "checks": {"guard": False}}},
                condition="controlled_fixture",
                driver="handoff",
                evidence="local_postgresql",
                repeat=2,
            ),
        ]
    )
    guard = mapping(mapping(summary["fixture_checks"])["guard"])
    assert guard["denominator"] == 2
    assert guard["pass_rate"] == 0.5
    assert assessment(summary, "plan")["pass_rate"] is None
    assert assessment(summary, "claims")["support_rate"] is None
    assert mapping(assessment(summary, "tools")["status_counts"])["not_applicable"] == 2


@pytest.mark.parametrize("checks", [{}, {"guard": 1}, {"guard": "true"}, [], None])
def test_fixture_requires_nonempty_exact_boolean_checks(
    checks: object,
) -> None:
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics(
            [
                slot(
                    {"fixture": {"status": "passed", "checks": checks}},
                    condition="deterministic_fixture",
                    driver="budget",
                ),
            ]
        )


@pytest.mark.parametrize("status", ["failed", "unassessed"])
def test_fixture_empty_checks_preserve_failed_or_unassessed_status(status: str) -> None:
    item = slot(
        {"fixture": {"status": status, "checks": {}}},
        condition="controlled_fixture",
        driver="refresh",
    )
    original = deepcopy(item)
    summary = summarize_metrics([item])
    fixture = assessment(summary, "fixture")
    assert mapping(fixture["status_counts"])[status] == 1
    assert fixture["denominator"] == int(status == "failed")
    assert fixture["pass_rate"] == (0.0 if status == "failed" else None)
    assert summary["fixture_checks"] == {}
    failures: list[dict[str, object]] = []
    if status == "failed":
        failures.append(
            {"case_id": "F01", "repeat": 1, "assessment": "fixture", "checks": []}
        )
    assert summary["known_failures"] == failures
    assert item == original


@pytest.mark.parametrize("status", ["failed", "unassessed"])
@pytest.mark.parametrize("checks", [{"guard": 1}, {"guard": "true"}, [], None])
def test_failed_or_unassessed_fixture_rejects_invalid_checks(
    status: str, checks: object
) -> None:
    item = slot(
        {"fixture": {"status": status, "checks": checks}},
        condition="controlled_fixture",
        driver="refresh",
    )
    original = deepcopy(item)
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])
    assert item == original


def test_reference_scores_only_final_structured_plan() -> None:
    summary = summarize_metrics(
        [
            slot(
                {
                    "plan": {
                        "status": "passed",
                        "scope": "final_plan",
                        "checks": {"budget": True},
                    },
                    "claims": {"supported_count": True, "secret": "PRIVATE"},
                },
                condition="deterministic",
                driver="reference",
            ),
        ]
    )
    assert assessment(summary, "plan")["pass_rate"] == 1.0
    assert assessment(summary, "claims")["support_rate"] is None
    assert "PRIVATE" not in repr(summary)


def test_inputs_are_immutable_and_raw_fields_are_not_copied() -> None:
    item = slot({"claims": claims(1)})
    item["report"] = {"answer": "SECRET_REPORT", "exception": "SECRET_EXCEPTION"}
    observation = mapping(item["observation"])
    observation["turns"] = [
        {"result": {"answer": "SECRET_ANSWER"}, "telemetry": "SECRET_TELEMETRY"}
    ]
    item["inputs"] = {"prompt": "SECRET_INPUT"}
    original = deepcopy(item)
    summary = summarize_metrics([item])
    assert item == original
    assert "SECRET_" not in repr(summary)


def test_hidden_reasoning_claim_scope_is_rejected() -> None:
    payload = claims(1)
    payload["scope"] = "hidden_reasoning"
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"claims": payload})])


def test_invalid_status_does_not_pass() -> None:
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics(
            [slot({"plan": {"status": "completed", "scope": "final_plan"}})]
        )


def test_empty_group_has_null_rates() -> None:
    summary = summarize_metrics([])
    for name in ("tools", "plan", "outcome", "claims", "fixture"):
        assert assessment(summary, name)["denominator"] == 0
        assert assessment(summary, name)["pass_rate"] is None
    assert metric(summary, "valid_calls")["rate"] is None
    assert assessment(summary, "claims")["support_rate"] is None
    assert summary["known_failures"] == []


@pytest.mark.parametrize(
    ("required", "correct", "expected"),
    [
        (True, None, "unassessed"),
        (False, None, "not_applicable"),
        (True, False, "failed"),
        (True, True, "passed"),
    ],
)
def test_clarification_correctness_has_explicit_status_denominators(
    required: bool, correct: bool | None, expected: str
) -> None:
    summary = summarize_metrics(
        [
            slot(
                {
                    "outcome": {
                        "status": "unassessed",
                        "scope": "final_turn",
                        "clarification_required": required,
                        "clarification_correct": correct,
                    }
                }
            )
        ]
    )
    clarification = mapping(summary["clarification_correctness"])
    assert mapping(clarification["status_counts"])[expected] == 1
    assert clarification["denominator"] == int(expected in {"passed", "failed"})


def test_nested_tool_failure_has_case_and_metric_name() -> None:
    summary = summarize_metrics(
        [slot({"tools": {"valid_calls": tool(0, 1, "failed")}}, repeat=2)]
    )
    assert summary["known_failures"] == [
        {
            "case_id": "F01",
            "repeat": 2,
            "assessment": "tools",
            "checks": ["valid_calls"],
        }
    ]


@pytest.mark.parametrize(
    ("key", "invalid"), [("case_id", "PRIVATE FAILURE DETAILS"), ("repeat", True)]
)
def test_failure_identifiers_are_safe_and_errors_are_static(
    key: str, invalid: object
) -> None:
    item = slot({"plan": {"status": "failed"}})
    item[key] = invalid
    original = deepcopy(item)
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])
    assert item == original


@pytest.mark.parametrize("scope", ["plan", "fixture", "tools"])
@pytest.mark.parametrize("status", ["failed", "unassessed"])
def test_observed_failure_requires_positive_repeat(scope: str, status: str) -> None:
    item = slot(
        {scope: {"status": status, "checks": {"budget": False}}},
        condition="deterministic_fixture" if scope == "fixture" else "tool_enabled",
        driver="budget" if scope == "fixture" else "model",
        repeat=0,
    )
    original = deepcopy(item)
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])
    assert item == original


@pytest.mark.parametrize(
    "invalid",
    [
        tool(True, 1, "not_applicable"),
        tool(-1, 1, "not_applicable"),
        tool(None, 1, "not_applicable"),
        tool(2, 1, "not_applicable"),
    ],
)
def test_supplied_not_applicable_counts_are_validated(
    invalid: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"tools": {"valid_calls": invalid}})])


def test_not_applicable_counts_do_not_inflate_measured_rates() -> None:
    summary = summarize_metrics(
        [slot({"tools": {"valid_calls": tool(1, 1, "not_applicable")}})]
    )
    valid = metric(summary, "valid_calls")
    assert valid["counts"] == {"numerator": 0, "denominator": 0}
    assert valid["rate"] is None
    assert valid["denominator"] == 0
    assert mapping(valid["status_counts"])["not_applicable"] == 1


def test_no_tool_assessments_ignore_tool_failures_and_counts() -> None:
    summary = summarize_metrics(
        [
            slot(
                {
                    "tools": {
                        "status": "failed",
                        "valid_calls": tool(1, 2, "failed"),
                        "unnecessary_calls": tool(1, 1, "failed"),
                    },
                    "plan": {"status": "passed", "checks": {"budget": True}},
                    "outcome": {"status": "passed"},
                    "claims": claims(1),
                },
                condition="no_tool",
                driver="no_tool",
            )
        ]
    )
    assert mapping(assessment(summary, "tools")["status_counts"])["not_applicable"] == 1
    assert assessment(summary, "tools")["denominator"] == 0
    for value in mapping(summary["tool_metrics"]).values():
        measured = mapping(value)
        assert measured["counts"] == {"numerator": 0, "denominator": 0}
        assert measured["rate"] is None
        assert mapping(measured["status_counts"])["not_applicable"] == 1
    assert assessment(summary, "plan")["pass_rate"] == 1.0
    assert assessment(summary, "outcome")["pass_rate"] == 1.0
    assert assessment(summary, "claims")["support_rate"] == 1.0
    assert summary["known_failures"] == []


@pytest.mark.parametrize("scope", ["plan", "fixture"])
def test_safe_case_prefixed_checks_and_only_observed_names(scope: str) -> None:
    names = [
        "B04a.available_cents",
        "B04b.outcome",
        "B05b.stale",
        "M06a.accepted",
        "M06a.total_cents",
        "M06b.outcome",
        "B04.available_cents",
        "budget",
        "a" * 64,
        "B04a." + "a" * 64,
    ]
    condition = "deterministic_fixture" if scope == "fixture" else "tool_enabled"
    driver = "budget" if scope == "fixture" else "model"
    summary = summarize_metrics(
        [
            slot(
                {scope: {"status": "failed", "checks": dict.fromkeys(names, False)}},
                condition=condition,
                driver=driver,
            ),
            slot(
                {scope: {"status": "passed", "checks": {"budget": True}}},
                condition=condition,
                driver=driver,
                repeat=2,
            ),
        ]
    )
    named = mapping(summary[f"{scope}_checks"])
    assert set(named) == set(names)
    assert mapping(named["budget"])["denominator"] == 2
    assert mapping(named["budget"])["pass_rate"] == 0.5
    for name in names:
        if name != "budget":
            assert mapping(named[name])["denominator"] == 1
            assert mapping(named[name])["pass_rate"] == 0.0
            assert mapping(mapping(named[name])["status_counts"])["failed"] == 1
    assert summary["known_failures"] == [
        {"case_id": "F01", "repeat": 1, "assessment": scope, "checks": names}
    ]


@pytest.mark.parametrize("scope", ["plan", "fixture"])
@pytest.mark.parametrize(
    "name",
    [
        "a" * 65,
        "B04a." + "a" * 65,
        "PRIVATE RAW ANSWER",
        "budget\n",
        "B04aa.budget",
        "b04.budget",
        "B04a.Budget",
        "B04a.budget.extra",
        "_budget",
        "",
    ],
)
def test_arbitrary_or_overlong_check_names_are_rejected(scope: str, name: str) -> None:
    item = slot(
        {scope: {"status": "failed", "checks": {name: False}}},
        condition="deterministic_fixture" if scope == "fixture" else "tool_enabled",
        driver="budget" if scope == "fixture" else "model",
    )
    original = deepcopy(item)
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])
    assert item == original


@pytest.mark.parametrize("scope", ["tools", "plan", "outcome", "claims", "fixture"])
@pytest.mark.parametrize("status", [[], {}, True, False, None, 1, "completed"])
def test_malformed_assessment_statuses_raise_static_errors(
    scope: str, status: object
) -> None:
    item = slot(
        {scope: {"status": status}},
        condition="controlled_fixture" if scope == "fixture" else "tool_enabled",
        driver="refresh" if scope == "fixture" else "model",
    )
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])


@pytest.mark.parametrize("status", [[], {}, True, False, None, 1, "completed"])
def test_malformed_nested_tool_statuses_raise_static_errors(status: object) -> None:
    payload = tool(0, 1)
    payload["status"] = status
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"tools": {"valid_calls": payload}})])


@pytest.mark.parametrize("value", [[], True, "PRIVATE RAW ANSWER", None])
@pytest.mark.parametrize("location", ["assessments", "plan", "checks", "valid_calls"])
def test_malformed_assessment_structures_raise_static_errors(
    location: str, value: object
) -> None:
    item = slot()
    if location == "assessments":
        item["assessments"] = value
    elif location == "plan":
        item["assessments"] = {"plan": value}
    elif location == "checks":
        item["assessments"] = {"plan": {"checks": value}}
    else:
        item["assessments"] = {"tools": {"valid_calls": value}}
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])


@pytest.mark.parametrize("value", [None, {}, True, "PRIVATE RAW ANSWER"])
def test_malformed_slot_collections_raise_static_errors(value: object) -> None:
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics(cast(list[dict[str, object]], value))


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("assessed_count", 1),
        ("supported_refusal_count", True),
        ("unknown_count", -1),
        ("scope", "hidden_reasoning"),
    ],
)
def test_not_applicable_claims_still_validate_strict_counts(
    field: str, invalid: object
) -> None:
    payload = claims(refusals=2)
    payload["status"] = "not_applicable"
    payload[field] = invalid
    item = slot({"claims": payload})
    original = deepcopy(item)
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([item])
    assert item == original


def test_refusals_do_not_change_mixed_factual_support_and_inputs() -> None:
    refusal = claims(refusals=2)
    refusal["status"] = "not_applicable"
    items = [slot({"claims": claims(1, 1, 2)}), slot({"claims": refusal}, repeat=2)]
    original = deepcopy(items)
    factual = assessment(summarize_metrics(items), "claims")
    assert factual["counts"] == {
        "supported_count": 1,
        "unsupported_count": 1,
        "assessed_count": 2,
        "unknown_count": 2,
        "supported_refusal_count": 2,
    }
    assert factual["support_rate"] == 0.5
    assert factual["conservative_support_rate"] == 0.25
    assert factual["denominator"] == 1
    assert items == original


@pytest.mark.parametrize("location", ["status", "check_name"])
def test_string_subclasses_are_rejected_before_status_or_check_operations(
    location: str,
) -> None:
    class Text(str):
        pass

    payload: dict[str, object] = {"status": "failed", "checks": {"budget": False}}
    if location == "status":
        payload["status"] = Text("failed")
    else:
        payload["checks"] = {Text("budget"): False}
    with pytest.raises(ValueError, match="^invalid evaluation metrics$"):
        summarize_metrics([slot({"plan": payload})])
