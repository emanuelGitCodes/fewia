import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from app.evaluation_plan_score import score_plan
from app.evaluation_reference import observe_reference_case
from app.evaluation_summary import summarize_evaluation
from app.evaluation_summary_metrics import summarize_metrics
from app.evaluation_summary_task import summarize_tasks

_ERROR = "^Invalid evaluation summary input$"


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _slot(
    *,
    condition: str = "tool_enabled",
    evidence: object = "deterministic_fake_provider",
    case_id: str = "F01",
    repeat: int = 1,
    calls: int = 2,
) -> dict[str, object]:
    assessments: dict[str, object] = {
        "plan": {
            "status": "passed",
            "scope": "final_plan",
            "checks": {
                "ingredient_coverage": True,
                "quantities": True,
                "sample_costs": True,
                "budget_cap": True,
                "diet": True,
                "exclusions": True,
            },
            "constraint_violations": [],
        },
        "outcome": {
            "status": "passed",
            "scope": "final_turn",
            "checks": {"completed_request": True},
            "clarification_required": False,
            "clarification_correct": None,
            "unassessed_reasons": [],
        },
        "claims": {
            "status": "passed",
            "scope": "public_output_only",
            "supported_count": 2,
            "assessed_count": 2,
            "unsupported_count": 0,
            "unknown_count": 0,
            "supported_refusal_count": 0,
        },
        "tools": {
            "status": "passed",
            **{
                name: {
                    "status": "passed",
                    "numerator": 0 if name == "unnecessary_calls" else calls,
                    "denominator": calls,
                }
                for name in (
                    "valid_calls",
                    "expected_tool_selection",
                    "expected_arguments",
                    "unnecessary_calls",
                )
            },
        },
    }
    driver = {
        "tool_enabled": "model",
        "no_tool": "no_tool",
        "deterministic": "reference",
        "deterministic_fixture": "budget",
        "controlled_fixture": "refresh",
    }[condition]
    if condition == "no_tool":
        assessments["tools"] = {"status": "not_applicable"}
    elif condition == "deterministic":
        assessments = {"plan": assessments["plan"]}
    elif condition.endswith("fixture"):
        assessments = {"fixture": {"status": "passed", "checks": {"guard": True}}}
    observation: dict[str, object] = {
        "case_id": case_id,
        "condition": condition,
        "status": "completed",
        "evidence_class": evidence,
        "turns": (
            []
            if condition.endswith("fixture")
            else [{"status": "completed", "result": {}, "calls": []}]
        ),
    }
    if condition == "deterministic":
        observation.update(final_only=True, scope="structured_input_final_plan")
    elif condition.endswith("fixture"):
        observation.update(model_id=None, model_quality_applicable=False)
    return {
        "case_id": case_id,
        "repeat": repeat,
        "condition": condition,
        "driver": driver,
        "elapsed_seconds": 0.5,
        "status": "completed",
        "observation": observation,
        "assessments": assessments,
        "report": None,
    }


def _assessment(slot: dict[str, object], name: str) -> dict[str, object]:
    return _map(_map(slot["assessments"])[name])


def _groups(summary: dict[str, object]) -> list[dict[str, object]]:
    assert type(summary["groups"]) is list
    return cast(list[dict[str, object]], summary["groups"])


def _quality(group: dict[str, object]) -> dict[str, object]:
    return _map(_map(group["tasks"])["quality"])


