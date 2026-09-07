import json
from datetime import date

from app.agent.chat_dispatch import dispatch
from app.agent.chat_messages import ToolCall
from app.agent.planning_tool import TOOL_NAME, execute_plan
from app.domain.budget import BudgetResult

PERIOD = date(2026, 9, 1)
_SECRET = "do-not-echo-raw-input"


def arguments(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
    }
    values.update(overrides)
    return values


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 250, False, ())


def test_valid_plan_returns_payload_and_matching_tool_result_id() -> None:
    call = ToolCall("call-1", TOOL_NAME, arguments())
    trace: list[dict[str, object]] = []
    expected = execute_plan(arguments(), budget(), PERIOD)
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate == expected
    assert block == {
        "toolResult": {
            "toolUseId": "call-1",
            "content": [{"json": expected}],
            "status": "success",
        }
    }
    evidence = expected["evidence_id"]
    assert isinstance(evidence, str)
    assert trace == [{"tool": TOOL_NAME, "outcome": "success", "evidence_id": evidence}]


def test_unknown_name_returns_unsupported_and_clears_candidate() -> None:
    call = ToolCall("call-9", "purchase_items", {"token": _SECRET})
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-9",
            "content": [{"json": {"error": "unsupported tool"}}],
            "status": "error",
        }
    }
    assert trace == [{"tool": "unsupported", "outcome": "error"}]
    assert set(trace[0]) == {"tool", "outcome"}


def test_invalid_args_return_static_error_and_clear_candidate() -> None:
    args = arguments(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    call = ToolCall("call-2", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    assert block == {
        "toolResult": {
            "toolUseId": "call-2",
            "content": [{"json": {"error": "arguments are invalid"}}],
            "status": "error",
        }
    }
    assert trace == [{"tool": TOOL_NAME, "outcome": "error"}]
    assert set(trace[0]) == {"tool", "outcome"}


def test_capped_budget_uses_smaller_plan_cap() -> None:
    args = arguments(plan_cap_cents=100)
    call = ToolCall("call-3", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(1_000), PERIOD, 1, "fixture", trace)
    assert candidate is not None
    budget_payload = candidate["budget"]
    plan_payload = candidate["plan"]
    assert isinstance(budget_payload, dict)
    assert isinstance(plan_payload, dict)
    assert budget_payload["available_cents"] == 100
    assert plan_payload["accepted"] is False
    assert block["toolResult"]["toolUseId"] == "call-3"
    assert block["toolResult"]["status"] == "success"
    assert trace[0]["tool"] == TOOL_NAME
    assert trace[0]["outcome"] == "success"


def test_errors_omit_raw_input_and_exception_context() -> None:
    args = arguments(meals=[{"recipe_id": _SECRET, "servings": 1}])
    call = ToolCall("call-4", TOOL_NAME, args)
    trace: list[dict[str, object]] = []
    candidate, block = dispatch(call, budget(), PERIOD, 1, "fixture", trace)
    assert candidate is None
    dumped = json.dumps({"block": block, "trace": trace})
    assert _SECRET not in dumped
    assert "ValidationError" not in dumped
    assert "PlanningToolError" not in dumped
    assert "Traceback" not in dumped
    assert block["toolResult"]["content"] == [
        {"json": {"error": "arguments are invalid"}}
    ]
    unknown = ToolCall("call-5", "purchase_items", {"token": _SECRET})
    unknown_trace: list[dict[str, object]] = []
    unknown_candidate, unknown_block = dispatch(
        unknown, budget(), PERIOD, 1, "fixture", unknown_trace
    )
    assert unknown_candidate is None
    unknown_dump = json.dumps({"block": unknown_block, "trace": unknown_trace})
    assert _SECRET not in unknown_dump
    assert "purchase_items" not in unknown_dump
