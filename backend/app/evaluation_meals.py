from typing import cast

from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED
from app.evaluation_plan_inputs import fixture_plan
from app.services.grocery_planner import PlanningError

_INPUT_KEYS = frozenset({"diet"})
_GOLD_KEYS = frozenset({"accepted", "total_cents", "allowed_outcomes"})


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
    except PlanningError:
        return {"accepted": False, "outcome": "diet_conflict"}
    except Exception:  # noqa: BLE001
        return {"outcome": "unexpected_error"}
    return {
        "accepted": result.accepted,
        "total_cents": result.total_cents,
        "outcome": "accept_plan",
    }


def _score(
    prefix: str, observed: dict[str, object], gold: dict[str, object]
) -> tuple[dict[str, bool], dict[str, object]]:
    checks: dict[str, bool] = {}
    labeled = {f"{prefix}{field}": value for field, value in observed.items()}
    for field in ("accepted", "total_cents"):
        if field in gold:
            checks[f"{prefix}{field}"] = _typed_equal(observed.get(field), gold[field])
    allowed = gold.get("allowed_outcomes")
    if isinstance(allowed, list):
        checks[f"{prefix}outcome"] = observed.get("outcome") in allowed
    return checks, labeled


def _merge(
    case: dict[str, object], variant: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    inputs = dict(_as_map(case.get("inputs")))
    gold = dict(_as_map(case.get("expected")))
    for key, value in variant.items():
        if key in _INPUT_KEYS:
            inputs[key] = value
        if key in _GOLD_KEYS:
            gold[key] = value
    if variant.get("accepted") is False and "total_cents" not in variant:
        gold.pop("total_cents", None)
    return inputs, gold


def evaluate_meal_case(case: dict[str, object]) -> dict[str, object]:
    checks: dict[str, bool] = {}
    observed: dict[str, object] = {}
    variants = case.get("variants")
    if isinstance(variants, list) and variants:
        for item in variants:
            variant = _as_map(item)
            variant_id = variant.get("id")
            prefix = f"{variant_id}." if type(variant_id) is str else ""
            inputs, gold = _merge(case, variant)
            part_checks, part_observed = _score(prefix, _observe(inputs), gold)
            checks.update(part_checks)
            observed.update(part_observed)
    else:
        inputs, gold = _merge(case, {})
        checks, observed = _score("", _observe(inputs), gold)
    case_id = case.get("id")
    return {
        "case_id": case_id if type(case_id) is str else "invalid_case",
        "checks": checks,
        "observed": observed,
        "unassessed": list(UNASSESSED),
        "evidence_class": EVIDENCE_CLASS,
    }
