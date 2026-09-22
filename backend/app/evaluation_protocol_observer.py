from datetime import date

from app.agent.chat_loop import run_chat
from app.agent.chat_messages import ChatProtocolError
from app.agent.planning_tool import TOOL_NAME
from app.domain.budget import BudgetResult
from app.evaluation_protocol_fixture import FakeProtocolProvider, as_map

STATIC_PROTOCOL = "assistant message is invalid"
SAFE_UNKNOWN = "not_a_registered_tool"
_PLANNER_KEYS = (
    "meals",
    "budget_period",
    "diet",
    "pantry_ingredients",
    "ingredient_exclusions",
    "plan_cap_cents",
)
_KINDS = frozenset({"unknown", "malformed", "planner"})
_FIXTURE_KIND = "malformed_or_unknown_tool"


def _miss() -> dict[str, object]:
    return {"outcome": "unexpected_error", "accepted": False}


def _labels(values: list[str], label: str, count: int) -> bool:
    return values == [label] * count


def observe_variant(
    case: dict[str, object],
    kind: str,
    prompt: str,
    budget: BudgetResult,
    clock: date,
) -> dict[str, object]:
    behavior = as_map(case.get("fixture_behavior"))
    if kind not in _KINDS or behavior.get("kind") != _FIXTURE_KIND:
        return _miss()
    if kind == "unknown" and behavior.get("unknown_tool_name") != SAFE_UNKNOWN:
        return _miss()
    payload: object = 0 if kind == "malformed" else {}
    if kind == "planner":
        inputs = as_map(case.get("inputs"))
        payload = {key: inputs.get(key) for key in _PLANNER_KEYS}
    name = SAFE_UNKNOWN if kind == "unknown" else TOOL_NAME
    provider = FakeProtocolProvider(name, payload)
    try:
        result: dict[str, object] | None = run_chat(provider, prompt, budget, clock)
        protocol: bool | None = None
    except ChatProtocolError as exc:
        result = None
        protocol = str(exc) == STATIC_PROTOCOL
        protocol = protocol and exc.__cause__ is None and exc.__context__ is None
    except Exception:
        result = None
        protocol = None
    row: dict[str, object] = {"model_calls": provider.calls}
    if kind == "malformed" and protocol is True:
        row["outcome"] = "malformed_tool_reject"
        row["protocol_static"] = True
        row["accepted"] = False
        return row
    if protocol is not None or not isinstance(result, dict):
        row["outcome"] = "unexpected_error"
        row["accepted"] = False
        return row
    plan = result.get("plan")
    row["accepted"] = isinstance(plan, dict) and plan.get("accepted") is True
    raw = result.get("tool_trace")
    items = raw if isinstance(raw, list) else []
    tools: list[str] = []
    outs: list[str] = []
    for item in items:
        if isinstance(item, dict) and type(item.get("tool")) is str:
            tools.append(str(item.get("tool")))
        if isinstance(item, dict) and type(item.get("outcome")) is str:
            outs.append(str(item.get("outcome")))
    closed = result.get("status") == "limit" and result.get("plan") is None
    calls = provider.calls
    if kind == "unknown":
        errors = provider.result_errors
        matched = closed and _labels(tools, "unsupported", calls)
        matched = matched and _labels(outs, "error", calls)
        matched = matched and errors == ["unsupported tool"] * (calls - 1)
        if not matched:
            row["outcome"] = "unexpected_error"
            return row
        row["unknown_tool_rejected"] = True
        row["outcome"] = "unknown_tool_reject"
        row["trace_tools"] = tools
        row["unsupported_results"] = len(errors)
        return row
    revisions = result.get("planner_revisions")
    if type(revisions) is not int:
        row["outcome"] = "unexpected_error"
        return row
    matched = closed and calls == revisions + 1
    matched = matched and _labels(tools, TOOL_NAME, revisions)
    matched = matched and _labels(outs, "success", revisions)
    if not matched:
        row["outcome"] = "unexpected_error"
        return row
    row["planner_revisions"] = revisions
    row["trace_tools"] = tools
    row["outcome"] = "planner_limit"
    return row
