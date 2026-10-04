from collections.abc import Callable
from copy import deepcopy
from time import monotonic
from typing import cast

from app.evaluation_budget import evaluate_budget_case
from app.evaluation_claim_score import score_claims
from app.evaluation_duplicate import evaluate_duplicate_case
from app.evaluation_followup import evaluate_followup_case
from app.evaluation_handoff import evaluate_handoff_case
from app.evaluation_matrix import EvaluationSlot
from app.evaluation_meals import evaluate_meal_case
from app.evaluation_missing import evaluate_missing_case
from app.evaluation_model import observe_model_case
from app.evaluation_no_tool import observe_no_tool_case
from app.evaluation_outcome_score import score_outcome
from app.evaluation_plan_score import score_plan
from app.evaluation_protocol import evaluate_protocol_case
from app.evaluation_reference import observe_reference_case
from app.evaluation_refresh import evaluate_refresh_case
from app.evaluation_runtime import EvaluationRuntime as EvaluationRuntime
from app.evaluation_runtime import fixture_result
from app.evaluation_tool_score import score_tools

_FIXTURES: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
    "budget": evaluate_budget_case,
    "meals": evaluate_meal_case,
    "followup": evaluate_followup_case,
    "missing": evaluate_missing_case,
    "refresh": evaluate_refresh_case,
    "handoff": evaluate_handoff_case,
    "protocol": evaluate_protocol_case,
}
_CONDITIONS = {
    "model": "tool_enabled",
    "no_tool": "no_tool",
    "reference": "deterministic",
    "budget": "deterministic_fixture",
    "meals": "deterministic_fixture",
    "followup": "deterministic_fixture",
    "missing": "deterministic_fixture",
    "refresh": "controlled_fixture",
    "handoff": "controlled_fixture",
    "protocol": "controlled_fixture",
    "duplicate": "controlled_fixture",
}
_SCORERS = {
    "tools": score_tools,
    "plan": score_plan,
    "outcome": score_outcome,
    "claims": score_claims,
}


def _boundary(slot: EvaluationSlot, status: str, reason: str) -> dict[str, object]:
    result = fixture_result(
        slot,
        {
            "case_id": slot.case_id,
            "status": status,
            "reason_code": reason,
            "checks": {},
            "evidence_class": "unknown",
            "evidence_paths": [],
        },
    )
    cast(dict[str, object], result["observation"])["reason_code"] = reason
    fixture = cast(dict[str, object], result["assessments"])
    cast(dict[str, object], fixture["fixture"])["reason_code"] = reason
    return result


def _execute(slot: EvaluationSlot, runtime: EvaluationRuntime) -> dict[str, object]:
    if slot.driver not in _CONDITIONS or slot.condition != _CONDITIONS[slot.driver]:
        raise ValueError
    case = deepcopy(slot.case)
    if slot.driver in ("model", "no_tool", "reference"):
        case.pop("expected", None)
        if slot.driver == "reference":
            observation = observe_reference_case(case)
        else:
            observer = (
                observe_model_case if slot.driver == "model" else observe_no_tool_case
            )
            observation = observer(
                case,
                runtime.provider_factory(),
                evidence_class=runtime.evidence_class,
                model_id=runtime.model_id,
            )
        status = observation["status"]
        if slot.driver == "reference" and status == "not_applicable":
            observation = {**observation, "status": "unassessed"}
        if observation["status"] not in (
            "completed",
            "failed",
            "partial",
            "unassessed",
        ):
            raise ValueError
        scorers = {"plan": score_plan} if slot.driver == "reference" else _SCORERS
        assessments = {
            name: scorer(deepcopy(slot.case), deepcopy(observation))
            for name, scorer in scorers.items()
        }
        return {"observation": observation, "assessments": assessments, "report": None}
    if slot.driver == "duplicate":
        if not runtime.database_url or not runtime.endpoint:
            return _boundary(slot, "unassessed", "missing_local_services")
        report = evaluate_duplicate_case(
            case, database_url=runtime.database_url, endpoint=runtime.endpoint
        )
    else:
        report = _FIXTURES[slot.driver](case)
    return fixture_result(slot, report)


def run_slot(slot: EvaluationSlot, runtime: EvaluationRuntime) -> dict[str, object]:
    started = monotonic()
    try:
        result = _execute(slot, runtime)
    except Exception:  # noqa: BLE001
        result = _boundary(slot, "failed", "slot_execution_failed")
    elapsed = monotonic() - started
    observation = cast(dict[str, object], result["observation"])
    return {
        "case_id": slot.case_id,
        "repeat": slot.repeat,
        "condition": slot.condition,
        "driver": slot.driver,
        "status": observation["status"],
        "elapsed_seconds": elapsed,
        **result,
    }
