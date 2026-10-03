from dataclasses import asdict
from typing import cast

import pytest

from app.evaluation_summary_task_assessments import assessment_status
from app.evaluation_summary_task_validation import TaskFacts, classify_slot

_CONDITIONS = [
    ("tool_enabled", "model"),
    ("no_tool", "no_tool"),
    ("deterministic", "reference"),
    ("deterministic_fixture", "budget"),
    ("controlled_fixture", "refresh"),
]


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _slot() -> dict[str, object]:
    return {
        "case_id": "case-1",
        "repeat": 1,
        "condition": "tool_enabled",
        "driver": "model",
        "status": "completed",
        "report": None,
        "observation": {
            "status": "completed",
            "evidence_class": "deterministic_fake_provider",
            "final_only": True,
            "scope": "structured_input_final_plan",
            "turns": [{"status": "completed"}],
        },
        "assessments": {
            "plan": {
                "status": "passed",
                "scope": "final_plan",
                "checks": {},
                "constraint_violations": [],
            },
            "outcome": {
                "status": "passed",
                "scope": "final_turn",
                "checks": {},
                "clarification_required": False,
                "clarification_correct": None,
            },
            "claims": {
                "status": "passed",
                "scope": "public_output_only",
                "checks": {},
                "assessed_count": 2,
                "supported_count": 2,
                "unsupported_count": 0,
                "unknown_count": 0,
                "supported_refusal_count": 0,
            },
            "tools": {
                "status": "passed",
                "valid_calls": {"status": "passed", "numerator": 2, "denominator": 2},
                "expected_tool_selection": {
                    "status": "passed",
                    "numerator": 2,
                    "denominator": 2,
                },
                "expected_arguments": {
                    "status": "passed",
                    "numerator": 2,
                    "denominator": 2,
                },
                "unnecessary_calls": {
                    "status": "passed",
                    "numerator": 0,
                    "denominator": 2,
                },
            },
            "fixture": {"status": "passed", "checks": {"guard": True}},
        },
    }


def _assessment(slot: dict[str, object], name: str) -> dict[str, object]:
    return _map(_map(slot["assessments"])[name])


@pytest.mark.parametrize(
    ("condition", "driver", "scope"),
    [
        ("tool_enabled", "model", "language_task"),
        ("no_tool", "no_tool", "language_task"),
        ("deterministic", "reference", "structured_reference"),
        *[
            ("deterministic_fixture", driver, "fixture_guard")
            for driver in ("budget", "meals", "followup", "missing")
        ],
        *[
            ("controlled_fixture", driver, "fixture_guard")
            for driver in ("refresh", "handoff", "protocol", "duplicate")
        ],
    ],
)
def test_exact_slot_schema(condition: str, driver: str, scope: str) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    assert classify_slot(slot) == TaskFacts(
        "case-1",
        1,
        condition,
        "deterministic_fake_provider",
        driver,
        "completed",
        "completed",
        scope,
        "passed",
    )


@pytest.mark.parametrize("level", ["slot", "observation", "turn"])
@pytest.mark.parametrize(
    ("status", "quality"),
    [
        ("completed", "passed"),
        ("failed", "failed"),
        ("partial", "failed"),
        ("unassessed", "unassessed"),
    ],
)
def test_execution_statuses_are_independent(
    level: str, status: str, quality: str
) -> None:
    slot = _slot()
    target = slot if level == "slot" else _map(slot["observation"])
    if level == "turn":
        target = {"status": "completed"}
        _map(slot["observation"])["turns"] = [{"status": "completed"}, target]
    target["status"] = status
    facts = classify_slot(slot)
    assert facts.quality_status == quality
    assert facts.execution_status == (status if level == "slot" else "completed")
    assert facts.observation_status == (
        status if level == "observation" else "completed"
    )


@pytest.mark.parametrize("level", ["slot", "observation"])
@pytest.mark.parametrize(
    "status", [None, True, 1, "passed", "not_applicable", "COMPLETE"]
)
def test_invalid_execution_status(level: str, status: object) -> None:
    slot = _slot()
    target = slot if level == "slot" else _map(slot["observation"])
    target["status"] = status
    with pytest.raises(ValueError, match="^invalid evaluation slot metadata$"):
        classify_slot(slot)