def test_mixed_groups_preserve_helpers_and_literal_denominators() -> None:
    passed = _slot(calls=8)
    failed = _slot(repeat=2)
    tools = _assessment(failed, "tools")
    tools["status"] = "failed"
    _map(tools["valid_calls"]).update(status="failed", numerator=1)
    _map(tools["unnecessary_calls"]).update(status="failed", numerator=1)
    plan = _assessment(failed, "plan")
    plan.update(status="failed", constraint_violations=["budget_cap"])
    _map(plan["checks"])["budget_cap"] = False
    missing = _slot(repeat=3)
    missing["assessments"] = {}
    partial = _slot(repeat=4)
    partial["assessments"] = {}
    _map(partial["observation"])["status"] = "partial"
    live = _slot(evidence="real_bedrock", repeat=5)
    _assessment(live, "outcome")["status"] = "failed"
    no_tool = _slot(condition="no_tool", evidence="real_bedrock")
    reference = _slot(condition="deterministic")
    fixture = _slot(condition="deterministic_fixture", evidence="local_postgresql")
    controlled = _slot(condition="controlled_fixture", evidence="local_postgresql")
    slots = [
        live,
        partial,
        no_tool,
        fixture,
        failed,
        controlled,
        reference,
        missing,
        passed,
    ]
    summary = summarize_evaluation(slots)
    assert summary["total_slots"] == 9
    groups = _groups(summary)
    assert [(group["condition"], group["evidence_class"]) for group in groups] == [
        ("controlled_fixture", "local_postgresql"),
        ("deterministic", "deterministic_fake_provider"),
        ("deterministic_fixture", "local_postgresql"),
        ("no_tool", "real_bedrock"),
        ("tool_enabled", "deterministic_fake_provider"),
        ("tool_enabled", "real_bedrock"),
    ]
    for group in groups:
        records = [
            slot
            for slot in slots
            if slot["condition"] == group["condition"]
            and _map(slot["observation"])["evidence_class"] == group["evidence_class"]
        ]
        assert set(group) == {
            "condition",
            "evidence_class",
            "slot_count",
            "metrics",
            "tasks",
        }
        assert group["slot_count"] == len(records)
        assert group["metrics"] == summarize_metrics(records)
        assert group["tasks"] == summarize_tasks(records)
    fake = groups[4]
    assert _quality(fake) == {
        "scope": "language_task",
        "passed": 1,
        "failed": 2,
        "unassessed": 1,
        "not_applicable": 0,
        "all_applicable": 4,
        "assessed_denominator": 3,
        "conservative_rate": 0.25,
        "assessed_only_rate": 1 / 3,
        "coverage": 0.75,
    }
    assert _map(fake["tasks"])["execution"] == {
        "slot": {"completed": 4, "failed": 0, "partial": 0, "unassessed": 0},
        "observation": {"completed": 3, "failed": 0, "partial": 1, "unassessed": 0},
    }
    metrics = _map(fake["metrics"])
    valid = _map(_map(metrics["tool_metrics"])["valid_calls"])
    assert valid["counts"] == {"numerator": 9, "denominator": 10}
    assert valid["rate"] == 0.9
    assert valid["denominator"] == 2
    assert valid["pass_rate"] == 0.5
    assert valid["status_counts"] == {
        "passed": 1,
        "failed": 1,
        "unassessed": 2,
        "not_applicable": 0,
    }
    unnecessary = _map(_map(metrics["tool_metrics"])["unnecessary_calls"])
    assert unnecessary["counts"] == {"numerator": 1, "denominator": 10}
    assert unnecessary["rate"] == 0.1
    assert unnecessary["direction"] == "lower_is_better"
    budget = _map(_map(metrics["plan_checks"])["budget_cap"])
    assert budget["denominator"] == 2
    assert budget["pass_rate"] == 0.5
    for name in (
        "ingredient_coverage",
        "quantities",
        "sample_costs",
        "diet",
        "exclusions",
    ):
        check = _map(_map(metrics["plan_checks"])[name])
        assert check["denominator"] == 2
        assert check["pass_rate"] == 1.0
    assert metrics["known_failures"] == [
        {
            "case_id": "F01",
            "repeat": 2,
            "assessment": "tools",
            "checks": ["valid_calls", "unnecessary_calls"],
        },
        {
            "case_id": "F01",
            "repeat": 2,
            "assessment": "plan",
            "checks": ["budget_cap"],
        },
    ]
    assert _quality(groups[5])["conservative_rate"] == 0.0
    assert _quality(groups[3])["passed"] == 1
    assert _quality(groups[1])["scope"] == "structured_reference"
    for index in (0, 2):
        assert _quality(groups[index])["scope"] == "fixture_guard"
        assert _quality(groups[index])["passed"] == 1


