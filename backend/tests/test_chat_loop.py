from __future__ import annotations

import copy
import json
from datetime import date
from typing import Literal, cast

import pytest
from botocore.session import Session
from botocore.validate import validate_parameters

from app.agent import chat_loop as loop
from app.agent.budget_tool import (
    TOOL_NAME as BUDGET_TOOL_NAME,
)
from app.agent.budget_tool import (
    budget_summary_answer,
    budget_tool_spec,
    execute_budget_summary,
)
from app.agent.chat_answer import (
    _UNKNOWN_RESTRICTION,
    CLARIFICATION,
    render_public_answer,
)
from app.agent.chat_dispatch import EvidenceRecorder
from app.agent.chat_loop import (
    MAX_MODEL_TURNS,
    MAX_PLANNER_REVISIONS,
    SYSTEM_PROMPT,
    ChatUnavailable,
    run_chat,
)
from app.agent.chat_messages import MAX_TOOL_CALLS, ChatProtocolError, ToolCall
from app.agent.planning_tool import TOOL_NAME, execute_plan, planner_tool_spec
from app.domain.budget import BudgetResult, SpendingSource
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS

PERIOD = date(2026, 9, 1)
_SECRET = "do-not-echo-raw-input"
_UNAVAILABLE = "The language model is unavailable."
_LIMIT = "The job reached a processing limit."
_INCOMPLETE = "The model did not complete a reply."
_SERVICE = Session().get_service_model("bedrock-runtime")
_INPUT_SHAPE = _SERVICE.operation_model("Converse").input_shape
_PRIVATE = (
    "history",
    "messages",
    "credentials",
    "password",
    "secret",
    "cost",
    "price",
)
_REV = "a" * 64


def _success_trace(
    tool_use_id: str,
    evidence_id: object,
    *,
    sequence: int = 1,
    revision_index: int = 1,
    revision_id: str | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": TOOL_NAME,
        "outcome": "success",
        "evidence_id": evidence_id,
        "tool_use_id": tool_use_id,
        "sequence": sequence,
        "revision_index": revision_index,
    }
    if revision_id is not None:
        entry["evidence_revision_id"] = revision_id
    return entry


def _error_trace(
    tool: str,
    tool_use_id: str,
    *,
    sequence: int = 1,
    revision_index: int | None = 1,
) -> dict[str, object]:
    return {
        "tool": tool,
        "outcome": "error",
        "tool_use_id": tool_use_id,
        "sequence": sequence,
        "revision_index": revision_index,
    }


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 250, False, ())


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    return f"USD {sign}${magnitude // 100}.{magnitude % 100:02d}"


def plan_args(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD.isoformat(),
    }
    values.update(overrides)
    return values


def previous(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD,
        "pantry_ingredients": ["salt"],
    }
    values.update(overrides)
    return values


def _assert_static(error: BaseException, token: str) -> None:
    assert token not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def _assert_public(result: dict[str, object], token: str = _SECRET) -> None:
    dumped = json.dumps(result)
    assert token not in dumped
    assert "reasoningContent" not in dumped
    for key in _PRIVATE:
        assert key not in result


def _validate_converse(
    system_prompt: str,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]],
) -> None:
    params: dict[str, object] = {
        "modelId": "model-id",
        "system": [{"text": system_prompt}],
        "messages": messages,
        "toolConfig": {"tools": tools},
    }
    validate_parameters(params, _INPUT_SHAPE)


class FakeLLM:
    def __init__(self, replies: list[dict[str, object] | BaseException]) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        snapshot = copy.deepcopy(messages)
        tool_snapshot = copy.deepcopy(tools)
        _validate_converse(system_prompt, snapshot, tool_snapshot)
        self.requests.append(
            {"system": system_prompt, "messages": snapshot, "tools": tool_snapshot}
        )
        if not self._replies:
            raise AssertionError("unexpected provider call")
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


class Heartbeats:
    def __init__(
        self, fail_at: int | None = None, token: str = "heartbeat-lost"
    ) -> None:
        self.count = 0
        self.fail_at = fail_at
        self.token = token

    def __call__(self) -> None:
        self.count += 1
        if self.fail_at is not None and self.count == self.fail_at:
            raise RuntimeError(self.token)


def _reply(
    content: list[dict[str, object]],
    stop: str,
    usage: dict[str, int] | None = None,
    *,
    omit_usage: bool = False,
) -> dict[str, object]:
    body: dict[str, object] = {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
    }
    if not omit_usage:
        tokens = {"inputTokens": 1, "outputTokens": 1}
        body["usage"] = tokens if usage is None else usage
    return body


def _chat_tools() -> list[dict[str, object]]:
    return [planner_tool_spec(), budget_tool_spec()]


def _budget_block(
    tool_id: str,
    payload: dict[str, object] | None = None,
    reasoning: object | None = None,
) -> dict[str, object]:
    return _tool_block(
        tool_id,
        name=BUDGET_TOOL_NAME,
        payload={} if payload is None else payload,
        reasoning=reasoning,
    )


def _budget_trace(
    tool_use_id: str, *, sequence: int = 1, outcome: str = "success"
) -> dict[str, object]:
    return {
        "tool": BUDGET_TOOL_NAME,
        "outcome": outcome,
        "tool_use_id": tool_use_id,
        "sequence": sequence,
        "revision_index": None,
    }


def _tool_block(
    tool_id: str,
    name: str = TOOL_NAME,
    payload: dict[str, object] | None = None,
    reasoning: object | None = None,
) -> dict[str, object]:
    block: dict[str, object] = {
        "toolUse": {
            "toolUseId": tool_id,
            "name": name,
            "input": plan_args() if payload is None else payload,
        }
    }
    if reasoning is not None:
        block["reasoningContent"] = reasoning
    return block


def _text_block(text: str, reasoning: object | None = None) -> dict[str, object]:
    block: dict[str, object] = {"text": text}
    if reasoning is not None:
        block["reasoningContent"] = reasoning
    return block


def _planner_then_final(
    tool_id: str = "call-1", payload: dict[str, object] | None = None
) -> list[dict[str, object] | BaseException]:
    return [
        _reply([_tool_block(tool_id, payload=payload)], "tool_use"),
        _reply([_text_block("Here is a labeled estimate.")], "end_turn"),
    ]


def _noop() -> None:
    return None


