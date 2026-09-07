from __future__ import annotations

import copy
import json
from datetime import date
from typing import Literal, cast

import pytest
from botocore.session import Session
from botocore.validate import validate_parameters

from app.agent.chat_loop import (
    MAX_MODEL_TURNS,
    MAX_PLANNER_REVISIONS,
    SYSTEM_PROMPT,
    ChatUnavailable,
    run_chat,
)
from app.agent.chat_messages import MAX_TOOL_CALLS, ChatProtocolError
from app.agent.planning_tool import TOOL_NAME, execute_plan, planner_tool_spec
from app.domain.budget import BudgetResult
from app.domain.grocery import SUPPORTED_RECIPE_IDS

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


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 250, False, ())


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
    )
    return result, provider


def test_planner_then_final_keeps_evidence_and_usage() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    result, provider = _run(_planner_then_final())
    assert len(provider.requests) == 2
    assert result["status"] == "planned"
    assert result["answer"] == "Here is a labeled estimate."
    assert result["plan"] == expected["plan"]
    assert result["budget"] == expected["budget"]
    assert result["request"] == expected["request"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["model_turns"] == 2
    assert result["planner_revisions"] == 1
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["tool_trace"] == [
        {
            "tool": TOOL_NAME,
            "outcome": "success",
            "evidence_id": expected["evidence_id"],
        }
    ]
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
    assert first["tools"] == [planner_tool_spec()]
    second_messages = provider.requests[1]["messages"]
    assert isinstance(second_messages, list)
    tool_user = second_messages[-1]
    assert tool_user["role"] == "user"
    content = tool_user["content"]
    assert isinstance(content, list)
    assert content[0]["toolResult"]["toolUseId"] == "call-1"
    assert content[0]["toolResult"]["status"] == "success"
    _validate_converse(
        cast(str, provider.requests[1]["system"]),
        cast(list[dict[str, object]], second_messages),
        cast(list[dict[str, object]], provider.requests[1]["tools"]),
    )


def test_plain_final_without_tool_is_clarification() -> None:
    result, provider = _run([_reply([_text_block("How many servings?")], "end_turn")])
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["answer"] == "How many servings?"
    assert result["plan"] is None
    assert result["evidence_id"] is None
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
    assert content[0] == {"text": "use two servings"}
    context = json.loads(cast(str, content[1]["text"]))
    assert context["previous_request"]["pantry_ingredients"] == ["salt"]
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
    assert result["planner_revisions"] == 2
    assert result["tool_trace"][0]["outcome"] == "success"
    assert result["tool_trace"][1] == {"tool": TOOL_NAME, "outcome": "error"}


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
    assert result["planner_revisions"] == 1
    assert result["tool_trace"][1] == {"tool": "unsupported", "outcome": "error"}
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
    assert result["status"] == "planned"
    dumped_result = json.dumps(result)
    assert "reasoningContent" not in dumped_result
    assert "hidden plan" not in dumped_result
    follow = json.dumps(provider.requests[1]["messages"])
    assert "reasoningContent" not in follow
    assert "hidden plan" not in follow
    assistant = provider.requests[1]["messages"]
    assert isinstance(assistant, list)
    content = assistant[1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"text": "public"}
    assert "reasoningContent" not in content[1]


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


def test_invalid_request_uses_context_validation() -> None:
    provider = FakeLLM([])
    with pytest.raises(ChatProtocolError, match="request is invalid") as caught:
        run_chat(provider, " ", budget(), PERIOD)
    _assert_static(caught.value, _SECRET)
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
    plan = result["plan"]
    assert isinstance(plan, dict)
    assert plan["accepted"] is False
