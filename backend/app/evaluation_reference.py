from copy import deepcopy

from app.agent.planning_tool import execute_plan
from app.evaluation_budget_inputs import _parse_date, fixture_budget
from app.evaluation_model_score import SUPPORTED_IDS
from app.evaluation_score_values import as_map

CONDITION = "deterministic_structured_input"
SCOPE_NOTE = (
    "The reference uses structured inputs. "
    "It does not measure language interpretation or persist evidence."
)
INPUTS_INVALID = "inputs are invalid"
_REQUEST_KEYS = (
    "budget_period",
    "plan_cap_cents",
    "diet",
    "pantry_ingredients",
    "ingredient_exclusions",
)


def _frame(case_id: str, status: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "condition": CONDITION,
        "status": status,
        "metrics_status": "unassessed",
        "scope_note": SCOPE_NOTE,
    }


def observe_reference_case(case: dict[str, object]) -> dict[str, object]:
    """Return a deterministic structured-input observation."""
    body = as_map(case)
    raw_id = None if body is None else body.get("id")
    if type(raw_id) is not str or raw_id not in SUPPORTED_IDS:
        return _frame("invalid_case", "unassessed")
    mapped = as_map(None if body is None else body.get("inputs"))
    failed = _frame(raw_id, "failed")
    failed["reason"] = INPUTS_INVALID
    raw_user = None if mapped is None else mapped.get("user_id")
    if mapped is None or type(raw_user) is not int:
        return failed
    inputs = mapped
    user_id = raw_user
    if user_id < 1:
        return failed
    meals_key = "followup_meals" if raw_id == "F05" else "meals"
    try:
        request: dict[str, object] = {"meals": deepcopy(inputs.get(meals_key))}
        for key in _REQUEST_KEYS:
            if key in inputs:
                request[key] = deepcopy(inputs[key])
        planned = execute_plan(
            request,
            fixture_budget(inputs),
            _parse_date(inputs.get("budget_period")),
            user_id=user_id,
        )
    except Exception:
        return failed
    plan = planned.get("plan")
    catalog: object = None
    if isinstance(plan, dict):
        catalog = plan.get("catalog_version")
    result = _frame(raw_id, "completed")
    result["request"] = planned.get("request")
    result["plan"] = plan
    result["budget"] = planned.get("budget")
    result["catalog_version"] = catalog
    return result