def test_empty_input_and_single_partial_matrix() -> None:
    assert summarize_evaluation([]) == {"total_slots": 0, "groups": []}
    summary = summarize_evaluation([_slot()])
    assert set(summary) == {"total_slots", "groups"}
    assert summary["total_slots"] == 1
    assert len(_groups(summary)) == 1


@pytest.mark.parametrize("evidence", [None, "unknown", "sample", True, []])
def test_unknown_evidence_cannot_pass(evidence: object) -> None:
    group = _groups(summarize_evaluation([_slot(evidence=evidence)]))[0]
    assert group["evidence_class"] == "unknown"
    assert _quality(group)["passed"] == 0
    assert _quality(group)["unassessed"] == 1
    assert _quality(group)["coverage"] == 0.0


def test_missing_evidence_and_assessments_remain_unknown() -> None:
    slot = _slot()
    _map(slot["observation"]).pop("evidence_class")
    slot["assessments"] = {}
    group = _groups(summarize_evaluation([slot]))[0]
    assert group["evidence_class"] == "unknown"
    assert _quality(group)["conservative_rate"] == 0.0
    assert _quality(group)["assessed_only_rate"] is None
    metrics = _map(group["metrics"])
    for name in ("tools", "plan", "outcome", "claims"):
        row = _map(_map(metrics["assessments"])[name])
        assert row["status_counts"] == {
            "passed": 0,
            "failed": 0,
            "unassessed": 1,
            "not_applicable": 0,
        }
        assert row["denominator"] == 0
        assert row["pass_rate"] is None
    assert metrics["plan_checks"] == {}


@pytest.mark.parametrize("name", ["tools", "plan", "outcome", "claims"])
def test_missing_required_assessment_blocks_task_pass(name: str) -> None:
    slot = _slot()
    _map(slot["assessments"]).pop(name)
    quality = _quality(_groups(summarize_evaluation([slot]))[0])
    assert quality["unassessed"] == 1
    assert quality["passed"] == 0


def test_no_tool_may_omit_tools_assessment() -> None:
    slot = _slot(condition="no_tool")
    _map(slot["assessments"]).pop("tools")
    original = deepcopy(slot)
    group = _groups(summarize_evaluation([slot]))[0]
    assert _quality(group)["passed"] == 1
    metrics = _map(group["metrics"])
    rows = [_map(_map(metrics["assessments"])["tools"])]
    rows.extend(_map(value) for value in _map(metrics["tool_metrics"]).values())
    for row in rows:
        assert row["status_counts"] == {
            "passed": 0,
            "failed": 0,
            "unassessed": 0,
            "not_applicable": 1,
        }
        assert row["denominator"] == 0
        assert row["pass_rate"] is None
    for value in _map(metrics["tool_metrics"]).values():
        metric = _map(value)
        assert metric["counts"] == {"numerator": 0, "denominator": 0}
        assert metric["rate"] is None
    assert metrics["known_failures"] == []
    assert slot == original


@pytest.mark.parametrize("condition", ["tool_enabled", "no_tool"])
def test_plan_and_outcome_check_maps_are_optional(condition: str) -> None:
    slot = _slot(condition=condition)
    for name in ("plan", "outcome"):
        _assessment(slot, name).pop("checks")
    original = deepcopy(slot)
    group = _groups(summarize_evaluation([slot]))[0]
    assert _quality(group)["passed"] == 1
    metrics = _map(group["metrics"])
    assert metrics["plan_checks"] == {}
    assert metrics["known_failures"] == []
    assert metrics == summarize_metrics([slot])
    assert group["tasks"] == summarize_tasks([slot])
    assert slot == original


