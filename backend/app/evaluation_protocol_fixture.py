from copy import deepcopy
from datetime import date
from typing import cast

CLOCK_ERROR = "clock is invalid"


def as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def period(inputs: dict[str, object]) -> date:
    value = inputs.get("budget_period")
    parsed: date | None = None
    if type(value) is str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            parsed = None
    if parsed is None or parsed.day != 1:
        raise ValueError(CLOCK_ERROR)
    return parsed


class FakeProtocolProvider:
    """Deterministic LLMProvider for evaluation. This class MUST NOT call Bedrock."""

    __slots__ = ("calls", "name", "payload", "result_errors")

    def __init__(self, name: str, payload: object) -> None:
        self.calls, self.name, self.payload = 0, name, payload
        self.result_errors: list[str] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        del system_prompt, tools
        self.calls += 1
        last = messages[-1] if messages else None
        blocks = last.get("content") if isinstance(last, dict) else []
        for block in blocks if isinstance(blocks, list) else []:
            item = block.get("toolResult") if isinstance(block, dict) else None
            content = item.get("content") if isinstance(item, dict) else None
            head = content[0] if isinstance(content, list) and content else None
            body = head.get("json") if isinstance(head, dict) else None
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(item, dict) and item.get("status") == "error":
                if type(error) is str:
                    self.result_errors.append(error)
        tool = {
            "toolUseId": f"t{self.calls}",
            "name": self.name,
            "input": deepcopy(self.payload),
        }
        message = {"role": "assistant", "content": [{"toolUse": tool}]}
        return {"output": {"message": message}, "stopReason": "tool_use"}
