from typing import cast

from app.evaluation_reference import observe_reference_case
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
SCOPE = "deterministic_reference_final_plan"
CONDITION = "deterministic_structured_input"
SCOPE_NOTE = (
    "The reference uses structured inputs. "
    "It compares the final result only. "
    "It does not measure language understanding, earlier-turn quality, "
    "or persisted evidence."
)


def compare_reference(
    case: dict[str, object], observation: dict[str, object]
) -> dict[str, object]:
    """Compare a structured-input reference with the final completed result."""
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
            "scope": SCOPE,
            "condition": CONDITION,
            "status": "unassessed" if skipped else ("passed" if passed else "failed"),
            "passed": passed,
            "checks": checks,
            "metrics_status": "unassessed",
            "scope_note": SCOPE_NOTE,
        }
        if evidence is not None:
            body["evidence_class"] = evidence
        return body

    try:
        if case_id not in SUPPORTED_IDS:
            return out({"supported_case": False}, True)
        reference = mp(observe_reference_case(case))
        want_request = None if reference is None else mp(reference.get("request"))
        want_plan = None if reference is None else mp(reference.get("plan"))
        want_budget = None if reference is None else mp(reference.get("budget"))
        ref_ok = (
            reference is not None
            and reference.get("status") == "completed"
            and reference.get("case_id") == case_id
        )
        if (
            not ref_ok
            or want_request is None
            or want_plan is None
            or want_budget is None
        ):
            return out({"supported_case": True, "reference_complete": False}, True)
        messages = None if case_map is None else case_map.get("messages")
        count = len(cast(list[object], messages)) if type(messages) is list else 0
        results = None if obs is None else completed_results(obs.get("turns"), count)
        final = None if results is None else results[-1]
        request = None if final is None else mp(final.get("request"))
        plan = None if final is None else mp(final.get("plan"))
        budget = None if final is None else mp(final.get("budget"))
        accepted = want_plan.get("accepted")
        want = (
            "planned"
            if accepted is True
            else ("needs_revision" if accepted is False else None)
        )
        left = lines(None if plan is None else plan.get("lines"))
        right = lines(want_plan.get("lines"))
        checks: dict[str, bool] = {
            "supported_case": True,
            "observation_complete": obs is not None
            and obs.get("status") == "completed",
            "case_id_match": obs is not None and obs.get("case_id") == case_id,
            "evidence_allowed": evidence is not None,
            "turns_complete": results is not None,
            "final_status": want is not None and has(final, "status", want),
            "request_meals": has(request, "meals", want_request.get("meals")),
            "request_diet": has(request, "diet", want_request.get("diet")),
            "request_period": has(
                request, "budget_period", want_request.get("budget_period")
            ),
            "request_plan_cap": has(
                request, "plan_cap_cents", want_request.get("plan_cap_cents")
            ),
            "request_pantry": ids_eq(
                request, "pantry_ingredients", want_request.get("pantry_ingredients")
            ),
            "request_exclusions": ids_eq(
                request,
                "ingredient_exclusions",
                want_request.get("ingredient_exclusions"),
            ),
            "plan_accepted": has(plan, "accepted", want_plan.get("accepted")),
            "plan_total_cents": has(plan, "total_cents", want_plan.get("total_cents")),
            "plan_notice": has(plan, "notice", want_plan.get("notice")),
            "plan_catalog_version": has(
                plan, "catalog_version", want_plan.get("catalog_version")
            ),
            "budget_available_cents": has(
                budget, "available_cents", want_budget.get("available_cents")
            ),
            "budget_pending_cents": has(
                budget, "pending_cents", want_budget.get("pending_cents")
            ),
            "budget_stale": has(budget, "stale", want_budget.get("stale")),
            "budget_warnings": has(budget, "warnings", want_budget.get("warnings")),
            "plan_lines": left is not None and right is not None and eq(left, right),
        }
        return out(checks, False)
    except Exception:
        return out({}, True)