def test_zero_claim_refusals_and_unknown_claims_preserve_arithmetic() -> None:
    refusal = _slot(condition="no_tool")
    _assessment(refusal, "plan")["status"] = "not_applicable"
    _assessment(refusal, "claims").update(
        status="not_applicable",
        supported_count=0,
        assessed_count=0,
        supported_refusal_count=1,
    )
    only = _groups(summarize_evaluation([refusal]))[0]
    factual = _map(_map(_map(only["metrics"])["assessments"])["claims"])
    assert factual["scope"] == "public_output_only"
    assert factual["support_rate"] is None
    assert _quality(only)["passed"] == 1
    unknown = _slot(condition="no_tool", repeat=2)
    _assessment(unknown, "claims").update(
        status="unassessed",
        supported_count=2,
        assessed_count=3,
        unsupported_count=1,
        unknown_count=2,
    )
    group = _groups(summarize_evaluation([refusal, unknown]))[0]
    claims = _map(_map(_map(group["metrics"])["assessments"])["claims"])
    assert claims["counts"] == {
        "supported_count": 2,
        "assessed_count": 3,
        "unsupported_count": 1,
        "unknown_count": 2,
        "supported_refusal_count": 1,
    }
    assert claims["support_rate"] == 2 / 3
    assert claims["conservative_support_rate"] == 2 / 5
    assert _quality(group)["failed"] == 1


def test_clarification_uses_explicit_correctness_denominator() -> None:
    correct, wrong, unknown = [_slot(repeat=repeat) for repeat in (1, 2, 3)]
    for slot, status, value in (
        (correct, "passed", True),
        (wrong, "failed", False),
        (unknown, "unassessed", None),
    ):
        _assessment(slot, "outcome").update(
            status=status, clarification_required=True, clarification_correct=value
        )
    group = _groups(summarize_evaluation([correct, wrong, unknown]))[0]
    clarity = _map(_map(group["metrics"])["clarification_correctness"])
    assert clarity["denominator"] == 2
    assert clarity["pass_rate"] == 0.5
    assert clarity["status_counts"] == {
        "passed": 1,
        "failed": 1,
        "unassessed": 1,
        "not_applicable": 0,
    }


def test_unknown_claims_block_pass_without_known_failures() -> None:
    slot = _slot()
    _assessment(slot, "claims")["unknown_count"] = 1
    group = _groups(summarize_evaluation([slot]))[0]
    assert _quality(group)["unassessed"] == 1
    assert _quality(group)["passed"] == 0
    claims = _map(_map(_map(group["metrics"])["assessments"])["claims"])
    assert _map(claims["counts"])["unknown_count"] == 1
    assert claims["support_rate"] == 1.0
    assert claims["conservative_support_rate"] == 2 / 3


@pytest.mark.parametrize("evidence", ["deterministic_fake_provider", "real_bedrock"])
def test_duplicate_identity_is_rejected_across_evidence(evidence: str) -> None:
    slots = [_slot(), _slot(evidence=evidence)]
    original = deepcopy(slots)
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation(slots)
    assert slots == original


@pytest.mark.parametrize("field", ["case_id", "condition"])
@pytest.mark.parametrize("value", [None, "PRIVATE_IDENTITY_MARKER", True, []])
def test_observation_identity_must_match(field: str, value: object) -> None:
    slot = _slot()
    _map(slot["observation"])[field] = value
    original = deepcopy(slot)
    with pytest.raises(ValueError, match=_ERROR) as error:
        summarize_evaluation([slot])
    assert "PRIVATE_IDENTITY_MARKER" not in str(error.value)
    assert slot == original


@pytest.mark.parametrize("field", ["case_id", "condition"])
def test_missing_observation_identity_is_rejected(field: str) -> None:
    slot = _slot()
    _map(slot["observation"]).pop(field)
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


@pytest.mark.parametrize("case_id", ["F1", "F001", "f01", "F01\n", "F０１", " F01"])
def test_case_identifier_requires_exact_ascii_pattern(case_id: str) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([_slot(case_id=case_id)])


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1", None])
def test_repeat_requires_exact_positive_integer(value: object) -> None:
    slot = _slot()
    slot["repeat"] = value
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


@pytest.mark.parametrize("value", [None, (), {}, "slots", 1, [None], [[]], [True]])
def test_malformed_collections_and_slots_have_static_errors(value: object) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation(cast(list[dict[str, object]], value))


def test_collection_and_slot_subclasses_are_rejected() -> None:
    class Slots(list[dict[str, object]]):
        pass

    class Slot(dict[str, object]):
        pass

    for rows in (Slots([_slot()]), [Slot(_slot())]):
        with pytest.raises(ValueError, match=_ERROR):
            summarize_evaluation(rows)


