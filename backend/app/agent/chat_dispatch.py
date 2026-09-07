from datetime import date
from typing import Literal

from app.agent import chat_messages as msgs
from app.agent.planning_tool import TOOL_NAME, PlanningToolError, execute_plan
from app.domain.budget import BudgetResult


def dispatch(
    call: msgs.ToolCall,
    budget: BudgetResult,
    period: date,
    user_id: int,
    source: Literal["fixture", "plaid_sandbox"],
    trace: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    if call.name != TOOL_NAME:
        trace.append({"tool": "unsupported", "outcome": "error"})
        return None, msgs.tool_result_block(
            call.tool_use_id, {"error": "unsupported tool"}, success=False
        )
    try:
        payload: dict[str, object] | None = execute_plan(
            call.tool_input, budget, period, user_id=user_id, spending_source=source
        )
    except PlanningToolError:
        payload = None
    if payload is None:
        trace.append({"tool": TOOL_NAME, "outcome": "error"})
        return None, msgs.tool_result_block(
            call.tool_use_id, {"error": "arguments are invalid"}, success=False
        )
    evidence = payload.get("evidence_id")
    entry: dict[str, object] = {"tool": TOOL_NAME, "outcome": "success"}
    if isinstance(evidence, str):
        entry["evidence_id"] = evidence
    trace.append(entry)
    return payload, msgs.tool_result_block(call.tool_use_id, payload, success=True)
