from collections import Counter
from typing import cast

from pydantic import ValidationError

from app.domain.grocery import GroceryRequest
from app.evaluation_shapes import as_map, typed_equal, valid_public_result

_METRICS = (
    "valid_calls",
    "expected_tool_selection",
    "expected_arguments",
    "unnecessary_calls",
)


def _arguments(call: object) -> dict[str, object] | None:
    item = as_map(call)
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
    period = arguments.get("budget_period")
    if type(period) is not str or period != normalized["budget_period"]:
        return None
    return {**normalized, **as_map(arguments)}


def _matches(expected: dict[str, object], arguments: object) -> bool:
    required = as_map(expected.get("arguments"))
    actual = as_map(arguments)
    return arguments is not None and all(
        key in actual and typed_equal(value, actual[key])
        for key, value in required.items()
    )


def _argument_matches(expected: list[dict[str, object]], calls: list[object]) -> int:
    arguments = [_arguments(call) for call in calls]
    paired: dict[int, int] = {}

    def pair(index: int, seen: set[int]) -> bool:
        for number, call in enumerate(calls):
            if (
                number in seen
                or expected[index]["name"] != as_map(call).get("tool")
                or not _matches(expected[index], arguments[number])
            ):
                continue
            seen.add(number)
            if number not in paired or pair(paired[number], seen):
                paired[number] = index
                return True
        return False

    return sum(pair(index, set()) for index in range(len(expected)))


def _metric(status: str, numerator: int, denominator: int) -> dict[str, object]:
    return {"status": status, "numerator": numerator, "denominator": denominator}


def score_tools(
    case: dict[str, object], observation: dict[str, object]
) -> dict[str, object]:
    turns = observation.get("turns")
    messages = case.get("messages")
    user_messages = messages if isinstance(messages, list) else []
    user_turns = sum(as_map(m).get("role") == "user" for m in user_messages)
    complete = (
        observation.get("status") == "completed"
        and isinstance(turns, list)
        and len(turns) == user_turns > 0
        and all(
            as_map(turn).get("status") == "completed"
            and valid_public_result(as_map(turn).get("result"))
            and isinstance(as_map(turn).get("calls"), list)
            for turn in turns
        )
    )
    identity = (
        type(case.get("id")) is str
        and bool(case["id"])
        and typed_equal(case["id"], observation.get("case_id"))
    )
    calls: list[object] = []
    shapes = isinstance(turns, list)
    for turn in turns if isinstance(turns, list) else []:
        observed = as_map(turn).get("calls")
        shapes = shapes and type(turn) is dict and isinstance(observed, list)
        if isinstance(observed, list):
            calls.extend(observed)
    shapes = shapes and all(
        set(as_map(call)) == {"tool", "input"} and type(as_map(call).get("tool")) is str
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
    expected = as_map(case.get("expected"))
    tools = expected.get("model_tools")
    forbidden = expected.get("unnecessary_model_tools", [])
    gold = (
        isinstance(tools, list)
        and isinstance(forbidden, list)
        and all(type(name) is str for name in forbidden)
        and all(
            type(as_map(tool).get("name")) is str
            and type(as_map(tool).get("arguments")) is dict
            for tool in tools
        )
    )
    if condition == "tool_enabled" and complete and identity and gold:
        final = cast(list[object], as_map(cast(list[object], turns)[-1])["calls"])
        expected_calls = [as_map(tool) for tool in cast(list[object], tools)]
        blocked = cast(list[object], forbidden)
        allowed = [tool for tool in expected_calls if tool["name"] not in blocked]
        selected = sum(
            min(total, sum(as_map(call).get("tool") == name for call in final))
            for name, total in Counter(tool["name"] for tool in allowed).items()
        )
        matched = _argument_matches(allowed, final)
        count = len(expected_calls)
        counts = (
            (valid, len(calls)),
            (selected, count),
            (matched, count),
            (len(final) - selected, len(final)),
        )
        for name, (value, total) in zip(_METRICS, counts, strict=True):
            passed = value == (0 if name == "unnecessary_calls" else total)
            metrics[name] = _metric("passed" if passed else "failed", value, total)
        passed = all(as_map(value)["status"] == "passed" for value in metrics.values())
        status = "passed" if passed and shapes else "failed"
    return {"status": status, "checks": checks, **metrics}
