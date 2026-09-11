from dataclasses import replace
from typing import cast

from app.domain.catalog import INGREDIENTS, Ingredient
from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED
from app.evaluation_plan_inputs import fixture_plan
from app.services.grocery_planner import PlanningError


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _typed_equal(observed: object, gold: object) -> bool:
    return type(observed) is type(gold) and observed == gold


def _catalog(case: dict[str, object]) -> dict[str, Ingredient] | None:
    behavior = _as_map(case.get("fixture_behavior"))
    ingredient_id = behavior.get("ingredient_id")
    if type(ingredient_id) is not str or ingredient_id not in INGREDIENTS:
        return None
    missing = replace(INGREDIENTS[ingredient_id], price_cents=None)
    return {**INGREDIENTS, ingredient_id: missing}


def _observe(
    inputs: dict[str, object], ingredients: dict[str, Ingredient] | None
) -> dict[str, object]:
    try:
        result = fixture_plan(inputs, ingredients=ingredients)
    except PlanningError:
        return {"accepted": False, "outcome": "diet_conflict"}
    except Exception:
        return {"outcome": "unexpected_error"}
    outcome = "incomplete_estimate" if result.total_cents is None else "accept_plan"
    return {
        "accepted": result.accepted,
        "total_cents": result.total_cents,
        "outcome": outcome,
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


def evaluate_missing_case(case: dict[str, object]) -> dict[str, object]:
    inputs = _as_map(case.get("inputs"))
    checks, observed = _score(_observe(inputs, _catalog(case)), _gold(case))
    case_id = case.get("id")
    return {
        "case_id": case_id if type(case_id) is str else "invalid_case",
        "checks": checks,
        "observed": observed,
        "unassessed": list(UNASSESSED),
        "evidence_class": EVIDENCE_CLASS,
    }