def _run(
    replies: list[dict[str, object] | BaseException],
    *,
    message: str = "plan chicken tacos",
    heartbeat: Heartbeats | None = None,
    history: list[dict[str, str]] | None = None,
    previous_request: dict[str, object] | None = None,
    spending_source: Literal["fixture", "plaid_sandbox"] = "fixture",
    user_id: int = 1,
    available_cents: int = 10_000,
    record_evidence: EvidenceRecorder | None = None,
    plan_cap_cents: int | None = None,
) -> tuple[dict[str, object], FakeLLM]:
    provider = FakeLLM(replies)
    pulse = _noop if heartbeat is None else heartbeat
    result = run_chat(
        provider,
        message,
        budget(available_cents),
        PERIOD,
        heartbeat=pulse,
        user_id=user_id,
        spending_source=spending_source,
        previous_request=previous_request,
        history=history,
        record_evidence=record_evidence,
        plan_cap_cents=plan_cap_cents,
    )
    return result, provider


def test_planner_then_final_keeps_evidence_and_usage() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    result, provider = _run(_planner_then_final())
    assert len(provider.requests) == 2
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert "Here is a labeled estimate." not in result["answer"]
    assert result["plan"] == expected["plan"]
    assert result["budget"] == expected["budget"]
    assert result["request"] == expected["request"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] is None
    assert result["model_turns"] == 2
    assert result["planner_revisions"] == 1
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["tool_trace"] == [_success_trace("call-1", expected["evidence_id"])]
    _assert_public(result)
    first = provider.requests[0]
    assert first["system"] == SYSTEM_PROMPT
    for recipe_id in SUPPORTED_RECIPE_IDS:
        assert recipe_id in SYSTEM_PROMPT
    assert "arithmetic" in SYSTEM_PROMPT
    assert "servings" in SYSTEM_PROMPT
    assert "pantry" in SYSTEM_PROMPT
    assert "MUST NOT purchase" in SYSTEM_PROMPT
    assert "cross-contact" in SYSTEM_PROMPT
    assert "secrets" in SYSTEM_PROMPT
    assert first["tools"] == _chat_tools()
    second_messages = provider.requests[1]["messages"]
    assert isinstance(second_messages, list)
    tool_user = second_messages[-1]
    assert tool_user["role"] == "user"
    content = tool_user["content"]
    assert isinstance(content, list)
    assert content[0]["toolResult"]["toolUseId"] == "call-1"
    assert content[0]["toolResult"]["status"] == "success"
    json_body = content[0]["toolResult"]["content"][0]["json"]
    assert isinstance(json_body, dict)
    plan = expected["plan"]
    budget_payload = expected["budget"]
    assert isinstance(plan, dict)
    assert isinstance(budget_payload, dict)
    assert json_body["plan"] == plan
    assert json_body["budget"] == budget_payload
    assert json_body["currency"] == "USD"
    assert json_body["money_unit"] == "cents"
    assert json_body["money_display"] == {
        "total": _usd(cast(int, plan["total_cents"])),
        "available": _usd(cast(int, budget_payload["available_cents"])),
        "pending": _usd(cast(int, budget_payload["pending_cents"])),
    }
    assert "currency" not in expected
    assert "money_display" not in expected
    _validate_converse(
        cast(str, provider.requests[1]["system"]),
        cast(list[dict[str, object]], second_messages),
        cast(list[dict[str, object]], provider.requests[1]["tools"]),
    )


def test_plain_final_without_tool_is_clarification() -> None:
    result, provider = _run([_reply([_text_block("How many servings?")], "end_turn")])
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert "How many servings?" not in result["answer"]
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["model_turns"] == 1
    assert result["planner_revisions"] == 0
    assert result["usage"] == {"inputTokens": 1, "outputTokens": 1}


def test_followup_history_and_previous_request_are_context_only() -> None:
    history = [
        {"role": "user", "text": "plan tacos"},
        {"role": "assistant", "text": "I can plan chicken tacos."},
    ]
    original = copy.deepcopy(history)
    prev = previous()
    original_prev = copy.deepcopy(prev)
    result, provider = _run(
        _planner_then_final(),
        message="use two servings",
        history=history,
        previous_request=prev,
    )
    assert result["status"] == "planned"
    assert history == original
    assert prev == original_prev
    messages = provider.requests[0]["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "user", "content": [{"text": "plan tacos"}]}
    assert messages[1] == {
        "role": "assistant",
        "content": [{"text": "I can plan chicken tacos."}],
    }
    last = messages[2]
    assert last["role"] == "user"
    content = last["content"]
    assert isinstance(content, list)
    assert content[-1] == {"text": "use two servings"}
    context = json.loads(cast(str, content[0]["text"]))
    assert context["previous_request"]["pantry_ingredients"] == ["salt"]
    assert context["plan_cap_cents"] is None
    assert context["context_role"] == (
        "previous_request is prior state; apply latest explicit additions and removals"
    )
    dumped = json.dumps(provider.requests)
    assert _SECRET not in dumped
    _assert_public(result)


def test_three_planner_calls_in_one_turn_keep_last_valid() -> None:
    first = plan_args()
    second = plan_args(meals=[{"recipe_id": "bean_tacos", "servings": 2}])
    third = plan_args(meals=[{"recipe_id": "lentil_soup", "servings": 1}])
    expected = execute_plan(third, budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _tool_block("a", payload=first),
                _tool_block("b", payload=second),
                _tool_block("c", payload=third),
            ],
            "tool_use",
        ),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert result["status"] == "planned"
    assert result["planner_revisions"] == 3
    assert result["model_turns"] == 2
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["plan"] == expected["plan"]
    assert len(provider.requests) == 2
    nested = provider.requests[1]["messages"]
    assert isinstance(nested, list)
    user_blocks = nested[-1]["content"]
    assert isinstance(user_blocks, list)
    assert len(user_blocks) == 3
    assert user_blocks[0]["toolResult"]["toolUseId"] == "a"
    assert user_blocks[2]["toolResult"]["toolUseId"] == "c"


def test_parser_rejects_more_than_three_calls() -> None:
    blocks = [_tool_block(f"id-{index}") for index in range(MAX_TOOL_CALLS + 1)]
    provider = FakeLLM([_reply(blocks, "tool_use")])
    with pytest.raises(
        ChatProtocolError, match="assistant message is invalid"
    ) as caught:
        run_chat(provider, "plan", budget(), PERIOD)
    _assert_static(caught.value, "id-0")
    assert len(provider.requests) == 1


