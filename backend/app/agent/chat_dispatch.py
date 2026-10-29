from collections.abc import Callable
from datetime import date
from typing import get_args

from app.agent import chat_messages as msgs
from app.agent.budget_tool import (
    TOOL_NAME as BUDGET_TOOL_NAME,
)
from app.agent.budget_tool import (
    BudgetToolError,
    execute_budget_summary,
)
from app.agent.catalog_tool import (
    TOOL_NAME as CATALOG_TOOL_NAME,
)
from app.agent.catalog_tool import CatalogToolError, execute_catalog_search
from app.agent.plan_tools import (
    GET_MEAL_TOOL,
    GET_PLAN_TOOL,
    PlanToolError,
    execute_get_meal,
    execute_get_plan,
)
from app.agent.planning_tool import TOOL_NAME, PlanningToolError, execute_plan
from app.agent.substitute_tool import (
    SUBSTITUTE_TOOL,
    SubstituteToolError,
    execute_substitute,
)
from app.domain.budget import BudgetResult, SpendingSource
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS, Diet
from app.domain.plan_revision import PlanRevisionInput

EvidenceRecorder = Callable[[dict[str, object]], str]


def _is_revision_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all("0" <= char <= "9" or "a" <= char <= "f" for char in value)
    )


def _revision_index(trace: list[dict[str, object]]) -> int:
    return 1 + sum(1 for item in trace if item.get("tool") == TOOL_NAME)


def _usd_cents_display(cents: object) -> str | None:
    if type(cents) is not int:
        return None
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    dollars = magnitude // 100
    fraction = magnitude % 100
    return f"USD {sign}${dollars}.{fraction:02d}"


def _money_display(payload: dict[str, object]) -> dict[str, str]:
    plan = payload.get("plan")
    budget = payload.get("budget")
    total = None if not isinstance(plan, dict) else plan.get("total_cents")
    available = None if not isinstance(budget, dict) else budget.get("available_cents")
    pending = None if not isinstance(budget, dict) else budget.get("pending_cents")
    total_text = _usd_cents_display(total)
    available_text = _usd_cents_display(available)
    pending_text = _usd_cents_display(pending)
    display: dict[str, str] = {
        "total": "unknown" if total_text is None else total_text,
    }
    if available_text is not None:
        display["available"] = available_text
    if pending_text is not None:
        display["pending"] = pending_text
    return display


def _llm_tool_payload(payload: dict[str, object]) -> dict[str, object]:
    wrapped = dict(payload)
    wrapped["currency"] = "USD"
    wrapped["money_unit"] = "cents"
    wrapped["money_display"] = _money_display(payload)
    return wrapped


def _entry(
    *,
    tool: str,
    outcome: str,
    tool_use_id: str,
    sequence: int,
    revision_index: int | None,
    evidence_id: object = None,
    evidence_revision_id: object = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": tool,
        "outcome": outcome,
        "tool_use_id": tool_use_id,
        "sequence": sequence,
        "revision_index": revision_index,
    }
    if isinstance(evidence_id, str):
        entry["evidence_id"] = evidence_id
    if isinstance(evidence_revision_id, str):
        entry["evidence_revision_id"] = evidence_revision_id
    return entry


