from copy import deepcopy
from typing import cast

import pytest

from app.evaluation_summary_task import summarize_tasks
from app.evaluation_summary_task_validation import TaskFacts


def _slot(condition: str = "tool_enabled") -> dict[str, object]:
    assessments: dict[str, object] = {
        "plan": {
            "status": "passed",
            "scope": "final_plan",
            "checks": {"budget": True},
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
            "supported_count": 0,
            "assessed_count": 0,
            "unsupported_count": 0,
            "unknown_count": 0,
            "supported_refusal_count": 1,
        },
        "tools": {
            "status": "passed",
            **{
                name: {
                    "status": "passed",
                    "numerator": 0 if name == "unnecessary_calls" else 2,
                    "denominator": 2,
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
        assessments.pop("tools")
    elif condition == "deterministic":
        assessments = {"plan": assessments["plan"]}
    elif condition.endswith("fixture"):
        assessments = {"fixture": {"status": "passed", "checks": {"guard": True}}}
    return {
        "case_id": "F01",
        "repeat": 1,
        "condition": condition,
        "driver": driver,
        "elapsed_seconds": 0.1,
        "status": "completed",
        "observation": {
            "status": "completed",
            "evidence_class": "deterministic_fake_provider",
            "turns": (
                []
                if condition.endswith("fixture")
                else [{"status": "completed", "result": {}, "calls": []}]
            ),
            **(
                {"final_only": True, "scope": "structured_input_final_plan"}
                if condition == "deterministic"
                else {}
            ),
        },
        "assessments": assessments,
        "report": None,
    }


def _map(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _quality(slot: dict[str, object]) -> dict[str, object]:
    return _map(summarize_tasks([slot])["quality"])


@pytest.mark.parametrize("assessment", ["plan", "outcome", "claims", "tools"])
def test_completed_execution_does_not_imply_quality(assessment: str) -> None:
    slot = _slot()
    _map(_map(slot["assessments"])[assessment])["status"] = "failed"
    summary = summarize_tasks([slot])
    execution = _map(summary["execution"])
    assert _map(execution["slot"])["completed"] == 1
    assert _map(execution["observation"])["completed"] == 1
    assert _map(summary["quality"])["failed"] == 1


@pytest.mark.parametrize(
    "failure", ["assessment", "check", "slot", "execution", "partial", "turn", "leak"]
)
def test_known_failure_precedes_unknown(failure: str) -> None:
    slot = _slot()
    _map(slot["assessments"]).pop("claims")
    _map(slot["observation"])["capture_incomplete"] = True
    _map(slot["observation"])["evidence_class"] = "unknown"
    if failure == "assessment":
        _map(_map(slot["assessments"])["outcome"])["status"] = "failed"
    elif failure == "check":
        _map(_map(slot["assessments"])["plan"])["checks"] = {"budget": False}
    elif failure == "slot":
        slot["status"] = "failed"
    elif failure in ("execution", "partial"):
        _map(slot["observation"])["status"] = (
            "failed" if failure == "execution" else "partial"
        )
    elif failure == "turn":
        _map(slot["observation"])["turns"] = [{"status": "failed"}]
    else:
        _map(slot["observation"])["secret_leak"] = True
    assert _quality(slot)["failed"] == 1


@pytest.mark.parametrize("assessment", ["plan", "outcome", "claims", "tools"])
def test_missing_required_assessment_is_unassessed(assessment: str) -> None:
    slot = _slot()
    _map(slot["assessments"]).pop(assessment)
    assert _quality(slot)["unassessed"] == 1


def test_no_tool_does_not_require_tools() -> None:
    slot = _slot("no_tool")
    assert _quality(slot)["passed"] == 1
    _map(slot["assessments"])["tools"] = {"status": "failed"}
    assert _quality(slot)["passed"] == 1
    for name in ("plan", "claims"):
        _map(_map(slot["assessments"])[name])["status"] = "not_applicable"
    assert _quality(slot)["passed"] == 1


@pytest.mark.parametrize(
    "flag,state", [("capture_incomplete", "unassessed"), ("secret_leak", "failed")]
)
@pytest.mark.parametrize("location", ["observation", "turn"])
def test_observable_capture_flags(flag: str, state: str, location: str) -> None:
    slot = _slot()
    observation = _map(slot["observation"])
    if location == "observation":
        observation[flag] = True
    else:
        turn: dict[str, object] = {"status": "completed", "result": {}, "calls": []}
        turn[flag] = True
        observation["turns"] = [turn]
    assert _quality(slot)[state] == 1


@pytest.mark.parametrize(
    "condition,scope",
    [
        ("tool_enabled", "language_task"),
        ("no_tool", "language_task"),
        ("deterministic", "structured_reference"),
        ("deterministic_fixture", "fixture_guard"),
        ("controlled_fixture", "fixture_guard"),
    ],
)
def test_reference_and_fixture_quality_scopes(condition: str, scope: str) -> None:
    slot = _slot(condition)
    slot["report"] = {"status": "failed", "answer": "private report"}
    quality = _quality(slot)
    assert quality["scope"] == scope
    assert quality["passed"] == 1
    name = "fixture" if condition.endswith("fixture") else "plan"
    _map(slot["assessments"]).pop(name)
    assert _quality(slot)["unassessed"] == 1


def test_fixture_requires_nonempty_exact_boolean_checks() -> None:
    slot = _slot("controlled_fixture")
    fixture = _map(_map(slot["assessments"])["fixture"])
    fixture["checks"] = {}
    assert _quality(slot)["unassessed"] == 1
    fixture["checks"] = {"guard": 1}
    assert _quality(slot)["unassessed"] == 1


def test_conservative_rate_uses_literal_applicable_denominator() -> None:
    slots = [_slot() for _ in range(10)]
    for repeat, slot in enumerate(slots, start=1):
        slot["repeat"] = repeat
    _map(slots[-1]["assessments"]).pop("outcome")
    quality = _map(summarize_tasks(slots)["quality"])
    assert quality["all_applicable"] == 10
    assert quality["assessed_denominator"] == 9
    assert quality["conservative_rate"] == 0.9
    assert quality["assessed_only_rate"] == 1.0
    assert quality["coverage"] == 0.9
    assert quality["unassessed"] == 1


def test_zero_records_have_null_rates() -> None:
    summary = summarize_tasks([])
    quality = _map(summary["quality"])
    assert summary["condition"] is None
    assert summary["evidence_class"] is None
    assert quality["scope"] is None
    assert set(summary) == {"condition", "evidence_class", "execution", "quality"}
    assert _map(summary["execution"]) == {
        "slot": dict.fromkeys(("completed", "failed", "partial", "unassessed"), 0),
        "observation": dict.fromkeys(
            ("completed", "failed", "partial", "unassessed"), 0
        ),
    }
    for status in ("passed", "failed", "unassessed", "not_applicable"):
        assert quality[status] == 0
    assert quality["all_applicable"] == quality["assessed_denominator"] == 0
    assert quality["conservative_rate"] is None
    assert quality["assessed_only_rate"] is None
    assert quality["coverage"] is None


def test_input_is_unchanged_and_output_excludes_raw_data() -> None:
    slot = _slot()
    slot["report"] = {"answer": "private answer", "error": "private error"}
    _map(slot["observation"])["turns"] = [
        {
            "status": "completed",
            "result": {"answer": "private turn"},
            "calls": [],
            "raw_output": "private raw output",
            "error": "private turn error",
        }
    ]
    original = deepcopy(slot)
    summary = summarize_tasks([slot])
    assert slot == original
    assert "private" not in repr(summary)
    assert set(summary) == {"condition", "evidence_class", "execution", "quality"}


def test_real_and_fake_provider_quality_cannot_be_combined() -> None:
    real, fake = _slot(), _slot()
    fake["repeat"] = 2
    _map(real["observation"])["evidence_class"] = "real_bedrock"
    assert summarize_tasks([real])["evidence_class"] == "real_bedrock"
    assert summarize_tasks([fake])["evidence_class"] == "deterministic_fake_provider"
    with pytest.raises(ValueError, match="^Invalid evaluation summary input$"):
        summarize_tasks([real, fake])


@pytest.mark.parametrize("assessment", ["plan", "outcome", "claims", "tools"])
def test_invalid_assessment_status_cannot_pass(assessment: str) -> None:
    slot = _slot()
    _map(_map(slot["assessments"])[assessment])["status"] = "completed"
    assert _quality(slot)["unassessed"] == 1


@pytest.mark.parametrize("condition", ["tool_enabled", "no_tool"])
def test_language_task_requires_actual_turn_execution(condition: str) -> None:
    slot = _slot(condition)
    _map(slot["observation"])["turns"] = []
    assert _quality(slot)["unassessed"] == 1
    _map(slot["observation"])["turns"] = [{"status": "partial"}]
    assert _quality(slot)["failed"] == 1


@pytest.mark.parametrize("field", ["final_only", "scope", "turns"])
def test_reference_requires_final_plan_observation(field: str) -> None:
    slot = _slot("deterministic")
    _map(slot["observation"]).pop(field)
    assert _quality(slot)["unassessed"] == 1


@pytest.mark.parametrize("condition", ["deterministic", "controlled_fixture"])
def test_reference_and_fixture_execution_failure_affects_quality(
    condition: str,
) -> None:
    slot = _slot(condition)
    _map(slot["observation"])["status"] = "failed"
    assert _quality(slot)["failed"] == 1


@pytest.mark.parametrize("location", ["slot", "capture", "captured", "telemetry"])
def test_unapproved_capture_locations_are_ignored(location: str) -> None:
    slot = _slot()
    flags: dict[str, object] = {"secret_leak": True, "capture_incomplete": True}
    if location == "slot":
        slot.update(flags)
    else:
        observation = _map(slot["observation"])
        observation[location] = flags
        observation["turns"] = [{"status": "completed", location: flags}]
    assert _quality(slot)["passed"] == 1


@pytest.mark.parametrize("flag", ["secret_leak", "capture_incomplete"])
@pytest.mark.parametrize("location", ["observation", "turn"])
def test_capture_flags_require_exact_booleans(flag: str, location: str) -> None:
    slot = _slot()
    observation = _map(slot["observation"])
    if location == "observation":
        observation[flag] = 1
    else:
        observation["turns"] = [{"status": "completed", flag: 1}]
    assert _quality(slot)["unassessed"] == 1


def test_execution_counts_keep_slot_and_observation_separate() -> None:
    statuses = ("completed", "failed", "partial", "unassessed")
    slots = [_slot() for _ in statuses]
    for repeat, (slot, status) in enumerate(zip(slots, statuses, strict=True), start=1):
        slot["repeat"] = repeat
        slot["status"] = status
        _map(slot["observation"])["status"] = "completed"
    execution = _map(summarize_tasks(slots)["execution"])
    assert execution == {
        "slot": dict.fromkeys(statuses, 1),
        "observation": {"completed": 4, "failed": 0, "partial": 0, "unassessed": 0},
    }
    for slot, status in zip(slots, statuses, strict=True):
        slot["status"] = "completed"
        _map(slot["observation"])["status"] = status
    execution = _map(summarize_tasks(slots)["execution"])
    assert execution == {
        "slot": {"completed": 4, "failed": 0, "partial": 0, "unassessed": 0},
        "observation": dict.fromkeys(statuses, 1),
    }


def test_mixed_conditions_are_rejected() -> None:
    with pytest.raises(ValueError, match="^Invalid evaluation summary input$"):
        summarize_tasks([_slot(), _slot("no_tool")])


def test_duplicate_identity_is_rejected_without_mutation() -> None:
    slots = [_slot(), _slot()]
    original = deepcopy(slots)
    with pytest.raises(ValueError, match="^Invalid evaluation summary input$"):
        summarize_tasks(slots)
    assert slots == original


def test_distinct_case_identities_are_allowed() -> None:
    slots = [_slot(), _slot()]
    slots[1]["case_id"] = "F02"
    assert _map(summarize_tasks(slots)["quality"])["passed"] == 2


@pytest.mark.parametrize(
    "label,expected",
    [
        ("real_bedrock", "real_bedrock"),
        ("deterministic_fake_provider", "deterministic_fake_provider"),
        ("local_postgresql", "local_postgresql"),
        ("unknown", "unknown"),
        ("unrecognized", "unknown"),
        (None, "unknown"),
    ],
)
def test_evidence_label_comes_from_facts(label: object, expected: str) -> None:
    slot = _slot()
    _map(slot["observation"])["evidence_class"] = label
    summary = summarize_tasks([slot])
    assert summary["evidence_class"] == expected
    state = "unassessed" if expected == "unknown" else "passed"
    assert _map(summary["quality"])[state] == 1


@pytest.mark.parametrize("evidence", ["unknown", "local_postgresql"])
def test_evidence_groups_remain_distinct(evidence: str) -> None:
    first, second = _slot(), _slot()
    second["repeat"] = 2
    _map(second["observation"])["evidence_class"] = evidence
    with pytest.raises(ValueError, match="^Invalid evaluation summary input$"):
        summarize_tasks([first, second])


@pytest.mark.parametrize(
    "field", ["case_id", "repeat", "condition", "driver", "status"]
)
def test_invalid_metadata_uses_static_safe_error(field: str) -> None:
    slot = _slot()
    slot[field] = None
    with pytest.raises(ValueError, match="^Invalid evaluation summary input$"):
        summarize_tasks([slot])


def test_not_applicable_facts_are_excluded_from_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = ("passed", "failed", "unassessed", "not_applicable")
    supplied: list[dict[str, object]] = []

    def classify(slot: dict[str, object]) -> TaskFacts:
        supplied.append(slot)
        repeat = len(supplied)
        return TaskFacts(
            "F01",
            repeat,
            "tool_enabled",
            "deterministic_fake_provider",
            "model",
            "completed",
            "completed",
            "language_task",
            statuses[repeat - 1],
        )

    monkeypatch.setattr("app.evaluation_summary_task.classify_slot", classify)
    slots: list[dict[str, object]] = [{} for _ in statuses]
    quality = _map(summarize_tasks(slots)["quality"])
    assert len(supplied) == len(slots)
    assert all(left is right for left, right in zip(supplied, slots, strict=True))
    assert quality == {
        "scope": "language_task",
        **dict.fromkeys(statuses, 1),
        "all_applicable": 3,
        "assessed_denominator": 2,
        "conservative_rate": 1 / 3,
        "assessed_only_rate": 1 / 2,
        "coverage": 2 / 3,
    }


def test_unassessed_tasks_have_null_assessed_only_rate() -> None:
    slot = _slot()
    _map(slot["observation"])["evidence_class"] = "unknown"
    quality = _quality(slot)
    assert quality["assessed_denominator"] == 0
    assert quality["assessed_only_rate"] is None
    assert quality["conservative_rate"] == 0
    assert quality["coverage"] == 0