def test_eight_unsupported_turns_hit_model_cap_without_ninth_call() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block(f"u-{index}", name="purchase_items", payload={"token": "x"})],
            "tool_use",
        )
        for index in range(MAX_MODEL_TURNS)
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_MODEL_TURNS
    assert result["status"] == "limit"
    assert result["answer"] == _LIMIT
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["model_turns"] == MAX_MODEL_TURNS
    assert result["planner_revisions"] == 0
    assert result["usage"] == {
        "inputTokens": MAX_MODEL_TURNS,
        "outputTokens": MAX_MODEL_TURNS,
    }


def test_eighth_turn_may_finish_with_text() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block(f"u-{index}", name="lookup", payload={})],
            "tool_use",
        )
        for index in range(MAX_MODEL_TURNS - 1)
    ]
    replies.append(_reply([_text_block("Need a meal choice.")], "end_turn"))
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_MODEL_TURNS
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert "Need a meal choice." not in result["answer"]
    assert result["model_turns"] == MAX_MODEL_TURNS
    assert result["plan"] is None
    assert result["planner_revisions"] == 0


def test_fourth_planner_call_is_limit_and_drops_candidate() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block(f"p-{index}")], "tool_use")
        for index in range(MAX_PLANNER_REVISIONS + 1)
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_PLANNER_REVISIONS + 1
    assert result["status"] == "limit"
    assert result["answer"] == _LIMIT
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["model_turns"] == MAX_PLANNER_REVISIONS + 1
    assert result["planner_revisions"] == MAX_PLANNER_REVISIONS


def test_three_planner_revisions_then_final_is_planned() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block(f"p-{index}")], "tool_use")
        for index in range(MAX_PLANNER_REVISIONS)
    ]
    replies.append(_reply([_text_block("ready")], "end_turn"))
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_PLANNER_REVISIONS + 1
    assert result["status"] == "planned"
    assert result["planner_revisions"] == MAX_PLANNER_REVISIONS
    assert result["plan"] is not None
    assert result["evidence_id"] is not None
    assert result["evidence_revision_id"] is None


def test_invalid_planner_calls_count_toward_revision_cap() -> None:
    bad = plan_args(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block(f"bad-{index}", payload=bad)], "tool_use")
        for index in range(MAX_PLANNER_REVISIONS + 1)
    ]
    result, _provider = _run(replies)
    assert result["status"] == "limit"
    assert result["planner_revisions"] == MAX_PLANNER_REVISIONS
    assert result["plan"] is None
    assert result["model_turns"] == MAX_PLANNER_REVISIONS + 1


def test_invalid_later_call_clears_candidate() -> None:
    bad = plan_args(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok"), _tool_block("bad", payload=bad)],
            "tool_use",
        ),
        _reply([_text_block("I cannot finish that plan.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["planner_revisions"] == 2
    assert result["answer"] == CLARIFICATION
    assert "I cannot finish that plan." not in result["answer"]
    assert result["tool_trace"][0]["outcome"] == "success"
    assert result["tool_trace"][1] == _error_trace(
        TOOL_NAME, "bad", sequence=2, revision_index=2
    )


def test_unsupported_later_call_clears_candidate() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _tool_block("ok"),
                _tool_block("buy", name="purchase_items", payload={"token": _SECRET}),
            ],
            "tool_use",
        ),
        _reply([_text_block("I will not purchase items.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["planner_revisions"] == 1
    assert result["answer"] == CLARIFICATION
    assert "I will not purchase items." not in result["answer"]
    assert result["tool_trace"][1] == _error_trace(
        "unsupported", "buy", sequence=2, revision_index=None
    )
    _assert_public(result)
    assert "purchase_items" not in json.dumps(result["tool_trace"])


def test_invalid_then_valid_keeps_last_candidate() -> None:
    bad = plan_args(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    good = plan_args(meals=[{"recipe_id": "bean_tacos", "servings": 2}])
    expected = execute_plan(good, budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("bad", payload=bad), _tool_block("ok", payload=good)],
            "tool_use",
        ),
        _reply([_text_block("updated")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "planned"
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["plan"] == expected["plan"]


@pytest.mark.parametrize(
    "stop",
    [
        "max_tokens",
        "content_filtered",
        "stop_sequence",
        "guardrail_intervened",
        "model_context_window_exceeded",
    ],
)
def test_incomplete_stops_drop_plan(stop: str) -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("ok")], "tool_use"),
        _reply([_text_block("truncated plan")], stop),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["status"] == "incomplete"
    assert result["answer"] == _INCOMPLETE
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["model_turns"] == 2
    assert result["planner_revisions"] == 1


def test_blank_end_turn_is_incomplete_and_drops_plan() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("ok")], "tool_use"),
        _reply([_text_block("   ")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "incomplete"
    assert result["plan"] is None


def test_reasoning_is_stripped_from_next_request_and_result() -> None:
    hidden = {"text": "hidden plan"}
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                {"reasoningContent": hidden},
                _text_block("public", reasoning=hidden),
                _tool_block("call-1", reasoning=hidden),
            ],
            "tool_use",
        ),
        _reply([_text_block("ready", reasoning=hidden)], "end_turn"),
    ]
    result, provider = _run(replies)
    expected = execute_plan(plan_args(), budget(), PERIOD)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert "ready" not in result["answer"]
    dumped_result = json.dumps(result)
    assert "reasoningContent" not in dumped_result
    assert "hidden plan" not in dumped_result
    follow = json.dumps(provider.requests[1]["messages"])
    assert "reasoningContent" not in follow
    assert "hidden plan" not in follow
    assert "public" not in follow
    assistant = provider.requests[1]["messages"]
    assert isinstance(assistant, list)
    content = assistant[1]["content"]
    assert isinstance(content, list)
    assert content == [
        {
            "toolUse": {
                "toolUseId": "call-1",
                "name": TOOL_NAME,
                "input": plan_args(),
            }
        }
    ]
    user_blocks = assistant[2]["content"]
    assert isinstance(user_blocks, list)
    assert user_blocks[0]["toolResult"]["toolUseId"] == "call-1"


def test_tool_use_history_keeps_validated_calls_only() -> None:
    hidden = {"text": "hidden plan"}
    first = plan_args()
    second = plan_args(meals=[{"recipe_id": "bean_tacos", "servings": 2}])
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                {"reasoningContent": hidden},
                _text_block("I will call tools now.", reasoning=hidden),
                _tool_block("call-a", payload=first, reasoning=hidden),
                _text_block("and another", reasoning=hidden),
                _tool_block("call-b", payload=second, reasoning=hidden),
            ],
            "tool_use",
        ),
        _reply([_text_block("Here is a labeled estimate.")], "end_turn"),
    ]
    result, provider = _run(replies)
    expected = execute_plan(second, budget(), PERIOD)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert "Here is a labeled estimate." not in result["answer"]
    assert len(provider.requests) == 2
    second_messages = provider.requests[1]["messages"]
    assert isinstance(second_messages, list)
    assistant = second_messages[1]
    assert assistant["role"] == "assistant"
    content = assistant["content"]
    assert isinstance(content, list)
    assert content == [
        {
            "toolUse": {
                "toolUseId": "call-a",
                "name": TOOL_NAME,
                "input": first,
            }
        },
        {
            "toolUse": {
                "toolUseId": "call-b",
                "name": TOOL_NAME,
                "input": second,
            }
        },
    ]
    user_message = second_messages[2]
    assert user_message["role"] == "user"
    user_blocks = user_message["content"]
    assert isinstance(user_blocks, list)
    assert len(user_blocks) == 2
    assert user_blocks[0]["toolResult"]["toolUseId"] == "call-a"
    assert user_blocks[1]["toolResult"]["toolUseId"] == "call-b"
    dumped = json.dumps(second_messages)
    assert "reasoningContent" not in dumped
    assert "hidden plan" not in dumped
    assert "I will call tools now." not in dumped
    assert "and another" not in dumped
    _assert_public(result)
    _validate_converse(
        cast(str, provider.requests[1]["system"]),
        cast(list[dict[str, object]], second_messages),
        cast(list[dict[str, object]], provider.requests[1]["tools"]),
    )


