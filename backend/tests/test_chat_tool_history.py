from __future__ import annotations

import copy
import json
from datetime import date

from app.agent.chat_answer import CLARIFY_ANSWER, render_public_answer
from app.agent.chat_loop import MAX_MODEL_TURNS, MAX_PLANNER_REVISIONS, run_chat
from app.agent.planning_tool import TOOL_NAME, execute_plan
from app.domain.budget import BudgetResult

PERIOD = date(2026, 9, 1)
MARKER = "SYNTH_MARKER_TOOL_PROSE_7f3a"
USER_TEXT = "plan chicken tacos"
PLAN_CAP = 5000


def _budget() -> BudgetResult:
    return BudgetResult(10_000, 250, False, ())


def _plan_args() -> dict[str, object]:
    return {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD.isoformat(),
    }


def _reply(content: list[dict[str, object]], stop: str) -> dict[str, object]:
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


def _tool_use(
    tool_id: str,
    name: str = TOOL_NAME,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "toolUse": {
            "toolUseId": tool_id,
            "name": name,
            "input": _plan_args() if payload is None else payload,
        }
    }


class FakeLLM:
    def __init__(self, replies: list[dict[str, object]]) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.requests.append(
            {
                "system": system_prompt,
                "messages": copy.deepcopy(messages),
                "tools": copy.deepcopy(tools),
            }
        )
        if not self._replies:
            raise AssertionError("unexpected provider call")
        return self._replies.pop(0)


def _assert_no_marker(value: object) -> None:
    assert MARKER not in json.dumps(value)


def _follow_messages(provider: FakeLLM) -> list[dict[str, object]]:
    assert len(provider.requests) == 2
    follow = provider.requests[1]
    _assert_no_marker(follow["system"])
    _assert_no_marker(follow["messages"])
    _assert_no_marker(follow["tools"])
    messages = follow["messages"]
    assert isinstance(messages, list)
    return messages


def _assert_caps_and_latest_user(provider: FakeLLM) -> None:
    assert MAX_MODEL_TURNS == 8
    assert MAX_PLANNER_REVISIONS == 3
    first = provider.requests[0]
    messages = first["messages"]
    assert isinstance(messages, list)
    last = messages[-1]
    assert last["role"] == "user"
    content = last["content"]
    assert isinstance(content, list)
    assert content[-1] == {"text": USER_TEXT}
    context = json.loads(str(content[0]["text"]))
    assert context["plan_cap_cents"] == PLAN_CAP


def test_tool_use_history_keeps_tool_use_and_drops_assistant_prose() -> None:
    payload = _plan_args()
    replies = [
        _reply(
            [
                {"text": f"draft {MARKER}"},
                _tool_use("call-1", payload=copy.deepcopy(payload)),
            ],
            "tool_use",
        ),
        _reply([{"text": f"final {MARKER}"}], "end_turn"),
    ]
    frozen = copy.deepcopy(replies)
    provider = FakeLLM(replies)
    result = run_chat(
        provider,
        USER_TEXT,
        _budget(),
        PERIOD,
        plan_cap_cents=PLAN_CAP,
    )
    assert replies == frozen
    _assert_caps_and_latest_user(provider)
    expected = execute_plan(copy.deepcopy(payload), _budget(), PERIOD)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["plan"] == expected["plan"]
    _assert_no_marker(result)
    _assert_no_marker(result["answer"])
    _assert_no_marker(result["tool_trace"])
    messages = _follow_messages(provider)
    assistant = messages[-2]
    user_block = messages[-1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == [
        {
            "toolUse": {
                "toolUseId": "call-1",
                "name": TOOL_NAME,
                "input": payload,
            }
        }
    ]
    assert user_block["role"] == "user"
    tool_content = user_block["content"]
    assert isinstance(tool_content, list)
    tool_result = tool_content[0]["toolResult"]
    assert isinstance(tool_result, dict)
    assert tool_result["toolUseId"] == "call-1"
    assert tool_result["status"] == "success"


def test_unknown_tool_history_keeps_static_error_and_drops_assistant_prose() -> None:
    unknown_input: dict[str, object] = {"action": "checkout"}
    replies = [
        _reply(
            [
                {"text": f"buy {MARKER}"},
                _tool_use(
                    "buy-1",
                    name="purchase_items",
                    payload=unknown_input,
                ),
            ],
            "tool_use",
        ),
        _reply([{"text": f"bought {MARKER}"}], "end_turn"),
    ]
    frozen = copy.deepcopy(replies)
    provider = FakeLLM(replies)
    result = run_chat(
        provider,
        USER_TEXT,
        _budget(),
        PERIOD,
        plan_cap_cents=PLAN_CAP,
    )
    assert replies == frozen
    _assert_caps_and_latest_user(provider)
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFY_ANSWER
    assert result["plan"] is None
    _assert_no_marker(result)
    _assert_no_marker(result["answer"])
    _assert_no_marker(result["tool_trace"])
    messages = _follow_messages(provider)
    assistant = messages[-2]
    user_block = messages[-1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == [
        {
            "toolUse": {
                "toolUseId": "buy-1",
                "name": "purchase_items",
                "input": unknown_input,
            }
        }
    ]
    assert user_block["role"] == "user"
    tool_content = user_block["content"]
    assert isinstance(tool_content, list)
    tool_result = tool_content[0]["toolResult"]
    assert isinstance(tool_result, dict)
    assert tool_result["toolUseId"] == "buy-1"
    assert tool_result["status"] == "error"
    result_content = tool_result["content"]
    assert isinstance(result_content, list)
    body = result_content[0]
    assert isinstance(body, dict)
    assert body["json"] == {"error": "unsupported tool"}
    trace = result["tool_trace"]
    assert isinstance(trace, list)
    assert trace[0]["tool"] == "unsupported"
    assert "purchase" not in json.dumps(trace)
