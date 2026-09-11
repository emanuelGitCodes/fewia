from typing import cast

from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED
from app.evaluation_plan_inputs import fixture_plan
from app.services.grocery_planner import PlanningError

_EXCLUSION_PREFIX = "ingredient is excluded:"


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _typed_equal(observed: object, gold: object) -> bool:
    return type(observed) is type(gold) and observed == gold


def _observe(inputs: dict[str, object]) -> dict[str, object]:
    try:
        result = fixture_plan(inputs)
    except PlanningError as exc:
        if str(exc).startswith(_EXCLUSION_PREFIX):
            return {"accepted": False, "outcome": "exclusion_reject"}
        return {"accepted": False, "outcome": "diet_conflict"}
    except Exception:
        return {"outcome": "unexpected_error"}
    return {
        "accepted": result.accepted,
        "total_cents": result.total_cents,
        "outcome": "accept_plan",
    }


def _score(
    observed: dict[str, object], gold: dict[str, object]
) -> tuple[dict[str, bool], dict[str, object]]:
    checks: dict[str, bool] = {}
    for field in ("accepted", "total_cents"):
        if field in gold:
            checks[field] = _typed_equal(observed.get(field), gold[field])
    allowed = gold.get("allowed_outcomes")
    if isinstance(allowed, list):
        checks["outcome"] = observed.get("outcome") in allowed
    return checks, dict(observed)


def _gold(case: dict[str, object]) -> dict[str, object]:
    gold = dict(_as_map(case.get("expected")))
    if gold.get("total_cents") is None:
        gold.pop("total_cents", None)
    return gold


def evaluate_followup_case(case: dict[str, object]) -> dict[str, object]:
    inputs = _as_map(case.get("inputs"))
    checks, observed = _score(_observe(inputs), _gold(case))
    case_id = case.get("id")
    return {
        "case_id": case_id if type(case_id) is str else "invalid_case",
        "checks": checks,
        "observed": observed,
        "unassessed": list(UNASSESSED),
        "evidence_class": EVIDENCE_CLASS,
    }
