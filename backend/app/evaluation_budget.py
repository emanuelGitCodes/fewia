from typing import cast

from app.domain.budget import StaleSpendingError
from app.evaluation_budget_inputs import fixture_budget

EVIDENCE_CLASS = "deterministic_fake_provider"
PERIOD_ERROR = "spending.period must match the current New York month"
BUDGET_OUTCOMES = frozenset(
    {"accept_budget", "period_mismatch", "stale_reject", "stale_cap_accept"}
)
UNASSESSED = (
    "tool_selection",
    "tool_arguments",
    "unnecessary_calls",
    "claim_support",
    "ingredient_coverage",
    "constraint_violations",
    "completion",
    "recovery",
    "cost",
    "latency",
    "p50_latency",
    "p95_latency",
    "token_use",
    "estimated_cost",
    "provider_calls",
    "model_quality",
    "live_providers",
    "local_postgresql",
    "plaid_sandbox",
    "live_instacart_development",
    "real_bedrock",
    "deployed_aws",
    "local_react_typescript_chat",
    "fastapi",
    "worker",
    "floci_sqs",
    "floci_s3",
    "plan_acceptance",
    "plan_rows",
    "hidden_reasoning",
)
_INPUT_KEYS = frozenset(
    {
        "now",
        "budget_period",
        "spending_period",
        "monthly_limit_cents",
        "posted_cents",
        "pending_cents",
        "plan_cap_cents",
        "spending_refreshed_at",
    }
)
_GOLD_KEYS = frozenset(
    {"available_cents", "pending_cents", "stale", "allowed_outcomes"}
)


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _typed_equal(observed: object, gold: object) -> bool:
    return type(observed) is type(gold) and observed == gold


def _observe(inputs: dict[str, object]) -> dict[str, object]:
    try:
        result = fixture_budget(inputs)
    except StaleSpendingError:
        return {"outcome": "stale_reject"}
    except ValueError as exc:
        if str(exc) == PERIOD_ERROR:
            return {"outcome": "period_mismatch"}
        return {"outcome": "unexpected_error"}
    except Exception:
        return {"outcome": "unexpected_error"}
    outcome = "stale_cap_accept" if result.stale else "accept_budget"
    return {
        "available_cents": result.available_cents,
        "pending_cents": result.pending_cents,
        "stale": result.stale,
        "outcome": outcome,
    }


def _score(
    prefix: str, observed: dict[str, object], gold: dict[str, object]
) -> tuple[dict[str, bool], dict[str, object]]:
    checks: dict[str, bool] = {}
    labeled = {f"{prefix}{field}": value for field, value in observed.items()}
    for field in ("available_cents", "pending_cents", "stale"):
        if field in gold:
            checks[f"{prefix}{field}"] = _typed_equal(observed.get(field), gold[field])
    allowed = gold.get("allowed_outcomes")
    if isinstance(allowed, list):
        budget_allowed = [item for item in allowed if item in BUDGET_OUTCOMES]
        if budget_allowed:
            checks[f"{prefix}outcome"] = observed.get("outcome") in budget_allowed
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
    return inputs, gold


def evaluate_budget_case(case: dict[str, object]) -> dict[str, object]:
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
