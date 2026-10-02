from app.agent.chat_answer import render_public_answer
from app.agent.chat_messages import build_chat_result
from app.agent.planning_tool import execute_plan
from app.evaluation_inputs import (
    INVALID_INPUT_ERROR,
    STALE_INPUT_ERROR,
    EvaluationInputError,
    prepare_case,
)
from app.evaluation_shapes import as_map, valid_public_result

CONDITION = "deterministic"
SUPPORTED_IDS = frozenset({"F01", "F02", "F05", "X04", "A01"})
SCOPE_NOTE = (
    "Only the final structured request ran. No earlier user turns ran. "
    "This comparison does not measure language understanding. "
    "No durable evidence store ran."
)
_REQUEST_KEYS = ("diet", "pantry_ingredients", "ingredient_exclusions")


def _frame(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "condition": CONDITION,
        "evidence_class": "deterministic_fake_provider",
        "scope": "structured_input_final_plan",
        "scope_note": SCOPE_NOTE,
        "status": "failed",
        "reason": INVALID_INPUT_ERROR,
        "final_only": False,
        "user_turn_count_original": None,
        "turns": [],
        "final": None,
        "calls": [],
        "tool_results": [],
        "provider_calls": 0,
        "usage": None,
        "snapshots": [],
        "evidence_revision_id": None,
        "evidence_path": "deterministic_domain",
    }


def observe_reference_case(case: dict[str, object]) -> dict[str, object]:
    """Observe one final plan from validated structured inputs."""
    raw_id = as_map(case).get("id")
    case_id = raw_id if type(raw_id) is str else "invalid_case"
    observation = _frame(case_id)
    if type(raw_id) is str and raw_id.strip() and raw_id not in SUPPORTED_IDS:
        observation.update(
            status="not_applicable", reason="case is outside the deterministic cohort"
        )
        return observation
    try:
        context = prepare_case(case)
        inputs = context.inputs
        request: dict[str, object] = {
            "meals": inputs.get(
                "followup_meals" if context.case_id == "F05" else "meals"
            ),
            "budget_period": context.period.isoformat(),
            "plan_cap_cents": context.plan_cap_cents,
        }
        request.update({key: inputs[key] for key in _REQUEST_KEYS if key in inputs})
        candidate = execute_plan(
            request,
            context.budget,
            context.period,
            user_id=context.user_id,
            spending_source="fixture",
        )
        plan = as_map(candidate.get("plan"))
        if plan.get("accepted") is True:
            status = "planned"
        elif plan.get("accepted") is False:
            status = (
                "clarification" if plan.get("total_cents") is None else "needs_revision"
            )
        else:
            raise ValueError
        final = build_chat_result(
            status, render_public_answer(candidate), candidate, "fixture", [], 0, 0
        )
        if not valid_public_result(final) or final["evidence_revision_id"] is not None:
            raise ValueError
    except EvaluationInputError as exc:
        if str(exc) == STALE_INPUT_ERROR:
            observation["reason"] = STALE_INPUT_ERROR
        return observation
    except Exception:
        observation["reason"] = "deterministic planning failed"
        return observation
    observation.update(
        status="completed",
        reason=None,
        final_only=True,
        user_turn_count_original=len(context.messages),
        turns=[
            {
                "status": "completed",
                "result": final,
                "calls": [],
                "tool_results": [],
                "provider_calls": 0,
                "usage": None,
                "snapshots": [],
                "evidence_path": "deterministic_domain",
            }
        ],
        final=final,
    )
    return observation
