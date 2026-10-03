from dataclasses import dataclass
from typing import cast

from app.evaluation_shapes import as_map
from app.evaluation_summary_task_assessments import assessment_status, combine_statuses

_ERROR = "invalid evaluation slot metadata"
_EXECUTION = ("completed", "failed", "partial", "unassessed")
_DRIVERS = {
    "tool_enabled": ("model",),
    "no_tool": ("no_tool",),
    "deterministic": ("reference",),
    "deterministic_fixture": ("budget", "meals", "followup", "missing"),
    "controlled_fixture": ("refresh", "handoff", "protocol", "duplicate"),
}


@dataclass(frozen=True)
class TaskFacts:
    case_id: str
    repeat: int
    condition: str
    evidence_class: str
    driver: str
    execution_status: str
    observation_status: str
    quality_scope: str
    quality_status: str


def _status(value: object, allowed: tuple[str, ...]) -> str:
    if type(value) is not str or value not in allowed:
        raise ValueError(_ERROR)
    return value


def _execution_quality(value: object) -> str:
    if type(value) is not str or value not in _EXECUTION:
        return "unassessed"
    if value in ("failed", "partial"):
        return "failed"
    return "passed" if value == "completed" else "unassessed"


def classify_slot(slot: dict[str, object]) -> TaskFacts:
    case_id, repeat = slot.get("case_id"), slot.get("repeat")
    if type(case_id) is not str or not case_id.strip():
        raise ValueError(_ERROR)
    if type(repeat) is not int or repeat <= 0:
        raise ValueError(_ERROR)
    condition = _status(slot.get("condition"), tuple(_DRIVERS))
    driver = _status(slot.get("driver"), _DRIVERS[condition])
    if any(type(slot.get(key)) is not dict for key in ("observation", "assessments")):
        raise ValueError(_ERROR)
    if "report" not in slot or type(slot["report"]) not in (dict, type(None)):
        raise ValueError(_ERROR)
    capture, assessments = as_map(slot["observation"]), as_map(slot["assessments"])
    execution = _status(slot.get("status"), _EXECUTION)
    observed = _status(capture.get("status"), _EXECUTION)
    scope = "language_task"
    names: tuple[str, ...] = ("plan", "outcome", "claims")
    if condition == "tool_enabled":
        names += ("tools",)
    elif condition == "deterministic":
        scope, names = "structured_reference", ("plan",)
    elif condition in ("deterministic_fixture", "controlled_fixture"):
        scope, names = "fixture_guard", ("fixture",)
    results = [_execution_quality(execution), _execution_quality(observed)]
    results.extend(assessment_status(assessments.get(name), name) for name in names)
    turns = capture.get("turns")
    records = [capture]
    if type(turns) is not list:
        results.append("unassessed")
    else:
        if not turns and scope == "language_task":
            results.append("unassessed")
        for turn in turns:
            if type(turn) is not dict:
                results.append("unassessed")
                continue
            record = cast(dict[str, object], turn)
            records.append(record)
            if any(type(key) is not str for key in record):
                results.append("unassessed")
            results.append(_execution_quality(record.get("status")))
    if condition == "deterministic" and not (
        capture.get("final_only") is True
        and capture.get("scope") == "structured_input_final_plan"
        and type(turns) is list
        and len(turns) == 1
        and type(turns[0]) is dict
        and as_map(turns[0]).get("status") == "completed"
    ):
        results.append("unassessed")
    for key, state in (("secret_leak", "failed"), ("capture_incomplete", "unassessed")):
        if any(record.get(key) is True for record in records):
            results.append(state)
    label = capture.get("evidence_class")
    labels = ("real_bedrock", "deterministic_fake_provider", "local_postgresql")
    evidence_class = label if type(label) is str and label in labels else "unknown"
    if evidence_class == "unknown":
        results.append("unassessed")
    return TaskFacts(
        case_id,
        repeat,
        condition,
        evidence_class,
        driver,
        execution,
        observed,
        scope,
        combine_statuses(results),
    )