@pytest.mark.parametrize("field", ["case_id", "condition"])
def test_observation_identity_rejects_spoofed_strings(field: str) -> None:
    class Spoofed(str):
        def __eq__(self, other: object) -> bool:
            raise AssertionError("spoofed identity compared")

    slot = _slot()
    _map(slot["observation"])[field] = Spoofed(cast(str, slot[field]))
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("plan", "final_turn"),
        ("outcome", "full_conversation"),
        ("claims", "hidden_reasoning"),
    ],
)
def test_applicable_assessment_scope_is_exact(name: str, scope: str) -> None:
    slot = _slot()
    _assessment(slot, name)["scope"] = scope
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])
    _assessment(slot, name).pop("scope")
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


@pytest.mark.parametrize("value", [True, -1, 3, 0.5, "1", None])
def test_invalid_tool_counts_are_rejected(value: object) -> None:
    slot = _slot()
    _map(_assessment(slot, "tools")["valid_calls"])["numerator"] = value
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


def test_incoherent_claim_counts_and_bool_checks_are_rejected() -> None:
    slot = _slot()
    _assessment(slot, "claims")["assessed_count"] = 1
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])
    slot = _slot()
    _map(_assessment(slot, "plan")["checks"])["quantities"] = 1
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


def test_zero_tool_denominator_has_no_rate() -> None:
    group = _groups(summarize_evaluation([_slot(calls=0)]))[0]
    tools = _map(_map(group["metrics"])["tool_metrics"])
    for value in tools.values():
        metric = _map(value)
        assert metric["counts"] == {"numerator": 0, "denominator": 0}
        assert metric["rate"] is None


@pytest.mark.parametrize("condition", ["deterministic_fixture", "controlled_fixture"])
@pytest.mark.parametrize("status", ["passed", "failed", "unassessed"])
def test_canonical_fixture_metadata_preserves_guard_status(
    condition: str, status: str
) -> None:
    slot = _slot(condition=condition, evidence="local_postgresql")
    checks = {"guard": True} if status == "passed" else {}
    _assessment(slot, "fixture").update(status=status, checks=checks)
    original = deepcopy(slot)
    group = _groups(summarize_evaluation([slot]))[0]
    observation = _map(slot["observation"])
    assert observation["turns"] == []
    assert observation["model_id"] is None
    assert observation["model_quality_applicable"] is False
    assert _quality(group)["scope"] == "fixture_guard"
    assert _quality(group)[status] == 1
    metrics = _map(group["metrics"])
    assert metrics == summarize_metrics([slot])
    assert group["tasks"] == summarize_tasks([slot])
    if status != "passed":
        assert metrics["fixture_checks"] == {}
    assert slot == original


@pytest.mark.parametrize("condition", ["deterministic_fixture", "controlled_fixture"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("turns", [{"status": "completed"}]),
        ("turns", None),
        ("turns", ()),
        ("turns", {}),
        ("model_id", "PRIVATE_MODEL_MARKER"),
        ("model_id", False),
        ("model_id", 0),
        ("model_quality_applicable", True),
        ("model_quality_applicable", 0),
        ("model_quality_applicable", None),
        ("model_quality_applicable", "false"),
    ],
)
def test_fixture_metadata_requires_canonical_values(
    condition: str, field: str, value: object
) -> None:
    slot = _slot(condition=condition, evidence="local_postgresql")
    _map(slot["observation"])[field] = value
    original = deepcopy(slot)
    with pytest.raises(ValueError, match=_ERROR) as error:
        summarize_evaluation([slot])
    assert "PRIVATE_MODEL_MARKER" not in str(error.value)
    assert slot == original


@pytest.mark.parametrize("condition", ["deterministic_fixture", "controlled_fixture"])
@pytest.mark.parametrize("field", ["turns", "model_id", "model_quality_applicable"])
def test_fixture_metadata_requires_canonical_fields(condition: str, field: str) -> None:
    slot = _slot(condition=condition, evidence="local_postgresql")
    _map(slot["observation"]).pop(field)
    original = deepcopy(slot)
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])
    assert slot == original