def test_duplicate_ids_raise_protocol_error() -> None:
    provider = FakeLLM([_reply([_tool_block("dup"), _tool_block("dup")], "tool_use")])
    with pytest.raises(
        ChatProtocolError, match="assistant message is invalid"
    ) as caught:
        run_chat(provider, "plan", budget(), PERIOD)
    _assert_static(caught.value, "dup")
    assert _SECRET not in str(caught.value)


def test_duplicate_ids_across_turns_raise_protocol_error() -> None:
    provider = FakeLLM(
        [
            _reply([_tool_block("same")], "tool_use"),
            _reply([_tool_block("same")], "tool_use"),
        ]
    )
    with pytest.raises(
        ChatProtocolError, match="assistant message is invalid"
    ) as caught:
        run_chat(provider, "plan", budget(), PERIOD)
    _assert_static(caught.value, "same")
    assert len(provider.requests) == 2


def test_provider_secret_error_has_no_raw_context_or_cause() -> None:
    provider = FakeLLM([RuntimeError(_SECRET)])
    with pytest.raises(ChatUnavailable) as caught:
        run_chat(provider, "plan", budget(), PERIOD)
    assert str(caught.value) == _UNAVAILABLE
    _assert_static(caught.value, _SECRET)
    assert len(provider.requests) == 1


def test_provider_protocol_error_becomes_unavailable_without_chain() -> None:
    error = ChatProtocolError("provider-secret-sentinel")
    error.__cause__ = RuntimeError(_SECRET)
    error.__context__ = RuntimeError(_SECRET)
    provider = FakeLLM([error])
    with pytest.raises(ChatUnavailable) as caught:
        run_chat(provider, "plan", budget(), PERIOD)
    assert str(caught.value) == _UNAVAILABLE
    _assert_static(caught.value, _SECRET)
    _assert_static(caught.value, "provider-secret-sentinel")
    assert len(provider.requests) == 1


def test_heartbeat_loss_before_provider_propagates() -> None:
    provider = FakeLLM(_planner_then_final())
    beats = Heartbeats(fail_at=1)
    with pytest.raises(RuntimeError, match="heartbeat-lost") as caught:
        run_chat(provider, "plan", budget(), PERIOD, heartbeat=beats)
    _assert_static(caught.value, _SECRET)
    assert len(provider.requests) == 0
    assert beats.count == 1


def test_heartbeat_loss_after_provider_propagates() -> None:
    provider = FakeLLM(_planner_then_final())
    beats = Heartbeats(fail_at=2)
    with pytest.raises(RuntimeError, match="heartbeat-lost"):
        run_chat(provider, "plan", budget(), PERIOD, heartbeat=beats)
    assert len(provider.requests) == 1
    assert beats.count == 2


def test_heartbeat_loss_before_tool_propagates() -> None:
    provider = FakeLLM(_planner_then_final())
    beats = Heartbeats(fail_at=3)
    with pytest.raises(RuntimeError, match="heartbeat-lost"):
        run_chat(provider, "plan", budget(), PERIOD, heartbeat=beats)
    assert len(provider.requests) == 1
    assert beats.count == 3


def test_usage_is_none_when_one_response_is_unknown() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok")],
            "tool_use",
            usage={"inputTokens": 4, "outputTokens": 5},
        ),
        _reply([_text_block("done")], "end_turn", omit_usage=True),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "planned"
    assert result["usage"] is None


def test_usage_sums_only_when_every_response_is_valid() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok")],
            "tool_use",
            usage={"inputTokens": 4, "outputTokens": 5, "totalTokens": 9},
        ),
        _reply(
            [_text_block("done")],
            "end_turn",
            usage={"inputTokens": 6, "outputTokens": 7},
        ),
    ]
    result, _provider = _run(replies)
    assert result["usage"] == {"inputTokens": 10, "outputTokens": 12}
    assert set(cast(dict[str, int], result["usage"])) == {"inputTokens", "outputTokens"}


def test_zero_token_counts_are_valid_usage() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok")],
            "tool_use",
            usage={"inputTokens": 0, "outputTokens": 0},
        ),
        _reply(
            [_text_block("done")],
            "end_turn",
            usage={"inputTokens": 0, "outputTokens": 0},
        ),
    ]
    result, _provider = _run(replies)
    assert result["usage"] == {"inputTokens": 0, "outputTokens": 0}


