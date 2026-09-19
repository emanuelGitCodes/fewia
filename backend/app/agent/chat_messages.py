from typing import NamedTuple

MAX_TOOL_CALLS, MAX_TOOL_FIELD_LEN = 3, 64
_STOP_REASONS = frozenset(
    "end_turn tool_use max_tokens stop_sequence "
    "guardrail_intervened content_filtered model_context_window_exceeded".split()
)


class ChatProtocolError(ValueError):
    pass


class ToolCall(NamedTuple):
    tool_use_id: str
    name: str
    tool_input: dict[str, object]


def _invalid() -> ChatProtocolError:
    return ChatProtocolError("assistant message is invalid")


def _as_str_map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        return None
    return {str(key): item for key, item in value.items()}


def _parse_tool_use(value: object, seen_ids: set[str]) -> ToolCall:
    block = _as_str_map(value)
    tool_id = None if block is None else block.get("toolUseId")
    name = None if block is None else block.get("name")
    payload = None if block is None else _as_str_map(block.get("input"))
    if not (
        isinstance(tool_id, str)
        and isinstance(name, str)
        and payload is not None
        and tool_id.strip() == tool_id
        and 0 < len(tool_id) <= MAX_TOOL_FIELD_LEN
        and name.strip()
        and len(name) <= MAX_TOOL_FIELD_LEN
        and tool_id not in seen_ids
    ):
        raise _invalid()
    seen_ids.add(tool_id)
    return ToolCall(tool_id, name, payload)


def parse_assistant_message(
    message: object, seen_ids: set[str]
) -> tuple[str, list[ToolCall], dict[str, object]]:
    body = _as_str_map(message)
    content = None if body is None else body.get("content")
    if (
        body is None
        or body.get("role") != "assistant"
        or not isinstance(content, list)
        or not content
    ):
        raise _invalid()
    texts: list[str] = []
    calls: list[ToolCall] = []
    kept: list[dict[str, object]] = []
    pending = set(seen_ids)
    for block in content:
        item = _as_str_map(block)
        if item is None:
            raise _invalid()
        item.pop("reasoningContent", None)
        if "text" in item and "toolUse" in item:
            raise _invalid()
        if "text" in item:
            text = item["text"]
            if not isinstance(text, str):
                raise _invalid()
            texts.append(text)
            kept.append({"text": text})
        elif "toolUse" in item:
            call = _parse_tool_use(item["toolUse"], pending)
            calls.append(call)
            tool_use = {
                "toolUseId": call.tool_use_id,
                "name": call.name,
                "input": call.tool_input,
            }
            kept.append({"toolUse": tool_use})
    if len(calls) > MAX_TOOL_CALLS:
        raise _invalid()
    seen_ids.update(pending)
    return "\n".join(texts), calls, {"role": "assistant", "content": kept}


def parse_provider_response(
    response: object, seen_ids: set[str]
) -> tuple[str, str, list[ToolCall], dict[str, object]]:
    body = _as_str_map(response)
    output = _as_str_map(None if body is None else body.get("output"))
    stop = None if body is None else body.get("stopReason")
    if (
        body is None
        or output is None
        or not isinstance(stop, str)
        or stop not in _STOP_REASONS
    ):
        raise ChatProtocolError("provider output is invalid")
    pending = set(seen_ids)
    text, calls, sanitized = parse_assistant_message(output.get("message"), pending)
    if (stop == "tool_use") != bool(calls):
        raise ChatProtocolError("provider output is invalid")
    seen_ids.update(pending)
    return stop, text, calls, sanitized


def tool_result_block(
    tool_use_id: str, content: dict[str, object], *, success: bool
) -> dict[str, object]:
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"json": dict(content)}],
            "status": "success" if success else "error",
        }
    }


def build_chat_result(
    status: str,
    answer: str,
    candidate: dict[str, object] | None,
    source: str,
    trace: list[dict[str, object]],
    turns: int,
    revisions: int,
) -> dict[str, object]:
    keep = (
        candidate if status in {"planned", "needs_revision", "clarification"} else None
    )
    return {
        "status": status,
        "answer": answer,
        "plan": None if keep is None else keep.get("plan"),
        "budget": None if keep is None else keep.get("budget"),
        "request": None if keep is None else keep.get("request"),
        "meal_nutrition": None if keep is None else keep.get("meal_nutrition"),
        "evidence_id": None if keep is None else keep.get("evidence_id"),
        "evidence_revision_id": (
            None if keep is None else keep.get("evidence_revision_id")
        ),
        "spending_source": source,
        "tool_trace": trace,
        "model_turns": turns,
        "planner_revisions": revisions,
    }
