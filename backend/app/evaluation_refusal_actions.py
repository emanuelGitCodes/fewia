from app.agent.budget_tool import TOOL_NAME
from app.agent.chat_messages import MAX_TOOL_FIELD_LEN


def _budget_read_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"tool", "input"}:
        return False
    arguments = value["input"]
    return (
        type(value["tool"]) is str
        and value["tool"] == TOOL_NAME
        and type(arguments) is dict
        and not arguments
    )


def _result_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "content",
        "status",
        "toolUseId",
    }:
        return False
    tool_id = value["toolUseId"]
    status = value["status"]
    return (
        isinstance(value["content"], list)
        and type(status) is str
        and status in ("success", "error")
        and type(tool_id) is str
        and 0 < len(tool_id) <= MAX_TOOL_FIELD_LEN
        and tool_id.strip() == tool_id
        and "[invalid]" not in tool_id
        and "[redacted]" not in tool_id
    )


def refusal_actions_valid(turns: list[object]) -> bool:
    """Validate captured refusal actions and result envelopes."""
    for turn in turns:
        if not isinstance(turn, dict):
            return False
        calls = turn.get("calls")
        results = turn.get("tool_results")
        if not isinstance(calls, list) or not isinstance(results, list):
            return False
        if not all(_budget_read_valid(call) for call in calls):
            return False
        if results and not calls:
            return False
        if not all(_result_valid(result) for result in results):
            return False
    return True