def _dispatch_budget(
    call: msgs.ToolCall,
    budget: BudgetResult,
    period: date,
    source: SpendingSource,
    trace: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    payload: dict[str, object] | None
    try:
        payload = execute_budget_summary(
            call.tool_input, budget, period, spending_source=source
        )
    except BudgetToolError:
        payload = None
    trace.append(
        _entry(
            tool=BUDGET_TOOL_NAME,
            outcome="error" if payload is None else "success",
            tool_use_id=call.tool_use_id,
            sequence=len(trace) + 1,
            revision_index=None,
        )
    )
    if payload is None:
        return None, msgs.tool_result_block(
            call.tool_use_id, {"error": "arguments are invalid"}, success=False
        )
    return payload, msgs.tool_result_block(call.tool_use_id, payload, success=True)


def _dispatch_plan_tool(
    call: msgs.ToolCall,
    budget: BudgetResult,
    plan: PlanRevisionInput | None,
    trace: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    payload: dict[str, object] | None
    try:
        if call.name == GET_PLAN_TOOL:
            payload = execute_get_plan(call.tool_input, plan, budget)
        elif call.name == SUBSTITUTE_TOOL:
            payload = execute_substitute(call.tool_input)
        else:
            payload = execute_get_meal(call.tool_input)
    except (PlanToolError, SubstituteToolError):
        payload = None
    trace.append(
        _entry(
            tool=call.name,
            outcome="error" if payload is None else "success",
            tool_use_id=call.tool_use_id,
            sequence=len(trace) + 1,
            revision_index=None,
        )
    )
    if payload is None:
        return None, msgs.tool_result_block(
            call.tool_use_id, {"error": "arguments are invalid"}, success=False
        )
    return payload, msgs.tool_result_block(call.tool_use_id, payload, success=True)


def dispatch(
    call: msgs.ToolCall,
    budget: BudgetResult,
    period: date,
    user_id: int,
    source: SpendingSource,
    trace: list[dict[str, object]],
    record_evidence: EvidenceRecorder | None = None,
    *,
    plan: PlanRevisionInput | None = None,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    if call.name in (GET_PLAN_TOOL, GET_MEAL_TOOL, SUBSTITUTE_TOOL):
        return _dispatch_plan_tool(call, budget, plan, trace)
    if call.name == CATALOG_TOOL_NAME:
        try:
            discovery = execute_catalog_search(call.tool_input)
        except CatalogToolError:
            discovery = None
        trace.append(
            _entry(
                tool=CATALOG_TOOL_NAME,
                outcome="error" if discovery is None else "success",
                tool_use_id=call.tool_use_id,
                sequence=len(trace) + 1,
                revision_index=None,
            )
        )
        return discovery, msgs.tool_result_block(
            call.tool_use_id,
            {"error": "catalog arguments are invalid"}
            if discovery is None
            else discovery,
            success=discovery is not None,
        )
    if call.name == BUDGET_TOOL_NAME:
        return _dispatch_budget(call, budget, period, source, trace)
    if call.name != TOOL_NAME:
        trace.append(
            _entry(
                tool="unsupported",
                outcome="error",
                tool_use_id=call.tool_use_id,
                sequence=len(trace) + 1,
                revision_index=None,
            )
        )
        return None, msgs.tool_result_block(
            call.tool_use_id, {"error": "unsupported tool"}, success=False
        )
    error_body: dict[str, object] = {"error": "arguments are invalid"}
    try:
        payload: dict[str, object] | None = execute_plan(
            call.tool_input, budget, period, user_id=user_id, spending_source=source
        )
    except PlanningToolError as exc:
        payload = None
        recipe_id = exc.detail.get("recipe_id")
        ingredient_id = exc.detail.get("ingredient_id")
        diet = exc.detail.get("diet")
        if (
            exc.error_code == "exclusion_reject"
            and isinstance(recipe_id, str)
            and isinstance(ingredient_id, str)
        ):
            error_body = {
                "error": "ingredient is excluded",
                "error_code": "exclusion_reject",
                "recipe_id": recipe_id,
                "ingredient_id": ingredient_id,
            }
        elif (
            exc.error_code == "diet_conflict"
            and isinstance(recipe_id, str)
            and isinstance(ingredient_id, str)
            and isinstance(diet, str)
        ):
            error_body = {
                "error": "ingredient conflicts with diet",
                "error_code": "diet_conflict",
                "recipe_id": recipe_id,
                "ingredient_id": ingredient_id,
                "diet": diet,
            }
        elif exc.error_code == "unsupported_recipe":
            error_body = {
                "error": "recipe is not supported",
                "error_code": "unsupported_recipe",
                "supported_recipe_ids": list(SUPPORTED_RECIPE_IDS),
            }
        elif exc.error_code == "unsupported_diet":
            error_body = {
                "error": "diet is not supported",
                "error_code": "unsupported_diet",
                "supported_diets": list(get_args(Diet)),
            }
        elif exc.error_code == "unsupported_ingredient":
            field = exc.detail.get("field")
            if field in {"pantry_ingredients", "ingredient_exclusions"}:
                error_body = {
                    "error": "ingredient is not supported",
                    "error_code": "unsupported_ingredient",
                    "field": field,
                    "supported_ingredient_ids": list(INGREDIENTS),
                }
    if payload is None:
        trace.append(
            _entry(
                tool=TOOL_NAME,
                outcome="error",
                tool_use_id=call.tool_use_id,
                sequence=len(trace) + 1,
                revision_index=_revision_index(trace),
            )
        )
        return None, msgs.tool_result_block(call.tool_use_id, error_body, success=False)
    if record_evidence is not None:
        revision = record_evidence(payload)
        if not _is_revision_id(revision):
            raise msgs.ChatProtocolError("evidence revision id is invalid")
        payload["evidence_revision_id"] = revision
    evidence = payload.get("evidence_id")
    revision_id = payload.get("evidence_revision_id")
    trace.append(
        _entry(
            tool=TOOL_NAME,
            outcome="success",
            tool_use_id=call.tool_use_id,
            sequence=len(trace) + 1,
            revision_index=_revision_index(trace),
            evidence_id=evidence,
            evidence_revision_id=revision_id,
        )
    )
    return payload, msgs.tool_result_block(
        call.tool_use_id, _llm_tool_payload(payload), success=True
    )