@pytest.mark.parametrize("condition", ["deterministic_fixture", "controlled_fixture"])
def test_fixture_turns_require_exact_list(condition: str) -> None:
    class Turns(list[object]):
        pass

    slot = _slot(condition=condition, evidence="local_postgresql")
    _map(slot["observation"])["turns"] = Turns()
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


@pytest.mark.parametrize("condition", ["deterministic_fixture", "controlled_fixture"])
@pytest.mark.parametrize("checks", [{}, {"guard": 1}])
def test_passed_fixture_requires_nonempty_boolean_checks(
    condition: str, checks: object
) -> None:
    slot = _slot(condition=condition, evidence="local_postgresql")
    _assessment(slot, "fixture")["checks"] = checks
    with pytest.raises(ValueError, match=_ERROR):
        summarize_evaluation([slot])


@pytest.mark.parametrize("field", ["final_only", "scope"])
def test_reference_needs_final_structured_scope(field: str) -> None:
    slot = _slot(condition="deterministic")
    _map(slot["observation"]).pop(field)
    quality = _quality(_groups(summarize_evaluation([slot]))[0])
    assert quality["scope"] == "structured_reference"
    assert quality["unassessed"] == 1


@pytest.mark.parametrize("location", ["observation", "turn"])
@pytest.mark.parametrize(
    ("flag", "state"), [("secret_leak", "failed"), ("capture_incomplete", "unassessed")]
)
def test_visible_capture_flags_prevent_task_pass(
    location: str, flag: str, state: str
) -> None:
    slot = _slot()
    observation = _map(slot["observation"])
    if location == "observation":
        observation[flag] = True
    else:
        observation["turns"] = [{"status": "completed", flag: True}]
    quality = _quality(_groups(summarize_evaluation([slot]))[0])
    assert quality[state] == 1
    assert quality["passed"] == 0


def test_input_unchanged_and_raw_fields_excluded() -> None:
    slot = _slot()
    slot["report"] = {"answer": "PRIVATE_REPORT", "exception": "PRIVATE_EXCEPTION"}
    slot["inputs"] = {"prompt": "PRIVATE_PROMPT"}
    slot["elapsed_seconds"] = "PRIVATE_TIMING"
    _map(slot["observation"])["turns"] = [
        {
            "status": "completed",
            "result": {"answer": "PRIVATE_ANSWER"},
            "calls": [{"arguments": "PRIVATE_ARGUMENTS"}],
            "telemetry": {"text": "PRIVATE_TELEMETRY"},
        }
    ]
    _assessment(slot, "plan")["reason"] = "PRIVATE_REASON"
    original = deepcopy(slot)
    summary = summarize_evaluation([slot])
    assert slot == original
    assert "PRIVATE_" not in repr(summary)
    group = _groups(summary)[0]
    assert _quality(group)["passed"] == 1
    _map(_map(group["metrics"])["plan_checks"]).clear()
    assert slot == original


def test_actual_reference_and_plan_score_producer_integration() -> None:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    corpus = _map(json.loads(path.read_text(encoding="utf-8")))
    scenarios = cast(list[dict[str, object]], corpus["scenarios"])
    case = next(case for case in scenarios if case["id"] == "F01")
    observation = observe_reference_case(case)
    assert observation["status"] == "completed"
    assert observation["final_only"] is True
    assert observation["user_turn_count_original"] == 2
    assert len(cast(list[object], observation["turns"])) == 1
    assessment = score_plan(case, observation)
    assert assessment["status"] == "passed"
    slot = _slot(condition="deterministic")
    slot["observation"] = observation
    slot["assessments"] = {"plan": assessment}
    original = deepcopy(slot)
    group = _groups(summarize_evaluation([slot]))[0]
    assert _quality(group)["scope"] == "structured_reference"
    assert _quality(group)["passed"] == 1
    metrics = _map(group["metrics"])
    assert _map(_map(metrics["assessments"])["claims"])["support_rate"] is None
    for value in _map(metrics["plan_checks"]).values():
        check = _map(value)
        assert check["denominator"] == 1
        assert check["pass_rate"] == 1.0
    assert slot == original