def test_exact_server_caps() -> None:
    assert MAX_MODEL_TURNS == 8
    assert MAX_PLANNER_REVISIONS == 3


def test_system_prompt_states_usd_cents_contract() -> None:
    assert "integer USD cents" in SYSTEM_PROMPT
    assert "*_cents" in SYSTEM_PROMPT
    assert "yen" in SYSTEM_PROMPT
    assert "whole-currency" in SYSTEM_PROMPT
    assert "money_display" in SYSTEM_PROMPT
    assert "estimate panel" in SYSTEM_PROMPT
    assert "concise plain-text" in SYSTEM_PROMPT
    assert "get_budget_summary" in SYSTEM_PROMPT
    assert "budget questions" in SYSTEM_PROMPT
    assert "server money strings" in SYSTEM_PROMPT


def test_system_prompt_offers_catalog_alternatives() -> None:
    assert "not in the catalog" in SYSTEM_PROMPT
    assert "MUST NOT invent a recipe" in SYSTEM_PROMPT
    assert "up to three catalog meals" in SYSTEM_PROMPT
    assert "stated diet" in SYSTEM_PROMPT
    assert "which one to plan" in SYSTEM_PROMPT
    assert "Name meals in plain words in replies, not as catalog IDs." in SYSTEM_PROMPT
    assert "Latest pantry additions and removals override prior pantry." in (
        SYSTEM_PROMPT
    )
    assert "shopping list does not mean purchasing it." in SYSTEM_PROMPT
    assert (
        "When plan_cap_cents is null, you MUST NOT invent a cap from "
        "available spending." in SYSTEM_PROMPT
    )


def test_system_prompt_requires_restriction_clarification() -> None:
    assert "A fixed recipe MUST NOT silently omit a conflicting ingredient." in (
        SYSTEM_PROMPT
    )
    assert (
        "Put a restriction term you cannot map in ingredient_exclusions exactly "
        "as the user wrote it." in SYSTEM_PROMPT
    )
    assert (
        "You MUST NOT translate a restriction group such as nightshades into "
        "catalog IDs." in SYSTEM_PROMPT
    )
    assert "The tool rejects unknown terms and asks the user." in SYSTEM_PROMPT
    assert "Ask the user before you choose an alternative." in SYSTEM_PROMPT


def test_unknown_restrictions_use_tool_clarification() -> None:
    args = plan_args(
        meals=[{"recipe_id": "bean_tacos", "servings": 2}],
        ingredient_exclusions=["mystery spice", "nightshades"],
    )
    result, provider = _run(
        _planner_then_final(payload=args),
        message=(
            "Plan 2 servings of bean tacos. I cannot have mystery spice or nightshades."
        ),
    )
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["answer"] == _UNKNOWN_RESTRICTION
    messages = cast(list[dict[str, object]], provider.requests[1]["messages"])
    assert "unsupported_ingredient" in json.dumps(messages)


def test_system_prompt_exposes_catalog_ingredient_id_name_pairs() -> None:
    assert "olive_oil:olive oil" in SYSTEM_PROMPT
    for ingredient_id, ingredient in INGREDIENTS.items():
        assert f"{ingredient_id}:{ingredient.name}" in SYSTEM_PROMPT
    assert (
        "You MUST use only those exact catalog IDs for pantry and exclusion "
        "tool fields." in SYSTEM_PROMPT
    )
    assert "You MUST ask for clarification for unknown terms." in SYSTEM_PROMPT
    assert "You MUST NOT invent aliases or mappings." in SYSTEM_PROMPT
    result, provider = _run([_reply([_text_block("How many servings?")], "end_turn")])
    assert result["status"] == "clarification"
    first = provider.requests[0]
    assert first["system"] == SYSTEM_PROMPT
    assert "olive_oil:olive oil" in cast(str, first["system"])
    for ingredient_id, ingredient in INGREDIENTS.items():
        assert f"{ingredient_id}:{ingredient.name}" in cast(str, first["system"])


def test_invalid_request_uses_context_validation() -> None:
    provider = FakeLLM([])
    with pytest.raises(ChatProtocolError, match="request is invalid") as caught:
        run_chat(provider, " ", budget(), PERIOD)
    _assert_static(caught.value, _SECRET)
    assert len(provider.requests) == 0
    with pytest.raises(ChatProtocolError, match="request is invalid") as cap_caught:
        run_chat(provider, "plan", budget(), PERIOD, plan_cap_cents=-1)
    _assert_static(cap_caught.value, "-1")
    assert len(provider.requests) == 0


def test_needs_revision_keeps_uncapped_plan() -> None:
    payload = plan_args(plan_cap_cents=100)
    expected = execute_plan(payload, budget(), PERIOD)
    result, _provider = _run(
        _planner_then_final(payload=payload), available_cents=1_000
    )
    assert result["status"] == "needs_revision"
    assert result["plan"] == expected["plan"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] is None
    plan = result["plan"]
    assert isinstance(plan, dict)
    assert plan["accepted"] is False


def test_record_evidence_runs_before_next_provider_turn() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    seen: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(dict(payload))
        assert "evidence_revision_id" not in payload
        return _REV

    result, provider = _run(_planner_then_final(), record_evidence=record)
    assert seen == [expected]
    assert result["status"] == "planned"
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] == _REV
    assert result["tool_trace"] == [
        _success_trace("call-1", expected["evidence_id"], revision_id=_REV)
    ]
    assert len(provider.requests) == 2
    second_messages = provider.requests[1]["messages"]
    assert isinstance(second_messages, list)
    tool_user = second_messages[-1]
    content = tool_user["content"]
    assert isinstance(content, list)
    json_body = content[0]["toolResult"]["content"][0]["json"]
    assert json_body["evidence_revision_id"] == _REV
    assert json_body["evidence_id"] == expected["evidence_id"]
    assert json_body["currency"] == "USD"
    assert json_body["money_unit"] == "cents"
    assert "money_display" in json_body
    assert "currency" not in expected
    assert "money_display" not in seen[0]
    _validate_converse(
        cast(str, provider.requests[1]["system"]),
        cast(list[dict[str, object]], second_messages),
        cast(list[dict[str, object]], provider.requests[1]["tools"]),
    )
    _assert_public(result)


