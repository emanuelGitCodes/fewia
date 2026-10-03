from typing import cast

from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_plan_facts import plan_integrity
from app.evaluation_shapes import as_map as mp
from app.evaluation_shapes import typed_equal as eq
from app.evaluation_shapes import valid_public_result

_FINAL_ONLY = ("F01", "F02", "F05", "X04", "A01")
_CONDITIONS = ("deterministic", "tool_enabled", "no_tool")
_PAYLOADS = ("plan", "request", "budget")
_REQUEST = (
    "meals diet budget_period plan_cap_cents pantry_ingredients ingredient_exclusions"
).split()
_BUDGET = (
    "monthly_limit_cents posted_cents pending_cents remaining_cents "
    "available_cents stale"
).split()


def _ids(value: object) -> set[str] | None:
    if type(value) is not list:
        return None
    items = cast(list[object], value)
    if any(type(item) is not str for item in items):
        return None
    ids = set(cast(list[str], items))
    return ids if len(ids) == len(items) else None


def _lines(value: object) -> dict[str, object] | None:
    if type(value) is not list:
        return None
    lines: dict[str, object] = {}
    for item in cast(list[object], value):
        line = mp(item)
        key = line.get("ingredient_id")
        if type(key) is not str or key in lines:
            return None
        lines[key] = line
    return lines


def _has(mapping: dict[str, object], key: str, value: object) -> bool:
    return key in mapping and eq(mapping[key], value)


def score_plan(
    case: dict[str, object], observation: dict[str, object]
) -> dict[str, object]:
    case, observation = mp(case), mp(observation)
    inputs, expected = mp(case.get("inputs")), mp(case.get("expected"))
    checks: dict[str, bool] = {}

    def report(status: str, reason: str | None = None) -> dict[str, object]:
        result: dict[str, object] = {
            "status": status,
            "scope": "final_plan",
            "checks": checks,
            "constraint_violations": [key for key in checks if not checks[key]],
            "scope_note": "Final request and plan only. Prior-turn language and "
            "durable evidence ownership are unassessed.",
        }
        if reason is not None:
            result["reason"] = reason
        return result

    messages = case.get("messages")
    if not inputs or not expected or type(messages) is not list or not messages:
        return report("unassessed", "Scenario context is missing.")
    count = len(cast(list[object], messages))
    original_count = observation.get("user_turn_count_original", count)
    condition = observation.get("condition")
    checks["condition"] = type(condition) is str and condition in _CONDITIONS
    checks["case_identity"] = type(case.get("id")) is str and eq(
        observation.get("case_id"), case["id"]
    )
    checks["observation_complete"] = observation.get("status") == "completed"
    final_only = observation.get("final_only", False)
    checks["final_scope"] = type(final_only) is bool and (
        final_only is False
        or (
            condition == "deterministic"
            and case.get("id") in _FINAL_ONLY
            and eq(observation.get("user_turn_count_original"), count)
        )
    )
    checks["user_turn_count_original"] = eq(original_count, count)
    raw_turns = observation.get("turns")
    turns = cast(list[object], raw_turns) if type(raw_turns) is list else []
    required_count = 1 if final_only is True else count
    checks["turns_complete"] = len(turns) == required_count and all(
        mp(turn).get("status") == "completed"
        and valid_public_result(mp(turn).get("result"))
        for turn in turns
    )
    if not all(checks.values()):
        return report("failed", "Observation is invalid or incomplete.")
    final = mp(mp(turns[-1]).get("result"))
    plan, request, budget = (mp(final.get(key)) for key in _PAYLOADS)
    required = (
        "lines" in expected
        or "missing_price_ingredient" in expected
        or type(expected.get("total_cents")) is int
        or (expected.get("accepted") is True and bool(inputs.get("meals")))
    )
    if not required:
        checks["no_unexpected_plan"] = final.get("plan") is None
        return report(
            "not_applicable" if checks["no_unexpected_plan"] else "failed",
            "No final plan is expected; use score_outcome for clarification/refusal.",
        )
    checks["final_plan_present"] = bool(plan and request and budget)
    for key in _REQUEST:
        source = "followup_meals" if key == "meals" and case.get("id") == "F05" else key
        left, right = request.get(key), inputs.get(source)
        match = _has(request, key, right)
        if key in ("pantry_ingredients", "ingredient_exclusions"):
            match = _ids(left) is not None and _ids(left) == _ids(right)
        checks[f"request_{key}"] = source in inputs and match
    for key in ("accepted", "total_cents", "notice"):
        checks[f"expected_{key}"] = key in expected and _has(plan, key, expected[key])
    catalog = mp(mp(expected.get("evidence_ids")).get("when_plan_returned"))
    version = expected.get("catalog_version", catalog.get("catalog_version"))
    checks["expected_catalog_version"] = type(version) is str and _has(
        plan, "catalog_version", version
    )
    for key in _BUDGET:
        if key in expected:
            checks[f"expected_budget_{key}"] = _has(budget, key, expected[key])
    try:
        scenario_budget = fixture_budget(inputs)
    except (TypeError, ValueError):
        checks["budget_inputs"] = False
    else:
        checks["budget_inputs"] = True
        checks["budget_arithmetic"] = _has(
            budget, "available_cents", scenario_budget.available_cents
        )
        checks["budget_stale"] = _has(budget, "stale", scenario_budget.stale)
    if "lines" in expected:
        actual, golden = _lines(plan.get("lines")), _lines(expected["lines"])
        checks["golden_lines"] = (
            actual is not None and golden is not None and eq(actual, golden)
        )
    checks.update(
        {f"integrity_{key}": value for key, value in plan_integrity(final).items()}
    )
    return report("passed" if all(checks.values()) else "failed")
