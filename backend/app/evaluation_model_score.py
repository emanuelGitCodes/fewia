from typing import cast

from app.evaluation_score_values import (
    as_map as mp,
)
from app.evaluation_score_values import (
    completed_results,
)
from app.evaluation_score_values import (
    has_value as has,
)
from app.evaluation_score_values import (
    id_lists_equal as ids_eq,
)
from app.evaluation_score_values import (
    lines_by_id as lines,
)
from app.evaluation_score_values import (
    typed_equal as eq,
)

SUPPORTED_IDS = frozenset({"F01", "F02", "F05", "X04", "A01"})
_EVIDENCE = frozenset({"deterministic_fake_provider", "real_bedrock"})
_LINE = (
    "ingredient_id",
    "name",
    "unit",
    "quantity",
    "packages",
    "cost_cents",
    "from_pantry",
)


def _gold_lines(value: object) -> dict[str, dict[str, object]] | None:
    index = lines(value)
    if index is None:
        return None
    for body in index.values():
        if any(key not in body for key in _LINE):
            return None
    return index


def score_model_plan(
    case: dict[str, object], observation: dict[str, object]
) -> dict[str, object]:
    case_map, obs = mp(case), mp(observation)
    raw_id = None if case_map is None else case_map.get("id")
    supported = type(raw_id) is str and raw_id in SUPPORTED_IDS
    case_id = raw_id if supported else "invalid_case"
    label = None if obs is None else obs.get("evidence_class")
    evidence = label if type(label) is str and label in _EVIDENCE else None

    def out(checks: dict[str, bool], skipped: bool) -> dict[str, object]:
        passed = not skipped and bool(checks) and all(checks.values())
        body: dict[str, object] = {
            "case_id": case_id,
            "scope": "structural_plan",
            "status": "unassessed" if skipped else ("passed" if passed else "failed"),
            "passed": passed,
            "checks": checks,
            "metrics_status": "unassessed",
        }
        if evidence is not None:
            body["evidence_class"] = evidence
        return body

    if case_id not in SUPPORTED_IDS:
        return out({"supported_case": False}, True)
    gold = None if case_map is None else mp(case_map.get("expected"))
    inputs = None if case_map is None else mp(case_map.get("inputs"))
    messages = None if case_map is None else case_map.get("messages")
    if gold is None or inputs is None or obs is None:
        return out({"supported_case": True, "observation_complete": False}, False)
    n = len(cast(list[object], messages)) if type(messages) is list else 0
    results = completed_results(obs.get("turns"), n)
    final = None if results is None else results[-1]
    plan = None if final is None else mp(final.get("plan"))
    request = None if final is None else mp(final.get("request"))
    budget = None if final is None else mp(final.get("budget"))
    accepted = gold.get("accepted")
    want = (
        "planned"
        if accepted is True
        else ("needs_revision" if accepted is False else None)
    )
    meal_key = "followup_meals" if case_id == "F05" else "meals"
    found = False
    trace = None if final is None else final.get("tool_trace")
    if type(trace) is list:
        for item in cast(list[object], trace):
            body = mp(item) or {}
            hit = body.get("tool") == "plan_groceries"
            found = found or (hit and body.get("outcome") == "success")
    turns = None if final is None else final.get("model_turns")
    revs = None if final is None else final.get("planner_revisions")
    meals = inputs[meal_key] if meal_key in inputs else None
    evid = mp(gold.get("evidence_ids")) or {}
    when = mp(evid.get("when_plan_returned")) or {}
    catalog = when.get("catalog_version")
    checks: dict[str, bool] = {
        "supported_case": True,
        "observation_complete": obs.get("status") == "completed",
        "case_id_match": obs.get("case_id") == case_id,
        "evidence_allowed": evidence is not None,
        "turns_complete": results is not None,
        "final_status": want is not None and has(final, "status", want),
        "request_meals": has(request, "meals", meals),
        "request_diet": has(request, "diet", inputs.get("diet")),
        "request_period": has(request, "budget_period", inputs.get("budget_period")),
        "request_plan_cap": "plan_cap_cents" in inputs
        and has(request, "plan_cap_cents", inputs["plan_cap_cents"]),
        "request_pantry": ids_eq(
            request, "pantry_ingredients", inputs.get("pantry_ingredients")
        ),
        "request_exclusions": ids_eq(
            request, "ingredient_exclusions", inputs.get("ingredient_exclusions")
        ),
        "planner_trace_success": found,
        "model_turns": type(turns) is int and 1 <= turns <= 8,
        "planner_revisions": type(revs) is int and 1 <= revs <= 3,
        "plan_accepted": type(accepted) is bool and has(plan, "accepted", accepted),
        "plan_total_cents": type(gold.get("total_cents")) is int
        and has(plan, "total_cents", gold["total_cents"]),
        "plan_notice": type(gold.get("notice")) is str
        and has(plan, "notice", gold["notice"]),
        "plan_catalog_version": type(catalog) is str
        and has(plan, "catalog_version", catalog),
    }
    if "available_cents" in gold:
        available = gold["available_cents"]
        checks["budget_available_cents"] = type(available) is int and has(
            budget, "available_cents", available
        )
    if "lines" in gold:
        left = lines(None if plan is None else plan.get("lines"))
        right = _gold_lines(gold["lines"])
        checks["plan_lines"] = (
            left is not None and right is not None and eq(left, right)
        )
    return out(checks, False)
