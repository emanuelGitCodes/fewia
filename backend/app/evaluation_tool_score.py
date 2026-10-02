from typing import cast

from pydantic import ValidationError

from app.domain.grocery import GroceryRequest

_METRICS = (
    "valid_calls",
    "expected_tool_selection",
    "expected_arguments",
    "unnecessary_calls",
)


def _dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if type(value) is dict else {}


def _same(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _same(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)


def _arguments(call: object) -> dict[str, object] | None:
    item = _dict(call)
    arguments = item.get("input")
    if set(item) != {"tool", "input"} or type(arguments) is not dict:
        return None
    if item["tool"] == "get_budget_summary":
        return {} if not arguments else None
    if item["tool"] != "plan_groceries":
        return None
    try:
        normalized = GroceryRequest.model_validate(arguments).model_dump(mode="json")
    except ValidationError:
        return None
    return {**normalized, **_dict(arguments)}


def _matches(expected: dict[str, object], arguments: object) -> bool:
    required = _dict(expected.get("arguments"))
    actual = _dict(arguments)
    return arguments is not None and all(
        key in actual and _same(value, actual[key]) for key, value in required.items()
    )


def _metric(status: str, numerator: int, denominator: int) -> dict[str, object]:
    return {"status": status, "numerator": numerator, "denominator": denominator}


def score_tools(
    case: dict[str, object], observation: dict[str, object]
) -> dict[str, object]:
    turns = observation.get("turns")
    messages = case.get("messages")
    user_messages = messages if isinstance(messages, list) else []
    user_turns = sum(_dict(m).get("role") == "user" for m in user_messages)
    complete = (
        observation.get("status") == "completed"
        and isinstance(turns, list)
        and len(turns) == user_turns > 0
        and all(
            _dict(turn).get("status") == "completed"
            and bool(_dict(_dict(turn).get("result")))
            and isinstance(_dict(turn).get("calls"), list)
            for turn in turns
        )
    )
    identity = (
        type(case.get("id")) is str
        and bool(case["id"])
        and _same(case["id"], observation.get("case_id"))
    )
    calls: list[object] = []
    shapes = isinstance(turns, list)
    for turn in turns if isinstance(turns, list) else []:
        observed = _dict(turn).get("calls")
        shapes = shapes and type(turn) is dict and isinstance(observed, list)
        if isinstance(observed, list):
            calls.extend(observed)
    shapes = shapes and all(
        set(_dict(call)) == {"tool", "input"} and type(_dict(call).get("tool")) is str
        for call in calls
    )
    valid = sum(_arguments(call) is not None for call in calls)
    checks = {"case_id": identity, "turns_complete": complete, "call_shapes": shapes}
    status = "unassessed" if identity and shapes and valid == len(calls) else "failed"
    metrics: dict[str, object] = {key: _metric("unassessed", 0, 0) for key in _METRICS}
    condition = observation.get("condition")
    if condition in ("no_tool", "deterministic"):
        metrics = {name: {"status": "not_applicable"} for name in _METRICS}
    elif condition == "tool_enabled":
        metrics["valid_calls"] = _metric(status, valid, len(calls))
    expected = _dict(case.get("expected"))
    tools = expected.get("model_tools")
    forbidden = expected.get("unnecessary_model_tools", [])
    gold = (
        isinstance(tools, list)
        and isinstance(forbidden, list)
        and all(type(name) is str for name in forbidden)
        and all(
            type(_dict(tool).get("name")) is str
            and type(_dict(tool).get("arguments")) is dict
            for tool in tools
        )
    )
    if condition == "tool_enabled" and complete and identity and gold:
        final = cast(list[object], _dict(cast(list[object], turns)[-1])["calls"])
        remaining = [_dict(tool) for tool in cast(list[object], tools)]
        selected, matched, count = 0, 0, len(cast(list[object], tools))
        for call in final:
            choices = [
                tool
                for tool in remaining
                if tool["name"] == _dict(call).get("tool")
                and tool["name"] not in cast(list[object], forbidden)
            ]
            if choices:
                arguments = _arguments(call)
                tool = next((t for t in choices if _matches(t, arguments)), choices[0])
                remaining.remove(tool)
                selected += 1
                matched += _matches(tool, arguments)
        counts = (
            (valid, len(calls)),
            (selected, count),
            (matched, count),
            (len(final) - selected, len(final)),
        )
        for name, (value, total) in zip(_METRICS, counts, strict=True):
            passed = value == (0 if name == "unnecessary_calls" else total)
            metrics[name] = _metric("passed" if passed else "failed", value, total)
        passed = all(_dict(value)["status"] == "passed" for value in metrics.values())
        status = "passed" if passed and shapes else "failed"
    return {"status": status, "checks": checks, **metrics}