@pytest.mark.parametrize("level", ["slot", "observation"])
def test_execution_status_alias_cannot_supply_status(level: str) -> None:
    slot = _slot()
    target = slot if level == "slot" else _map(slot["observation"])
    target["execution_status"] = target.pop("status")
    with pytest.raises(ValueError, match="^invalid evaluation slot metadata$"):
        classify_slot(slot)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("case_id", " "),
        ("case_id", 1),
        ("repeat", True),
        ("repeat", 0),
        ("repeat", 1.0),
        ("condition", "unknown"),
        ("condition", []),
        ("driver", "reference"),
        ("driver", True),
        ("observation", []),
        ("assessments", None),
        ("report", False),
        ("report", []),
    ],
)
def test_metadata_validation(key: str, value: object) -> None:
    slot = _slot()
    slot[key] = value
    with pytest.raises(ValueError, match="^invalid evaluation slot metadata$"):
        classify_slot(slot)


def test_report_is_required() -> None:
    slot = _slot()
    del slot["report"]
    with pytest.raises(ValueError, match="^invalid evaluation slot metadata$"):
        classify_slot(slot)
    slot["report"] = {}
    assert classify_slot(slot).quality_status == "passed"


@pytest.mark.parametrize(
    "label", ["real_bedrock", "deterministic_fake_provider", "local_postgresql"]
)
def test_exact_observation_evidence(label: str) -> None:
    slot = _slot()
    _map(slot["observation"])["evidence_class"] = label
    assert classify_slot(slot).evidence_class == label
    assert classify_slot(slot).quality_status == "passed"


@pytest.mark.parametrize("label", [None, True, [], "unknown", "REAL_BEDROCK", "sample"])
def test_invalid_evidence_cannot_pass(label: object) -> None:
    slot = _slot()
    _map(slot["observation"])["evidence_class"] = label
    facts = classify_slot(slot)
    assert facts.evidence_class == "unknown"
    assert facts.quality_status == "unassessed"


def test_slot_evidence_alias_cannot_supply_observation_evidence() -> None:
    slot = _slot()
    slot["evidence_class"] = _map(slot["observation"]).pop("evidence_class")
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize("condition", ["deterministic_fixture", "controlled_fixture"])
def test_fixture_guard_alias_cannot_supply_fixture(condition: str) -> None:
    slot = _slot()
    slot.update(
        condition=condition,
        driver="budget" if condition.startswith("det") else "refresh",
    )
    assessments = _map(slot["assessments"])
    assessments["fixture_guard"] = assessments.pop("fixture")
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize(
    "key",
    [
        "assessed_count",
        "supported_count",
        "unsupported_count",
        "unknown_count",
        "supported_refusal_count",
    ],
)
@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, "0"])
def test_claims_counts_require_exact_nonnegative_integers(
    key: str, value: object
) -> None:
    slot = _slot()
    _assessment(slot, "claims")[key] = value
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize(
    "key",
    [
        "assessed_count",
        "supported_count",
        "unsupported_count",
        "unknown_count",
        "supported_refusal_count",
    ],
)
def test_claims_count_alias_cannot_supply_exact_count(key: str) -> None:
    slot = _slot()
    claims = _assessment(slot, "claims")
    claims[key.removesuffix("_count")] = claims.pop(key)
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize(
    ("changes", "quality"),
    [
        ({"supported_count": 1}, "unassessed"),
        ({"unknown_count": 1}, "unassessed"),
        ({"supported_count": 1, "unsupported_count": 1}, "failed"),
        ({"unsupported_count": 1, "unknown_count": 1}, "failed"),
        ({"unsupported_count": 1, "supported_refusal_count": None}, "failed"),
        (
            {"assessed_count": 0, "supported_count": 0, "supported_refusal_count": 1},
            "passed",
        ),
    ],
)
def test_claims_consistency_and_failure_precedence(
    changes: dict[str, object], quality: str
) -> None:
    slot = _slot()
    _assessment(slot, "claims").update(changes)
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(
    "turns", [None, {}, "turn", (), [None], [False], [[]], ["turn"]]
)
def test_malformed_turns_cannot_pass(turns: object) -> None:
    slot = _slot()
    _map(slot["observation"])["turns"] = turns
    assert classify_slot(slot).quality_status == "unassessed"


