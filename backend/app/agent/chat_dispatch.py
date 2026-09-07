from collections.abc import Callable
from datetime import date
from typing import Literal

from app.agent import chat_messages as msgs
from app.agent.planning_tool import TOOL_NAME, PlanningToolError, execute_plan
from app.domain.budget import BudgetResult

EvidenceRecorder = Callable[[dict[str, object]], str]


def _is_revision_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all("0" <= char <= "9" or "a" <= char <= "f" for char in value)
    )


def _revision_index(trace: list[dict[str, object]]) -> int:
    return 1 + sum(1 for item in trace if item.get("tool") == TOOL_NAME)


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


def dispatch(
    call: msgs.ToolCall,
    budget: BudgetResult,
    period: date,
    user_id: int,
    source: Literal["fixture", "plaid_sandbox"],
    trace: list[dict[str, object]],
    record_evidence: EvidenceRecorder | None = None,
) -> tuple[dict[str, object] | None, dict[str, object]]:
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
    try:
        payload: dict[str, object] | None = execute_plan(
            call.tool_input, budget, period, user_id=user_id, spending_source=source
        )
    except PlanningToolError:
        payload = None
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
        return None, msgs.tool_result_block(
            call.tool_use_id, {"error": "arguments are invalid"}, success=False
        )
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
    return payload, msgs.tool_result_block(call.tool_use_id, payload, success=True)