def test_record_evidence_error_skips_success_and_followup() -> None:
    def record(payload: dict[str, object]) -> str:
        raise RuntimeError("store-failed")

    provider = FakeLLM(_planner_then_final())
    with pytest.raises(RuntimeError, match="store-failed") as caught:
        run_chat(provider, "plan", budget(), PERIOD, record_evidence=record)
    _assert_static(caught.value, _SECRET)
    assert len(provider.requests) == 1


def test_invalid_record_id_skips_followup() -> None:
    def record(payload: dict[str, object]) -> str:
        return "NOT-HEX"

    provider = FakeLLM(_planner_then_final())
    with pytest.raises(
        ChatProtocolError, match="evidence revision id is invalid"
    ) as caught:
        run_chat(provider, "plan", budget(), PERIOD, record_evidence=record)
    _assert_static(caught.value, "NOT-HEX")
    assert len(provider.requests) == 1


def test_repeated_revision_id_two_revisions_stay_ordered() -> None:
    def record(payload: dict[str, object]) -> str:
        return _REV

    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("a"), _tool_block("b")],
            "tool_use",
        ),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies, record_evidence=record)
    assert result["status"] == "planned"
    assert result["evidence_revision_id"] == _REV
    assert result["planner_revisions"] == 2
    assert result["tool_trace"] == [
        _success_trace("a", expected["evidence_id"], revision_id=_REV),
        _success_trace(
            "b",
            expected["evidence_id"],
            sequence=2,
            revision_index=2,
            revision_id=_REV,
        ),
    ]
    dumped = json.dumps(result["tool_trace"])
    assert "chicken_tacos" not in dumped
    assert "reasoningContent" not in dumped
    second_messages = provider.requests[1]["messages"]
    assert isinstance(second_messages, list)
    _validate_converse(
        cast(str, provider.requests[1]["system"]),
        cast(list[dict[str, object]], second_messages),
        cast(list[dict[str, object]], provider.requests[1]["tools"]),
    )


def test_invalid_and_unsupported_trace_indices() -> None:
    bad = plan_args(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _tool_block("bad", payload=bad),
                _tool_block("buy", name="purchase_items", payload={"token": _SECRET}),
                _tool_block("ok"),
            ],
            "tool_use",
        ),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "planned"
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] is None
    assert result["tool_trace"] == [
        _error_trace(TOOL_NAME, "bad"),
        _error_trace("unsupported", "buy", sequence=2, revision_index=None),
        _success_trace("ok", expected["evidence_id"], sequence=3, revision_index=2),
    ]
    dumped = json.dumps(result["tool_trace"])
    assert _SECRET not in dumped
    assert "purchase_items" not in dumped
    assert "servings" not in dumped
    assert "reasoningContent" not in dumped


def test_adversarial_final_text_cannot_override_validated_plan() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    plan = expected["plan"]
    assert isinstance(plan, dict)
    total = cast(int, plan["total_cents"])
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("call-1")], "tool_use"),
        _reply(
            [
                _text_block(
                    "This is safe for peanut allergy and cross-contact. "
                    "Accepted total USD $2.00. The plan is complete."
                )
            ],
            "end_turn",
        ),
    ]
    result, _provider = _run(replies)
    answer = result["answer"]
    assert result["status"] == "planned"
    assert result["plan"] == expected["plan"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert answer == render_public_answer(expected)
    assert "peanut" not in answer
    assert "cross-contact" not in answer
    assert "allergy" not in answer
    assert "USD $2.00" not in answer
    assert _usd(total) in answer
    assert SAMPLE_ESTIMATE_NOTICE in answer


def test_exclusion_after_success_drops_prior_evidence() -> None:
    excluded = plan_args(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    )
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok"), _tool_block("ex", payload=excluded)],
            "tool_use",
        ),
        _reply(
            [
                _text_block(
                    "The earlier plan is valid and costs USD $1.00. "
                    "It is safe for onion allergy."
                )
            ],
            "end_turn",
        ),
    ]
    result, _provider = _run(replies)
    answer = result["answer"]
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert "onion" in answer
    assert "Change the recipe or the restriction." in answer
    assert "vegetable_pasta" not in answer
    assert "USD $1.00" not in answer
    assert "safe" not in answer
    assert "valid" not in answer


def test_exclusion_then_unsupported_tool_is_generic_clarification() -> None:
    excluded = plan_args(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    )
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _tool_block("ex", payload=excluded),
                _tool_block("buy", name="purchase_items", payload={"token": _SECRET}),
            ],
            "tool_use",
        ),
        _reply([_text_block("I will not purchase items.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert "onion" not in result["answer"]
    assert "Change the recipe or the restriction." not in result["answer"]
    assert "I will not purchase items." not in result["answer"]
    _assert_public(result)


def test_malformed_later_error_clears_exclusion_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_dispatch = loop.dispatch
    excluded = plan_args(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    )

    def fake_dispatch(
        call: ToolCall,
        budget_value: BudgetResult,
        period: date,
        user_id: int,
        source: SpendingSource,
        trace: list[dict[str, object]],
        record_evidence: EvidenceRecorder | None = None,
    ) -> tuple[dict[str, object] | None, dict[str, object]]:
        if call.name != TOOL_NAME:
            return None, {
                "toolResult": {
                    "toolUseId": call.tool_use_id,
                    "status": "error",
                    "content": [{"text": "generic failure"}],
                }
            }
        return real_dispatch(
            call,
            budget_value,
            period,
            user_id,
            source,
            trace,
            record_evidence=record_evidence,
        )

    monkeypatch.setattr(loop, "dispatch", fake_dispatch)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _tool_block("ex", payload=excluded),
                _tool_block("later", name="lookup", payload={}),
            ],
            "tool_use",
        ),
        _reply([_text_block("Need a meal choice.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert "onion" not in result["answer"]
    assert "Change the recipe or the restriction." not in result["answer"]
    assert "Need a meal choice." not in result["answer"]
    _assert_public(result)


def test_limit_and_incomplete_drop_recorded_revision_id() -> None:
    def record(payload: dict[str, object]) -> str:
        return _REV

    limit_replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block(f"p-{index}")], "tool_use")
        for index in range(MAX_PLANNER_REVISIONS + 1)
    ]
    limit_result, _limit_provider = _run(limit_replies, record_evidence=record)
    assert limit_result["status"] == "limit"
    assert limit_result["plan"] is None
    assert limit_result["evidence_id"] is None
    assert limit_result["evidence_revision_id"] is None
    incomplete_replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("ok")], "tool_use"),
        _reply([_text_block("truncated plan")], "max_tokens"),
    ]
    incomplete, _provider = _run(incomplete_replies, record_evidence=record)
    assert incomplete["status"] == "incomplete"
    assert incomplete["plan"] is None
    assert incomplete["evidence_id"] is None
    assert incomplete["evidence_revision_id"] is None