def test_missing_turns_cannot_pass() -> None:
    slot = _slot()
    del _map(slot["observation"])["turns"]
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize("level", ["observation", "turn"])
@pytest.mark.parametrize(
    ("flag", "quality"),
    [("secret_leak", "failed"), ("capture_incomplete", "unassessed")],
)
def test_capture_flags_at_exact_levels(level: str, flag: str, quality: str) -> None:
    slot = _slot()
    observation = _map(slot["observation"])
    if level == "observation":
        observation[flag] = True
    else:
        observation["turns"] = [
            {"status": "completed"},
            {"status": "completed", flag: True},
        ]
    assert classify_slot(slot).quality_status == quality


def test_known_failure_survives_incomplete_capture_and_malformed_turn() -> None:
    slot = _slot()
    observation = _map(slot["observation"])
    observation["capture_incomplete"] = True
    observation["turns"] = [None, {"secret_leak": True}]
    assert classify_slot(slot).quality_status == "failed"
    observation["turns"] = None
    slot["status"] = "partial"
    assert classify_slot(slot).quality_status == "failed"


@pytest.mark.parametrize("value", [True, None, 1, "true", []])
def test_raw_public_content_and_wrong_level_flags_are_ignored(value: object) -> None:
    slot = _slot()
    public = {"secret_leak": value, "capture_incomplete": value, "answer": object()}
    slot.update(
        secret_leak=value, capture_incomplete=value, result=public, messages=object()
    )
    slot["report"] = public
    observation = _map(slot["observation"])
    observation.update(result=public, answers=object(), messages=object())
    observation["turns"] = [
        {
            "status": "completed",
            "result": public,
            "answer": object(),
            "messages": object(),
        }
    ]
    facts = classify_slot(slot)
    assert facts.quality_status == "passed"
    assert set(asdict(facts)) == {
        "case_id",
        "repeat",
        "condition",
        "evidence_class",
        "driver",
        "execution_status",
        "observation_status",
        "quality_scope",
        "quality_status",
    }


def test_wrong_aliases_cannot_override_exact_fields() -> None:
    slot = _slot()
    slot.update(execution_status="failed", evidence_class="sample")
    _map(slot["assessments"])["fixture_guard"] = {"status": "failed"}
    _assessment(slot, "claims").update(
        assessed=0, supported=0, unsupported=99, unknown=99
    )
    assert classify_slot(slot).quality_status == "passed"


@pytest.mark.parametrize("kind", ["plan", "outcome", "claims"])
def test_assessment_scope_is_exact(kind: str) -> None:
    slot = _slot()
    _assessment(slot, kind)["scope"] = "other"
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize("checks", [None, [], {"guard": "true"}, {"guard": 1}])
def test_check_types_are_exact(checks: object) -> None:
    slot = _slot()
    _assessment(slot, "plan")["checks"] = checks
    assert classify_slot(slot).quality_status == "unassessed"


def test_failed_check_precedes_unassessed_check() -> None:
    slot = _slot()
    _assessment(slot, "plan")["checks"] = {"known": False, "invalid": None}
    assert classify_slot(slot).quality_status == "failed"


@pytest.mark.parametrize(
    ("violations", "quality"),
    [(None, "unassessed"), ([1], "unassessed"), (["budget"], "failed")],
)
def test_plan_constraint_validation(violations: object, quality: str) -> None:
    slot = _slot()
    _assessment(slot, "plan")["constraint_violations"] = violations
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(
    ("required", "correct", "quality"),
    [
        (True, True, "passed"),
        (True, False, "failed"),
        (True, None, "failed"),
        (1, True, "unassessed"),
        (False, 1, "unassessed"),
    ],
)
def test_clarification_validation(
    required: object, correct: object, quality: str
) -> None:
    slot = _slot()
    _assessment(slot, "outcome").update(
        clarification_required=required, clarification_correct=correct
    )
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(
    "metric",
    [
        "valid_calls",
        "expected_tool_selection",
        "expected_arguments",
        "unnecessary_calls",
    ],
)
@pytest.mark.parametrize(
    ("numerator", "denominator", "quality"),
    [
        (True, 2, "unassessed"),
        (0, False, "unassessed"),
        (0, 0, "passed"),
        (-1, 2, "unassessed"),
        (3, 2, "unassessed"),
        (0.0, 2, "unassessed"),
    ],
)
def test_tool_metric_validation(
    metric: str, numerator: object, denominator: object, quality: str
) -> None:
    slot = _slot()
    _map(_assessment(slot, "tools")[metric]).update(
        numerator=numerator, denominator=denominator
    )
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(
    "metric", ["valid_calls", "expected_tool_selection", "expected_arguments"]
)
def test_tool_metric_failure_and_missing_assessment(metric: str) -> None:
    slot = _slot()
    _map(_assessment(slot, "tools")[metric])["numerator"] = 1
    assert classify_slot(slot).quality_status == "failed"
    del _assessment(slot, "tools")[metric]
    assert classify_slot(slot).quality_status == "unassessed"


