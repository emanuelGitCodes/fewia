from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_protocol_fixture import as_map, period
from app.evaluation_protocol_observer import observe_variant

_KEYS = ("unknown_tool", "malformed", "planner_limit")
_KINDS = ("unknown", "malformed", "planner")


def _eq(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _listed(value: object, allowed: object) -> bool:
    if value == "unexpected_error" or not isinstance(allowed, list):
        return False
    return any(_eq(value, item) for item in allowed)


def _observe(case: dict[str, object]) -> dict[str, object]:
    inputs = as_map(case.get("inputs"))
    clock = period(inputs)
    budget = fixture_budget(inputs)
    prompt = case.get("prompt")
    if type(prompt) is not str:
        raise TypeError("prompt")
    return {
        key: observe_variant(case, kind, prompt, budget, clock)
        for key, kind in zip(_KEYS, _KINDS, strict=True)
    }


def evaluate_protocol_case(case: dict[str, object]) -> dict[str, object]:
    gold = as_map(case.get("expected"))
    try:
        observed = _observe(case)
    except Exception:
        miss: dict[str, object] = {"outcome": "unexpected_error", "accepted": False}
        observed = {key: dict(miss) for key in _KEYS}
    unknown = as_map(observed.get("unknown_tool"))
    malformed = as_map(observed.get("malformed"))
    planner = as_map(observed.get("planner_limit"))
    allowed = gold.get("allowed_outcomes")
    constraints = as_map(gold.get("constraint_results"))
    want = gold.get("accepted")
    turn = constraints.get("turn_bound")
    bound = constraints.get("planner_bound")
    after = bound + 1 if type(bound) is int else None
    accepted = _eq(unknown.get("accepted"), want)
    accepted = accepted and _eq(malformed.get("accepted"), want)
    accepted = accepted and _eq(planner.get("accepted"), want)
    failed = unknown.get("outcome") == "unexpected_error"
    failed = failed or malformed.get("outcome") == "unexpected_error"
    failed = failed or planner.get("outcome") == "unexpected_error"
    outcome = not failed and _listed(unknown.get("outcome"), allowed)
    outcome = outcome and _listed(malformed.get("outcome"), allowed)
    outcome = outcome and malformed.get("protocol_static") is True
    outcome = outcome and _eq(malformed.get("model_calls"), 1)
    rejected = unknown.get("unknown_tool_rejected") is True
    rejected = rejected and _eq(
        unknown.get("unknown_tool_rejected"),
        constraints.get("unknown_tool_rejected"),
    )
    turns = unknown.get("outcome") == "unknown_tool_reject"
    turns = turns and _eq(unknown.get("model_calls"), turn)
    turns = turns and _eq(turn, gold.get("max_model_turns"))
    limited = planner.get("outcome") == "planner_limit"
    limited = limited and _eq(planner.get("planner_revisions"), bound)
    limited = limited and _eq(planner.get("model_calls"), after)
    limited = limited and _eq(bound, gold.get("max_planner_revisions"))
    raw_id = case.get("id")
    case_id = "P04" if raw_id == "P04" else "invalid_case"
    report: dict[str, object] = {
        "case_id": case_id,
        "checks": {
            "accepted": accepted,
            "outcome": outcome,
            "unknown_tool_rejected": rejected,
            "max_model_turns": turns,
            "max_planner_revisions": limited,
        },
        "observed": observed,
        "unassessed": list(UNASSESSED),
        "evidence_class": EVIDENCE_CLASS,
    }
    target = gold.get("evidence_class")
    if type(target) is str and target == "real_bedrock":
        report["target_evidence_class"] = target
    return report