def test_followup_provider_receives_cap_and_latest_pantry_context() -> None:
    prev = previous(pantry_ingredients=["salt", "oil"])
    result, provider = _run(
        _planner_then_final(),
        message="remove oil and add rice",
        history=[
            {"role": "user", "text": "plan tacos"},
            {"role": "assistant", "text": "I can plan chicken tacos."},
        ],
        previous_request=prev,
        plan_cap_cents=2_000,
        available_cents=10_000,
    )
    assert result["status"] == "planned"
    assert len(provider.requests) == 2
    first_prompt = provider.requests[0]["system"]
    assert first_prompt == SYSTEM_PROMPT
    assert "MUST preserve that cap or lower it" in SYSTEM_PROMPT
    assert "MUST NOT clear or raise the cap" in SYSTEM_PROMPT
    assert (
        "A cap may change only when the user changes budget controls." in SYSTEM_PROMPT
    )
    for request in provider.requests:
        assert request["system"] == SYSTEM_PROMPT
        messages = request["messages"]
        assert isinstance(messages, list)
        current = messages[2]
        assert isinstance(current, dict)
        content = current["content"]
        assert isinstance(content, list)
        assert content[-1] == {"text": "remove oil and add rice"}
        context = json.loads(cast(str, content[0]["text"]))
        assert context["plan_cap_cents"] == 2_000
        assert context["budget"]["available_cents"] == 10_000
        assert context["previous_request"]["pantry_ingredients"] == ["salt", "oil"]
        assert context["context_role"] == (
            "previous_request is prior state; apply latest explicit "
            "additions and removals"
        )


@pytest.mark.parametrize(
    ("reason", "answer"),
    [
        (
            "secrets",
            "I cannot provide credentials or raw bank records. "
            "I can help plan meals using the budget summary.",
        ),
        (
            "purchase",
            "I cannot buy items or place orders. I can help prepare a grocery plan.",
        ),
        (
            "external_url",
            "I cannot open external links or place orders. "
            "I can help prepare a grocery plan.",
        ),
    ],
)
def test_structured_refusal_without_tool_use(reason: str, answer: str) -> None:
    body = '{"refusal":"' + reason + '"}'
    result, provider = _run([_reply([_text_block(body)], "end_turn")])
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["answer"] == answer
    assert body not in result["answer"]
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["meal_nutrition"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["tool_trace"] == []
    assert result["model_turns"] == 1
    assert result["planner_revisions"] == 0
    assert result["usage"] == {"inputTokens": 1, "outputTokens": 1}
    _assert_public(result)


def test_structured_refusal_after_plan_clears_public_fields() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("call-1")], "tool_use"),
        _reply([_text_block('{"refusal":"purchase"}')], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == (
        "I cannot buy items or place orders. I can help prepare a grocery plan."
    )
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["meal_nutrition"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["tool_trace"] == [_success_trace("call-1", expected["evidence_id"])]
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["model_turns"] == 2
    assert result["planner_revisions"] == 1
    assert '{"refusal"' not in json.dumps(result)
    _assert_public(result)


def test_malformed_refusal_does_not_echo_sentinel() -> None:
    raw = '{"refusal": "' + _SECRET + '" leftover'
    result, _provider = _run([_reply([_text_block(raw)], "end_turn")])
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert _SECRET not in json.dumps(result)
    assert "refusal" not in result["answer"]
    _assert_public(result)


def test_pantry_owned_ingredient_request_stays_planner_capable() -> None:
    result, provider = _run(
        _planner_then_final(),
        message="add the pantry-owned salt back to the shopping list",
    )
    assert result["status"] == "planned"
    assert result["planner_revisions"] == 1
    assert result["plan"] is not None
    assert result["evidence_id"] is not None
    assert result["answer"] == render_public_answer(
        execute_plan(plan_args(), budget(), PERIOD)
    )
    assert provider.requests[0]["tools"] == _chat_tools()
    assert "ordinary planning" in SYSTEM_PROMPT
    assert "pantry-owned ingredient" in SYSTEM_PROMPT


def test_system_prompt_requests_structured_refusal() -> None:
    assert '{"refusal":"secrets"}' in SYSTEM_PROMPT
    assert '{"refusal":"purchase"}' in SYSTEM_PROMPT
    assert '{"refusal":"external_url"}' in SYSTEM_PROMPT
    assert "MUST NOT call the planning tool" in SYSTEM_PROMPT
    assert "credentials or raw bank records" in SYSTEM_PROMPT
    assert "actual purchases or orders" in SYSTEM_PROMPT
    assert "opening external URLs" in SYSTEM_PROMPT
    assert "pantry-owned ingredient" in SYSTEM_PROMPT
    assert "ordinary planning" in SYSTEM_PROMPT
    assert "MUST NOT purchase" in SYSTEM_PROMPT
    assert "secrets" in SYSTEM_PROMPT
    assert (
        "For ordinary replies, write a concise plain-text final reply." in SYSTEM_PROMPT
    )


def test_summary_only_uses_budget_answer_without_plan() -> None:
    expected = budget_summary_answer(budget(), PERIOD, spending_source="fixture")
    summary = execute_budget_summary({}, budget(), PERIOD, spending_source="fixture")
    seen: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(payload)
        return _REV

    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_text_block("You have plenty of money left.")], "end_turn"),
    ]
    result, provider = _run(replies, record_evidence=record)
    assert result["status"] == "clarification"
    assert result["answer"] == expected
    assert "plenty of money" not in result["answer"]
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["meal_nutrition"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["planner_revisions"] == 0
    assert result["model_turns"] == 2
    assert result["tool_trace"] == [_budget_trace("s1")]
    assert seen == []
    second_messages = provider.requests[1]["messages"]
    assert isinstance(second_messages, list)
    tool_user = second_messages[-1]
    content = tool_user["content"]
    assert isinstance(content, list)
    json_body = content[0]["toolResult"]["content"][0]["json"]
    assert json_body == summary
    _assert_public(result)


def test_plan_then_summary_keeps_plan() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("p1")], "tool_use"),
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_text_block("Here is the budget and the plan.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert "Here is the budget" not in result["answer"]
    assert result["plan"] == expected["plan"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["planner_revisions"] == 1
    assert result["tool_trace"] == [
        _success_trace("p1", expected["evidence_id"]),
        _budget_trace("s1", sequence=2),
    ]


def test_summary_then_plan_returns_plan() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_tool_block("p1")], "tool_use"),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["plan"] == expected["plan"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["planner_revisions"] == 1
    assert result["tool_trace"] == [
        _budget_trace("s1"),
        _success_trace("p1", expected["evidence_id"], sequence=2),
    ]


def test_invalid_summary_after_plan_clears_candidate() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("p1")], "tool_use"),
        _reply(
            [_budget_block("s1", payload={"cap": 1, "identity": _SECRET})],
            "tool_use",
        ),
        _reply([_text_block("The earlier plan is still valid.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert "still valid" not in result["answer"]
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["planner_revisions"] == 1
    assert result["tool_trace"][0] == _success_trace("p1", expected["evidence_id"])
    assert result["tool_trace"][1] == _budget_trace("s1", sequence=2, outcome="error")
    _assert_public(result)


def test_summary_then_later_failure_uses_clarification() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply(
            [_tool_block("buy", name="purchase_items", payload={"token": _SECRET})],
            "tool_use",
        ),
        _reply([_text_block("I will not purchase items.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["planner_revisions"] == 0
    assert result["tool_trace"] == [
        _budget_trace("s1"),
        _error_trace("unsupported", "buy", sequence=2, revision_index=None),
    ]
    _assert_public(result)


def test_diet_conflict_returns_public_clarification() -> None:
    args = plan_args(
        meals=[{"recipe_id": "chicken_tacos", "servings": 2}], diet="vegan"
    )
    result, _provider = _run(_planner_then_final(payload=args))
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["answer"] == (
        "Chicken tacos are not vegan. Change the recipe or the restriction."
    )
    assert result["tool_trace"] == [_error_trace(TOOL_NAME, "call-1")]
    _assert_public(result)


def test_system_prompt_routes_named_meal_diet_conflicts_to_tool() -> None:
    assert (
        "A fixed recipe MUST NOT silently omit a conflicting ingredient. "
        "When a named catalog meal conflicts with the stated diet, call "
        "plan_groceries with both; the tool reports the conflict. "
    ) in SYSTEM_PROMPT


def test_typed_clarification_then_summary_keeps_typed_error() -> None:
    excluded = plan_args(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    )
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("ex", payload=excluded)], "tool_use"),
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_text_block("Here is your remaining budget.")], "end_turn"),
    ]
    result, _provider = _run(replies)
    answer = result["answer"]
    assert result["status"] == "clarification"
    assert "onion" in answer
    assert "Change the recipe or the restriction." in answer
    assert "Here is your remaining budget." not in answer
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["planner_revisions"] == 1
    assert result["tool_trace"][0] == _error_trace(TOOL_NAME, "ex")
    assert result["tool_trace"][1] == _budget_trace("s1", sequence=2)


def test_refusal_after_summary_drops_summary_answer() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_text_block('{"refusal":"secrets"}')], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == (
        "I cannot provide credentials or raw bank records. "
        "I can help plan meals using the budget summary."
    )
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["evidence_id"] is None
    assert result["planner_revisions"] == 0
    assert result["tool_trace"] == [_budget_trace("s1")]
    assert '{"refusal"' not in json.dumps(result)
    _assert_public(result)