def test_unnecessary_calls_fail() -> None:
    slot = _slot()
    _map(_assessment(slot, "tools")["unnecessary_calls"])["numerator"] = 1
    assert classify_slot(slot).quality_status == "failed"


@pytest.mark.parametrize("kind", ["plan", "claims"])
def test_valid_not_applicable_assessment(kind: str) -> None:
    slot = _slot()
    _assessment(slot, kind)["status"] = "not_applicable"
    assert classify_slot(slot).quality_status == "passed"
    _assessment(slot, kind)["scope"] = "other"
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize("status", [True, "completed", None])
def test_invalid_assessment_status(status: object) -> None:
    slot = _slot()
    _assessment(slot, "plan")["status"] = status
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize("checks", [{}, None, {"guard": False}, {"guard": True}])
def test_fixture_checks(checks: object) -> None:
    slot = _slot()
    slot.update(condition="deterministic_fixture", driver="budget")
    _assessment(slot, "fixture")["checks"] = checks
    expected = "passed" if checks == {"guard": True} else "unassessed"
    if checks == {"guard": False}:
        expected = "failed"
    assert classify_slot(slot).quality_status == expected


@pytest.mark.parametrize(
    ("condition", "driver", "ignored"),
    [
        ("no_tool", "no_tool", "tools"),
        ("deterministic", "reference", "outcome"),
        ("deterministic", "reference", "claims"),
        ("deterministic", "reference", "tools"),
        ("controlled_fixture", "refresh", "plan"),
        ("controlled_fixture", "refresh", "outcome"),
        ("controlled_fixture", "refresh", "claims"),
        ("controlled_fixture", "refresh", "tools"),
    ],
)
@pytest.mark.parametrize("status", ["invalid", "failed", "not_applicable"])
def test_only_condition_assessments_are_used(
    condition: str, driver: str, ignored: str, status: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _assessment(slot, ignored)["status"] = status
    assert classify_slot(slot).quality_status == "passed"


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
def test_empty_turns_depend_on_condition(condition: str, driver: str) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _map(slot["observation"])["turns"] = []
    expected = "passed" if condition.endswith("_fixture") else "unassessed"
    assert classify_slot(slot).quality_status == expected


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
@pytest.mark.parametrize(
    ("status", "quality"),
    [
        ("completed", "passed"),
        ("failed", "failed"),
        ("partial", "failed"),
        ("unassessed", "unassessed"),
        (None, "unassessed"),
        (True, "unassessed"),
        (1, "unassessed"),
        ("passed", "unassessed"),
        ("not_applicable", "unassessed"),
        ("COMPLETED", "unassessed"),
        ([], "unassessed"),
    ],
)
def test_turn_status_for_every_condition(
    condition: str, driver: str, status: object, quality: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _map(slot["observation"])["turns"] = [{"status": status}]
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
@pytest.mark.parametrize("turn", [{}, {"execution_status": "completed"}, None, []])
def test_malformed_turn_for_every_condition(
    condition: str, driver: str, turn: object
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _map(slot["observation"])["turns"] = [turn]
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("final_only", None),
        ("final_only", False),
        ("final_only", 1),
        ("final_only", "true"),
        ("scope", None),
        ("scope", "structured_reference"),
        ("scope", "STRUCTURED_INPUT_FINAL_PLAN"),
        ("turns", []),
        ("turns", [{"status": "completed"}, {"status": "completed"}]),
        ("turns", [{"status": "unassessed"}]),
    ],
)
def test_reference_requires_final_scope_and_one_completed_turn(
    field: str, value: object
) -> None:
    slot = _slot()
    slot.update(condition="deterministic", driver="reference")
    _map(slot["observation"])[field] = value
    facts = classify_slot(slot)
    assert facts.quality_scope == "structured_reference"
    assert facts.quality_status == "unassessed"


@pytest.mark.parametrize("field", ["final_only", "scope", "turns"])
def test_reference_requires_observation_markers(field: str) -> None:
    slot = _slot()
    slot.update(condition="deterministic", driver="reference")
    observation = _map(slot["observation"])
    slot[field] = observation.pop(field)
    assert classify_slot(slot).quality_status == "unassessed"


class _Turn(dict[str, object]):
    pass


class _ExecutionStatus(str):
    pass


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
def test_turn_requires_exact_dict_and_status(condition: str, driver: str) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    observation = _map(slot["observation"])
    observation["turns"] = [_Turn(status="completed")]
    assert classify_slot(slot).quality_status == "unassessed"
    observation["turns"] = [{"status": _ExecutionStatus("completed")}]
    assert classify_slot(slot).quality_status == "unassessed"


@pytest.mark.parametrize("level", ["slot", "observation"])
def test_top_execution_status_requires_exact_string(level: str) -> None:
    slot = _slot()
    target = slot if level == "slot" else _map(slot["observation"])
    target["status"] = _ExecutionStatus("completed")
    with pytest.raises(ValueError, match="^invalid evaluation slot metadata$"):
        classify_slot(slot)


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
@pytest.mark.parametrize(
    ("flag", "quality"),
    [("secret_leak", "failed"), ("capture_incomplete", "unassessed")],
)
def test_turn_flags_for_every_condition(
    condition: str, driver: str, flag: str, quality: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _map(slot["observation"])["turns"] = [{"status": "completed", flag: True}]
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize("level", ["observation", "turn"])
@pytest.mark.parametrize("flag", ["secret_leak", "capture_incomplete"])
@pytest.mark.parametrize(
    ("value", "quality"),
    [
        (False, "passed"),
        (None, "unassessed"),
        (0, "unassessed"),
        (1, "unassessed"),
        (0.0, "unassessed"),
        ("true", "unassessed"),
        ([], "unassessed"),
        ({}, "unassessed"),
    ],
)
def test_flags_require_exact_booleans(
    level: str, flag: str, value: object, quality: str
) -> None:
    slot = _slot()
    observation = _map(slot["observation"])
    if level == "observation":
        observation[flag] = value
    else:
        observation["turns"] = [{"status": "completed", flag: value}]
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
@pytest.mark.parametrize("level", ["observation", "turn"])
@pytest.mark.parametrize("flag", ["secret_leak", "capture_incomplete"])
@pytest.mark.parametrize("value", [None, 1, "true", []])
@pytest.mark.parametrize("failure", ["execution", "assessment", "secret_leak"])
def test_known_failure_precedes_malformed_flags(
    condition: str, driver: str, level: str, flag: str, value: object, failure: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    observation = _map(slot["observation"])
    turn: dict[str, object] = {"status": "completed"}
    observation["turns"] = [turn]
    target = observation if level == "observation" else turn
    target[flag] = value
    if failure == "execution":
        slot["status"] = "partial"
    elif failure == "assessment":
        kind = "fixture" if condition.endswith("_fixture") else "plan"
        _assessment(slot, kind)["status"] = "failed"
    else:
        other = turn if level == "observation" else observation
        other["secret_leak"] = True
    observation["capture_incomplete"] = (
        value if level == "observation" and flag == "capture_incomplete" else True
    )
    assert classify_slot(slot).quality_status == "failed"


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
@pytest.mark.parametrize(
    "failure", [{"status": "failed"}, {"status": "partial"}, {"secret_leak": True}]
)
@pytest.mark.parametrize("failure_first", [True, False])
def test_turn_failure_precedes_unknown_evidence(
    condition: str, driver: str, failure: dict[str, object], failure_first: bool
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    turns = [failure, None] if failure_first else [None, failure]
    _map(slot["observation"]).update(
        turns=turns, capture_incomplete=True, evidence_class="sample"
    )
    assert classify_slot(slot).quality_status == "failed"


@pytest.mark.parametrize(("condition", "driver"), _CONDITIONS)
@pytest.mark.parametrize(
    ("turn", "quality"),
    [
        ({1: "invalid", "status": "completed"}, "unassessed"),
        ({1: "invalid", "status": "partial"}, "failed"),
        ({1: "invalid", "status": None, "secret_leak": True}, "failed"),
    ],
)
def test_malformed_turn_keys_preserve_known_failure(
    condition: str, driver: str, turn: dict[object, object], quality: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _map(slot["observation"])["turns"] = [turn]
    assert classify_slot(slot).quality_status == quality


@pytest.mark.parametrize(
    ("kind", "record"),
    [
        ("plan", {"status": "not_applicable", "scope": "final_plan"}),
        ("claims", {"status": "not_applicable", "scope": "public_output_only"}),
    ],
)
@pytest.mark.parametrize(
    ("condition", "driver"), [("tool_enabled", "model"), ("no_tool", "no_tool")]
)
def test_minimal_abstentions_use_approved_helper(
    kind: str, record: dict[str, object], condition: str, driver: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _map(slot["assessments"])[kind] = record
    assert assessment_status(record, kind) == "not_applicable"
    facts = classify_slot(slot)
    assert facts.quality_scope == "language_task"
    assert facts.quality_status == "passed"


@pytest.mark.parametrize("status", ["passed", "unassessed", "not_applicable"])
@pytest.mark.parametrize("counts", [False, True])
@pytest.mark.parametrize(
    ("condition", "driver", "quality"),
    [("tool_enabled", "model", "unassessed"), ("no_tool", "no_tool", "passed")],
)
def test_tool_not_applicable_metrics_cannot_pass_required_assessment(
    status: str, counts: bool, condition: str, driver: str, quality: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    tools = _assessment(slot, "tools")
    tools["status"] = status
    for name in tools.keys() - {"status"}:
        tools[name] = {"status": "not_applicable"}
        if counts:
            _map(tools[name]).update(numerator=0, denominator=0)
    facts = classify_slot(slot)
    assert facts.quality_scope == "language_task"
    assert facts.quality_status == quality
    _assessment(slot, "claims")["status"] = "failed"
    _map(slot["observation"])["capture_incomplete"] = True
    assert classify_slot(slot).quality_status == "failed"


def test_tool_enabled_passed_zero_counts_are_successful_abstention() -> None:
    slot = _slot()
    tools = _assessment(slot, "tools")
    for name in tools.keys() - {"status"}:
        tools[name] = {"status": "passed", "numerator": 0, "denominator": 0}
    assert assessment_status(tools, "tools") == "passed"
    facts = classify_slot(slot)
    assert facts.condition == "tool_enabled"
    assert facts.quality_scope == "language_task"
    assert facts.quality_status == "passed"


@pytest.mark.parametrize("minimal", [False, True])
@pytest.mark.parametrize("failure_level", ["slot", "observation", "turn"])
def test_reference_plan_abstention_cannot_pass(
    minimal: bool, failure_level: str
) -> None:
    slot = _slot()
    slot.update(condition="deterministic", driver="reference")
    if minimal:
        _map(slot["assessments"])["plan"] = {
            "status": "not_applicable",
            "scope": "final_plan",
        }
    else:
        _assessment(slot, "plan")["status"] = "not_applicable"
    assert assessment_status(_assessment(slot, "plan"), "plan") == "not_applicable"
    facts = classify_slot(slot)
    assert facts.quality_scope == "structured_reference"
    assert facts.quality_status == "unassessed"
    observation = _map(slot["observation"])
    observation["capture_incomplete"] = True
    if failure_level == "turn":
        observation["turns"] = [{"status": "failed"}]
    else:
        target = slot if failure_level == "slot" else observation
        target["status"] = "failed"
    assert classify_slot(slot).quality_status == "failed"


@pytest.mark.parametrize(
    ("condition", "driver", "kind"),
    [
        ("tool_enabled", "model", "tools"),
        ("no_tool", "no_tool", "outcome"),
        ("deterministic", "reference", "plan"),
        ("deterministic_fixture", "budget", "fixture"),
        ("controlled_fixture", "refresh", "fixture"),
    ],
)
def test_assessment_failure_precedes_missing_execution_evidence(
    condition: str, driver: str, kind: str
) -> None:
    slot = _slot()
    slot.update(condition=condition, driver=driver)
    _assessment(slot, kind)["status"] = "failed"
    _map(slot["observation"]).update(turns=None, status="unassessed")
    assert classify_slot(slot).quality_status == "failed"
