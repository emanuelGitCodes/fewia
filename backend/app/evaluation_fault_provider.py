"""Scripted protocol guard probes exclude model quality evidence."""

from dataclasses import dataclass
from typing import cast

from app.agent.provider import LLMUnavailable

_SECRET = "SYNTHETIC_PROTOCOL_SECRET_SENTINEL"
UNAVAILABLE_VARIANTS: dict[str, tuple[int, int, str]] = {
    "unavailable": (1, 0, "chat_unavailable"),
}
PROTOCOL_VARIANTS: dict[str, tuple[int, int, str]] = {
    "unknown_tool": (8, 0, "limit"),
    "invalid_planner": (4, 3, "limit"),
    "malformed_input": (1, 0, "chat_protocol_error"),
    "duplicate_id": (2, 0, "chat_protocol_error"),
    "too_many_tools": (1, 0, "chat_protocol_error"),
    "stop_mismatch": (1, 0, "chat_protocol_error"),
}


@dataclass
class FaultProvider:
    variant: str
    cutoff: int
    calls: int = 0
    errors: int = 0

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls += 1
        if self.variant == "unavailable" or self.calls > self.cutoff:
            raise LLMUnavailable(_SECRET)
        for block in cast(list[dict[str, object]], messages[-1].get("content", [])):
            item = block.get("toolResult")
            if isinstance(item, dict) and item.get("status") == "error":
                self.errors += 1
        planner = self.variant == "invalid_planner"
        tool: dict[str, object] = {
            "toolUseId": f"t{1 if self.variant == 'duplicate_id' else self.calls}",
            "name": "plan_groceries" if planner else "unknown_tool",
            "input": [] if self.variant == "malformed_input" else {"meals": "invalid"},
        }
        content = [{"toolUse": tool}]
        if self.variant == "too_many_tools":
            content = [{"toolUse": dict(tool, toolUseId=f"t{i}")} for i in range(4)]
        return {
            "output": {"message": {"role": "assistant", "content": content}},
            "stopReason": "end_turn" if self.variant == "stop_mismatch" else "tool_use",
        }