def test_invalid_summary_clears_prior_summary_fallback() -> None:
    expected = budget_summary_answer(budget(), PERIOD, spending_source="fixture")
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply(
            [_budget_block("s2", payload={"transactions": [_SECRET]})],
            "tool_use",
        ),
        _reply([_text_block("Available USD $99.00")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert result["answer"] != expected
    assert "USD $99.00" not in result["answer"]
    assert result["plan"] is None
    assert result["planner_revisions"] == 0
    _assert_public(result)


def test_three_planner_revisions_plus_summaries_then_fourth_hits_limit() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1"), _tool_block("p1")], "tool_use"),
        _reply([_tool_block("p2")], "tool_use"),
        _reply([_budget_block("s2"), _tool_block("p3")], "tool_use"),
        _reply([_text_block("ready")], "end_turn"),
    ]
    planned, _provider = _run(replies)
    assert planned["status"] == "planned"
    assert planned["planner_revisions"] == MAX_PLANNER_REVISIONS
    assert planned["plan"] is not None
    assert planned["evidence_id"] is not None
    limit_replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1"), _tool_block("p1")], "tool_use"),
        _reply([_tool_block("p2")], "tool_use"),
        _reply([_budget_block("s2"), _tool_block("p3")], "tool_use"),
        _reply([_tool_block("p4")], "tool_use"),
    ]
    limited, provider = _run(limit_replies)
    assert len(provider.requests) == MAX_PLANNER_REVISIONS + 1
    assert limited["status"] == "limit"
    assert limited["answer"] == _LIMIT
    assert limited["plan"] is None
    assert limited["evidence_id"] is None
    assert limited["planner_revisions"] == MAX_PLANNER_REVISIONS


def test_eight_summary_rounds_hit_model_cap_with_zero_planner() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_budget_block(f"s-{turn}-{index}") for index in range(MAX_TOOL_CALLS)],
            "tool_use",
        )
        for turn in range(MAX_MODEL_TURNS)
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_MODEL_TURNS
    assert result["status"] == "limit"
    assert result["answer"] == _LIMIT
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["planner_revisions"] == 0
    assert len(result["tool_trace"]) == 24
    assert result["tool_trace"] == [
        _budget_trace(
            f"s-{turn}-{index}",
            sequence=turn * MAX_TOOL_CALLS + index + 1,
        )
        for turn in range(MAX_MODEL_TURNS)
        for index in range(MAX_TOOL_CALLS)
    ]
