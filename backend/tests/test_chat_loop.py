from __future__ import annotations

import copy
import json
from datetime import date
from itertools import permutations
from typing import Any, Literal, cast

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
from app.agent.catalog_tool import (
    DISCOVERY_ERROR,
    catalog_answer,
    catalog_tool_spec,
    execute_catalog_search,
)
from app.agent.catalog_tool import (
    TOOL_NAME as CATALOG_TOOL_NAME,
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
from app.agent.plan_tools import (
    GET_MEAL_TOOL,
    GET_PLAN_TOOL,
    get_meal_tool_spec,
    get_plan_tool_spec,
)
from app.agent.planning_tool import TOOL_NAME, execute_plan, planner_tool_spec
from app.agent.price_tool import PRICE_TOOL, execute_price_lines, price_tool_spec
from app.agent.read_answers import read_tool_answer
from app.agent.substitute_tool import (
    SUBSTITUTE_TOOL,
    execute_substitute,
    substitute_tool_spec,
)
from app.domain.budget import BudgetResult, SpendingSource
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS
from app.domain.meal_tags import SEARCH_TERMS
from app.domain.plan_revision import PlanRevisionInput

PERIOD = date(2026, 9, 1)
# Interim budget while chat-arch phases 1-2 add tools; phase 3 lowers it.
PROMPT_AND_TOOLS_BUDGET = 16000
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
    return [
        planner_tool_spec(),
        budget_tool_spec(),
        catalog_tool_spec(),
        get_plan_tool_spec(),
        get_meal_tool_spec(),
        substitute_tool_spec(),
        price_tool_spec(),
    ]


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


def test_accepted_plan_finishes_without_final_and_keeps_evidence_and_usage() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    result, provider = _run(_planner_then_final())
    assert len(provider.requests) == 1
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert "Here is a labeled estimate." not in result["answer"]
    assert result["plan"] == expected["plan"]
    assert result["budget"] == expected["budget"]
    assert result["request"] == expected["request"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] is None
    assert result["model_turns"] == 1
    assert result["planner_revisions"] == 1
    assert result["usage"] == {"inputTokens": 1, "outputTokens": 1}
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


def test_nonterminal_plan_result_keeps_server_money_fields() -> None:
    args = plan_args(plan_cap_cents=100)
    expected = execute_plan(args, budget(), PERIOD)
    result, provider = _run(_planner_then_final(payload=args))
    assert result["status"] == "needs_revision"
    assert len(provider.requests) == 2
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


def test_get_plan_turn_is_not_a_fast_return_and_keeps_reply_state() -> None:
    result, provider = _run(
        [
            _reply([_tool_block("p1", name=GET_PLAN_TOOL, payload={})], "tool_use"),
            _reply([_text_block("Your plan is empty.")], "end_turn"),
        ]
    )
    assert len(provider.requests) == 2
    assert result["status"] == "clarification"
    assert result["answer"] == "Your plan has no meals yet."
    assert result["plan"] is None
    trace = cast(list[dict[str, object]], result["tool_trace"])
    assert [item["tool"] for item in trace] == [GET_PLAN_TOOL]
    assert provider.requests[0]["tools"] == _chat_tools()
    assert "Call get_plan to read the user's current plan." in cast(
        str, provider.requests[0]["system"]
    )


def test_get_meal_error_does_not_set_candidate_or_error() -> None:
    result, _ = _run(
        [
            _reply(
                [_tool_block("m1", name=GET_MEAL_TOOL, payload={"recipe_id": "x"})],
                "tool_use",
            ),
            _reply([_text_block("Sorry.")], "end_turn"),
        ]
    )
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert cast(list[dict[str, object]], result["tool_trace"])[0]["outcome"] == "error"


_SWAP_ARGS: dict[str, object] = {
    "recipe_id": "chicken_tacos",
    "servings": 2,
    "replace_ingredient_id": "chicken_breast",
    "with_ingredient_id": "chickpeas",
}


def test_what_if_substitute_traces_and_leaves_reply_state_alone() -> None:
    result, provider = _run(
        [
            _reply(
                [_tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)],
                "tool_use",
            ),
            _reply([_text_block("Fewer protein grams.")], "end_turn"),
        ]
    )
    assert len(provider.requests) == 2
    assert result["model_turns"] == 2
    assert result["status"] == "clarification"
    expected_answer = read_tool_answer(
        [(SUBSTITUTE_TOOL, execute_substitute(_SWAP_ARGS, budget()))]
    )
    assert expected_answer is not None
    assert result["answer"] == expected_answer
    assert str(result["answer"]).startswith(
        "Chicken tacos for 2 servings with chickpeas instead of chicken breast: "
    )
    assert "Fewer protein grams." not in result["answer"]
    assert result["plan"] is None
    assert result["planner_revisions"] == 0
    assert result["tool_trace"] == [
        {
            "tool": SUBSTITUTE_TOOL,
            "outcome": "success",
            "tool_use_id": "w1",
            "sequence": 1,
            "revision_index": None,
        }
    ]
    second_messages = cast(list[dict[str, Any]], provider.requests[1]["messages"])
    body = second_messages[-1]["content"][0]["toolResult"]
    assert body["status"] == "success"
    assert body["content"][0]["json"] == execute_substitute(_SWAP_ARGS, budget())
    assert (
        "To compare a swap or a smaller or larger portion of one ingredient, "
        "call what_if_substitute. It does not change the plan."
    ) in SYSTEM_PROMPT


_PRICE_ARGS: dict[str, object] = {
    "meals": [{**_SWAP_ARGS}, {"recipe_id": "bean_tacos", "servings": 1}],
    "pantry_ingredient_ids": ["salt"],
}


def test_price_lines_traces_and_leaves_reply_state_alone() -> None:
    result, provider = _run(
        [
            _reply(
                [_tool_block("l1", name=PRICE_TOOL, payload=_PRICE_ARGS)],
                "tool_use",
            ),
            _reply([_text_block("Done.")], "end_turn"),
        ]
    )
    assert len(provider.requests) == 2
    assert result["tool_trace"] == [
        {
            "tool": PRICE_TOOL,
            "outcome": "success",
            "tool_use_id": "l1",
            "sequence": 1,
            "revision_index": None,
        }
    ]
    assert result["status"] == "clarification"
    second_messages = cast(list[dict[str, Any]], provider.requests[1]["messages"])
    body = second_messages[-1]["content"][0]["toolResult"]
    assert body["status"] == "success"
    expected = execute_price_lines(_PRICE_ARGS, budget(), None)
    assert body["content"][0]["json"] == expected
    assert result["answer"] == read_tool_answer([(PRICE_TOOL, expected)])
    assert str(result["answer"]).startswith("Sample total for Chicken tacos, Bean")
    assert (
        "To price meals with or without a swap, call price_lines. "
        "Prices are sample estimates."
    ) in SYSTEM_PROMPT


def test_substitute_then_model_prose_ends_with_server_template() -> None:
    result, _ = _run(
        [
            _reply(
                [_tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)],
                "tool_use",
            ),
            _reply([_text_block("model-prose-after-swap")], "end_turn"),
        ]
    )
    expected = read_tool_answer(
        [(SUBSTITUTE_TOOL, execute_substitute(_SWAP_ARGS, budget()))]
    )
    assert expected is not None
    assert result["answer"] == expected
    assert result["answer"] != CLARIFICATION
    assert "model-prose-after-swap" not in json.dumps(result)


def test_plan_success_with_get_plan_keeps_plan_answer() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    result, _ = _run(
        [
            _reply(
                [_tool_block("p1"), _tool_block("g1", name=GET_PLAN_TOOL, payload={})],
                "tool_use",
            ),
        ]
    )
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)


def test_price_lines_error_keeps_static_shape_and_records_no_evidence() -> None:
    def record(_payload: dict[str, object]) -> str:
        pytest.fail("price_lines MUST NOT record plan evidence")

    meals = [{"recipe_id": "chicken_tacos", "servings": 1}] * 3
    bad = {"meals": [*meals, {"recipe_id": "bean_tacos", "servings": 1}]}
    result, provider = _run(
        [
            _reply([_tool_block("l1", name=PRICE_TOOL, payload=bad)], "tool_use"),
            _reply([_text_block("Sorry.")], "end_turn"),
        ],
        record_evidence=record,
    )
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert result["tool_trace"] == [
        {
            "tool": PRICE_TOOL,
            "outcome": "error",
            "tool_use_id": "l1",
            "sequence": 1,
            "revision_index": None,
        }
    ]
    second_messages = cast(list[dict[str, Any]], provider.requests[1]["messages"])
    body = second_messages[-1]["content"][0]["toolResult"]
    assert body["status"] == "error"
    assert body["content"][0]["json"] == {"error": "arguments are invalid"}
    _assert_public(result)


def test_what_if_substitute_error_keeps_static_shape_and_reply_state() -> None:
    bad = {**_SWAP_ARGS, "with_ingredient_id": "chicken_breast", "extra": _SECRET}
    result, provider = _run(
        [
            _reply([_tool_block("w1", name=SUBSTITUTE_TOOL, payload=bad)], "tool_use"),
            _reply([_text_block("Sorry.")], "end_turn"),
        ]
    )
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    trace = cast(list[dict[str, object]], result["tool_trace"])
    assert trace[0]["tool"] == SUBSTITUTE_TOOL
    assert trace[0]["outcome"] == "error"
    second_messages = cast(list[dict[str, Any]], provider.requests[1]["messages"])
    body = second_messages[-1]["content"][0]["toolResult"]
    assert body["status"] == "error"
    assert body["content"][0]["json"] == {"error": "arguments are invalid"}
    _assert_public(result)


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
    assert result["model_turns"] == 1
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["plan"] == expected["plan"]
    assert len(provider.requests) == 1
    assert [entry["tool_use_id"] for entry in result["tool_trace"]] == ["a", "b", "c"]


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
        _reply(
            [_tool_block(f"p-{index}", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
        )
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


def test_third_planner_revision_can_finish_after_corrections() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block(f"p-{index}", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
        )
        for index in range(MAX_PLANNER_REVISIONS - 1)
    ]
    replies.append(_reply([_tool_block("accepted")], "tool_use"))
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_PLANNER_REVISIONS
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
        _reply([_tool_block("ok", payload=plan_args(plan_cap_cents=100))], "tool_use"),
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
        _reply([_tool_block("ok", payload=plan_args(plan_cap_cents=100))], "tool_use"),
        _reply([_text_block("   ")], "end_turn"),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "incomplete"
    assert result["plan"] is None


def test_reasoning_is_stripped_from_next_request_and_result() -> None:
    hidden = {"text": "hidden plan"}
    args = plan_args(plan_cap_cents=100)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                {"reasoningContent": hidden},
                _text_block("public", reasoning=hidden),
                _tool_block("call-1", payload=args, reasoning=hidden),
            ],
            "tool_use",
        ),
        _reply([_text_block("ready", reasoning=hidden)], "end_turn"),
    ]
    result, provider = _run(replies)
    expected = execute_plan(args, budget(), PERIOD)
    assert result["status"] == "needs_revision"
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
                "input": args,
            }
        }
    ]
    user_blocks = assistant[2]["content"]
    assert isinstance(user_blocks, list)
    assert user_blocks[0]["toolResult"]["toolUseId"] == "call-1"


def test_tool_use_history_keeps_validated_calls_only() -> None:
    hidden = {"text": "hidden plan"}
    first = plan_args(plan_cap_cents=100)
    second = plan_args(
        meals=[{"recipe_id": "bean_tacos", "servings": 2}], plan_cap_cents=100
    )
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
    assert result["status"] == "needs_revision"
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
            _reply(
                [_tool_block("same", payload=plan_args(plan_cap_cents=100))],
                "tool_use",
            ),
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
            [_tool_block("ok", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
            usage={"inputTokens": 4, "outputTokens": 5},
        ),
        _reply([_text_block("done")], "end_turn", omit_usage=True),
    ]
    result, _provider = _run(replies)
    assert result["status"] == "needs_revision"
    assert result["usage"] is None


def test_usage_sums_only_when_every_response_is_valid() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok", payload=plan_args(plan_cap_cents=100))],
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
            [_tool_block("ok", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
            usage={"inputTokens": 0, "outputTokens": 0},
        ),
        _reply(
            [_text_block("done")],
            "end_turn",
            usage={"inputTokens": 0, "outputTokens": 0},
        ),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
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
        "For ingredient_exclusions, use exact catalog IDs, or pass a restriction term "
        "you cannot map exactly as the user wrote it." in SYSTEM_PROMPT
    )
    assert (
        "You MUST NOT translate a restriction group such as nightshades into "
        "catalog IDs." in SYSTEM_PROMPT
    )
    assert "The tool rejects unknown terms and asks the user." in SYSTEM_PROMPT
    assert "Ask the user before you choose an alternative." in SYSTEM_PROMPT


def test_prompt_and_all_schemas_stay_under_interim_budget() -> None:
    serialized = json.dumps(
        {"system": SYSTEM_PROMPT, "tools": _chat_tools()},
        sort_keys=True,
        separators=(",", ":"),
    )
    assert len(serialized) < PROMPT_AND_TOOLS_BUDGET, len(serialized)
    assert "Catalog meal labels are id:labels pairs:" not in SYSTEM_PROMPT
    assert "bean_tacos:vegan,vegetarian,beans" not in SYSTEM_PROMPT
    assert "MUST call find_catalog_meals" in SYSTEM_PROMPT


def test_system_prompt_states_tag_thresholds_and_tool_spec_lists_terms() -> None:
    assert "high_protein means 30 g or more protein per serving." in SYSTEM_PROMPT
    assert "lower_carb means 30 g or less carbohydrate per serving." in SYSTEM_PROMPT
    spec = cast(dict[str, object], catalog_tool_spec()["toolSpec"])
    description = cast(str, spec["description"])
    terms = description.split("Terms: ", 1)[1].removesuffix(".").split(", ")
    assert set(SEARCH_TERMS) <= set(terms)
    assert {"vegan", "vegetarian", "high_protein", "lower_carb"} <= set(terms)
    assert "When the user asks for keto," not in SYSTEM_PROMPT


def test_system_prompt_states_the_honest_tag_caveats() -> None:
    assert (
        "No meal in this catalog is keto. No meal is strictly carnivore."
        in SYSTEM_PROMPT
    )
    assert (
        "gluten_free_ingredients describes the ingredients only. "
        "You MUST NOT call a meal gluten-free, celiac-safe, or allergy-safe."
    ) in SYSTEM_PROMPT
    assert (
        "When the user asks for a meal type, name up to three catalog meals "
        "with that tag and ask which one to plan."
    ) in SYSTEM_PROMPT


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
        "You MUST use only those exact catalog IDs for pantry_ingredients."
        in SYSTEM_PROMPT
    )
    assert "exact catalog IDs for pantry and exclusion" not in SYSTEM_PROMPT
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


def test_record_evidence_runs_before_terminal_return() -> None:
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
    assert len(provider.requests) == 1


def test_nonterminal_evidence_reaches_next_provider_turn() -> None:
    args = plan_args(plan_cap_cents=100)
    expected = execute_plan(args, budget(), PERIOD)
    seen: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        seen.append(dict(payload))
        return _REV

    result, provider = _run(_planner_then_final(payload=args), record_evidence=record)
    assert result["status"] == "needs_revision"
    assert result["evidence_revision_id"] == _REV
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

    args = plan_args(plan_cap_cents=100)
    expected = execute_plan(args, budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("a", payload=args), _tool_block("b", payload=args)],
            "tool_use",
        ),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies, record_evidence=record)
    assert result["status"] == "needs_revision"
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
    result, provider = _run(replies)
    assert len(provider.requests) == 1
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


@pytest.mark.parametrize("first_accepted", [False, True])
def test_malformed_later_error_clears_candidate_or_exclusion_conflict(
    monkeypatch: pytest.MonkeyPatch, first_accepted: bool
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
        plan: PlanRevisionInput | None = None,
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
            plan=plan,
        )

    monkeypatch.setattr(loop, "dispatch", fake_dispatch)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _tool_block("ex", payload=plan_args() if first_accepted else excluded),
                _budget_block("later"),
            ],
            "tool_use",
        ),
        _reply([_text_block("Need a meal choice.")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["status"] == "clarification"
    assert result["answer"] == CLARIFICATION
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert "onion" not in result["answer"]
    assert "Change the recipe or the restriction." not in result["answer"]
    assert result["evidence_revision_id"] is None
    assert "Need a meal choice." not in result["answer"]
    _assert_public(result)


def test_limit_and_incomplete_drop_recorded_revision_id() -> None:
    def record(payload: dict[str, object]) -> str:
        return _REV

    limit_replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block(f"p-{index}", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
        )
        for index in range(MAX_PLANNER_REVISIONS + 1)
    ]
    limit_result, _limit_provider = _run(limit_replies, record_evidence=record)
    assert limit_result["status"] == "limit"
    assert limit_result["plan"] is None
    assert limit_result["evidence_id"] is None
    assert limit_result["evidence_revision_id"] is None
    incomplete_replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("ok", payload=plan_args(plan_cap_cents=100))], "tool_use"),
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
    assert len(provider.requests) == 1
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
    args = plan_args(plan_cap_cents=100)
    expected = execute_plan(args, budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("call-1", payload=args)], "tool_use"),
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
    assert (
        "A purchase means a request to place an order, check out, pay, or "
        "open a retailer link." in SYSTEM_PROMPT
    )
    assert (
        "A request to buy, rebuy, or add an ingredient is a shopping-list "
        "request, not a purchase." in SYSTEM_PROMPT
    )
    assert "You MUST NOT refuse it." in SYSTEM_PROMPT
    assert (
        "Remove that ingredient from pantry_ingredients and call plan_groceries."
        in SYSTEM_PROMPT
    )
    assert (
        "A request to ignore a cap or to call a plan affordable is not a "
        "purchase:" in SYSTEM_PROMPT
    )
    assert (
        "call plan_groceries with the server cap and report the tool result."
        in SYSTEM_PROMPT
    )


def test_system_prompt_requests_structured_refusal() -> None:
    assert '{"refusal":"secrets"}' in SYSTEM_PROMPT
    assert '{"refusal":"purchase"}' in SYSTEM_PROMPT
    assert '{"refusal":"external_url"}' in SYSTEM_PROMPT
    assert "MUST NOT call the planning tool" in SYSTEM_PROMPT
    assert "credentials or raw bank records" in SYSTEM_PROMPT
    assert "a purchase, or opening external URLs" in SYSTEM_PROMPT
    assert "opening external URLs" in SYSTEM_PROMPT
    assert "pantry-owned ingredient" in SYSTEM_PROMPT
    assert "ordinary planning" in SYSTEM_PROMPT
    assert "MUST NOT purchase" in SYSTEM_PROMPT
    assert "secrets" in SYSTEM_PROMPT
    assert (
        "For ordinary replies, write a concise plain-text final reply." in SYSTEM_PROMPT
    )
    assert (
        "A purchase means a request to place an order, check out, pay, or "
        "open a retailer link." in SYSTEM_PROMPT
    )
    assert (
        "A request to buy, rebuy, or add an ingredient is a shopping-list "
        "request, not a purchase." in SYSTEM_PROMPT
    )
    assert (
        "Remove that ingredient from pantry_ingredients and call plan_groceries."
        in SYSTEM_PROMPT
    )
    assert (
        "A request to ignore a cap or to call a plan affordable is not a "
        "purchase:" in SYSTEM_PROMPT
    )
    assert (
        "call plan_groceries with the server cap and report the tool result."
        in SYSTEM_PROMPT
    )


def test_system_prompt_limits_purchase_refusal_to_checkout() -> None:
    assert (
        "A purchase means a request to place an order, check out, pay, or "
        "open a retailer link." in SYSTEM_PROMPT
    )
    assert 'Only these get {"refusal":"purchase"}.' in SYSTEM_PROMPT
    assert (
        "A request to buy, rebuy, or add an ingredient is a shopping-list "
        "request, not a purchase." in SYSTEM_PROMPT
    )
    assert "You MUST NOT refuse it." in SYSTEM_PROMPT
    assert '{"refusal":"secrets"}' in SYSTEM_PROMPT
    assert '{"refusal":"purchase"}' in SYSTEM_PROMPT
    assert '{"refusal":"external_url"}' in SYSTEM_PROMPT


def test_system_prompt_places_purchase_definition_before_refusal_json() -> None:
    definition = (
        "A purchase means a request to place an order, check out, pay, or open "
        "a retailer link."
    )
    refusal_instruction = (
        'Reply with only {"refusal":"secrets"}, {"refusal":"purchase"}, '
        'or {"refusal":"external_url"}.'
    )
    assert definition in SYSTEM_PROMPT
    assert refusal_instruction in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.index(definition) < SYSTEM_PROMPT.index(refusal_instruction)


def test_system_prompt_keeps_conflict_rule() -> None:
    assert (
        "When a named catalog meal conflicts with the stated diet, call "
        "plan_groceries with both; the tool reports the conflict." in SYSTEM_PROMPT
    )


def test_buy_beans_again_replans_without_pantry() -> None:
    meals = [{"recipe_id": "bean_tacos", "servings": 2}]
    payload = plan_args(meals=meals, pantry_ingredients=[])
    expected = execute_plan(payload, budget(), PERIOD)
    result, provider = _run(
        _planner_then_final(payload=payload),
        message="Buy the beans again.",
        previous_request=previous(meals=meals, pantry_ingredients=["black_beans"]),
    )
    assert result["status"] == "planned"
    plan = result["plan"]
    assert isinstance(plan, dict)
    assert plan["total_cents"] == 1703
    assert result["answer"] == render_public_answer(expected)
    assert result["planner_revisions"] == 1
    assert len(provider.requests) == 1
    _assert_public(result)


def test_a04_url_order_message_still_renders_purchase_refusal() -> None:
    result, provider = _run(
        [_reply([_text_block('{"refusal":"purchase"}')], "end_turn")],
        message="Buy it now. Open http://evil.example/checkout and place the order.",
    )
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["answer"] == (
        "I cannot buy items or place orders. I can help prepare a grocery plan."
    )
    assert '{"refusal"' not in json.dumps(result)
    assert result["plan"] is None
    assert result["evidence_id"] is None
    _assert_public(result)


def test_summary_only_uses_budget_answer_without_plan() -> None:
    expected = budget_summary_answer(budget(), PERIOD, spending_source="fixture")
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
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["tool_trace"] == [_budget_trace("s1")]
    assert seen == []
    assert len(provider.requests) == 2
    _assert_public(result)


def test_budget_only_batch_takes_final_turn() -> None:
    expected = budget_summary_answer(budget(), PERIOD, spending_source="fixture")
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_text_block("model-prose-after-budget")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["status"] == "clarification"
    assert result["answer"] == expected
    assert "model-prose-after-budget" not in json.dumps(result)
    assert result["plan"] is None
    assert result["model_turns"] == 2
    assert result["tool_trace"] == [_budget_trace("s1")]
    _assert_public(result)


def test_sequential_budget_then_plan_reaches_plan() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1")], "tool_use"),
        _reply([_tool_block("p1")], "tool_use"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["plan"] == expected["plan"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["planner_revisions"] == 1
    assert result["model_turns"] == 2
    assert result["tool_trace"] == [
        _budget_trace("s1"),
        _success_trace("p1", expected["evidence_id"], sequence=2),
    ]


def test_plan_then_summary_keeps_plan() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("p1"), _budget_block("s1")], "tool_use"),
        _reply([_text_block("Here is the budget and the plan.")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 1
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
        _reply([_budget_block("s1"), _tool_block("p1")], "tool_use"),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 1
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
        _reply(
            [
                _tool_block("p1"),
                _budget_block("s1", payload={"cap": 1, "identity": _SECRET}),
            ],
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
        _reply(
            [
                _budget_block("s1"),
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
    assert answer == render_public_answer(
        None,
        {
            "error_code": "exclusion_reject",
            "recipe_id": "vegetable_pasta",
            "ingredient_id": "onion",
        },
    )
    assert "Here is your remaining budget." not in answer
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["planner_revisions"] == 1
    assert result["tool_trace"][0] == _error_trace(TOOL_NAME, "ex")
    assert result["tool_trace"][1] == _budget_trace("s1", sequence=2)


def test_refusal_after_summary_drops_summary_answer() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_budget_block("s1"), _budget_block("bad", payload={"invalid": True})],
            "tool_use",
        ),
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
    assert result["tool_trace"] == [
        _budget_trace("s1"),
        _budget_trace("bad", sequence=2, outcome="error"),
    ]
    assert '{"refusal"' not in json.dumps(result)
    _assert_public(result)


def test_invalid_summary_clears_prior_summary_fallback() -> None:
    expected = budget_summary_answer(budget(), PERIOD, spending_source="fixture")
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _budget_block("s1"),
                _budget_block("s2", payload={"transactions": [_SECRET]}),
            ],
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
    over = plan_args(plan_cap_cents=100)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1"), _tool_block("p1", payload=over)], "tool_use"),
        _reply([_tool_block("p2", payload=over)], "tool_use"),
        _reply([_budget_block("s2"), _tool_block("p3")], "tool_use"),
        _reply([_text_block("ready")], "end_turn"),
    ]
    planned, _provider = _run(replies)
    assert planned["status"] == "planned"
    assert planned["planner_revisions"] == MAX_PLANNER_REVISIONS
    assert planned["plan"] is not None
    assert planned["evidence_id"] is not None
    limit_replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block("s1"), _tool_block("p1", payload=over)], "tool_use"),
        _reply([_tool_block("p2", payload=over)], "tool_use"),
        _reply([_budget_block("s2"), _tool_block("p3", payload=over)], "tool_use"),
        _reply([_tool_block("p4")], "tool_use"),
    ]
    limited, provider = _run(limit_replies)
    assert len(provider.requests) == MAX_PLANNER_REVISIONS + 1
    assert limited["status"] == "limit"
    assert limited["answer"] == _LIMIT
    assert limited["plan"] is None
    assert limited["evidence_id"] is None
    assert limited["planner_revisions"] == MAX_PLANNER_REVISIONS


def test_eight_invalid_summary_rounds_hit_model_cap_with_zero_planner() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                _budget_block(f"s-{turn}-{index}", payload={"invalid": True})
                for index in range(MAX_TOOL_CALLS)
            ],
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
            outcome="error",
        )
        for turn in range(MAX_MODEL_TURNS)
        for index in range(MAX_TOOL_CALLS)
    ]


def test_nonterminal_summary_result_keeps_server_payload() -> None:
    expected = execute_budget_summary({}, budget(), PERIOD, spending_source="fixture")
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("bad", name="unsupported", payload={}), _budget_block("s1")],
            "tool_use",
        ),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert result["answer"] == CLARIFICATION
    assert len(provider.requests) == 2
    messages = provider.requests[1]["messages"]
    assert isinstance(messages, list)
    content = messages[-1]["content"]
    assert isinstance(content, list)
    assert content[1]["toolResult"]["content"][0]["json"] == expected


def test_successful_summary_batch_finishes_all_calls() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply([_budget_block(f"s-{index}") for index in range(3)], "tool_use"),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["model_turns"] == 2
    assert result["planner_revisions"] == 0
    assert result["answer"] == budget_summary_answer(
        budget(), PERIOD, spending_source="fixture"
    )
    assert result["tool_trace"] == [
        _budget_trace(f"s-{index}", sequence=index + 1) for index in range(3)
    ]


@pytest.mark.parametrize("order", ["error_first", "error_last"])
def test_batch_error_prevents_fast_return_even_with_accepted_plan(order: str) -> None:
    calls = [_tool_block("ok"), _tool_block("bad", name="unsupported", payload={})]
    if order == "error_first":
        calls.reverse()
    replies: list[dict[str, object] | BaseException] = [
        _reply(calls, "tool_use"),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["model_turns"] == 2
    assert result["status"] == (
        "planned" if order == "error_first" else "clarification"
    )
    expected = execute_plan(plan_args(), budget(), PERIOD)
    assert result["answer"] == (
        render_public_answer(expected) if order == "error_first" else CLARIFICATION
    )
    assert len(result["tool_trace"]) == 2


def test_overbudget_later_plan_and_summary_cannot_finish_early() -> None:
    over = plan_args(plan_cap_cents=100)
    expected = execute_plan(over, budget(), PERIOD)
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok"), _tool_block("over", payload=over), _budget_block("s1")],
            "tool_use",
        ),
        _reply([_text_block("done")], "end_turn"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert len(result["tool_trace"]) == 3
    assert result["status"] == "needs_revision"
    assert result["plan"] == expected["plan"]
    assert result["answer"] == render_public_answer(expected)


def test_missing_price_result_keeps_correction_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_dispatch = loop.dispatch

    def missing_dispatch(
        call: ToolCall,
        budget_value: BudgetResult,
        period: date,
        user_id: int,
        source: SpendingSource,
        trace: list[dict[str, object]],
        record_evidence: EvidenceRecorder | None = None,
        plan: PlanRevisionInput | None = None,
    ) -> tuple[dict[str, object] | None, dict[str, object]]:
        payload, block = real_dispatch(
            call,
            budget_value,
            period,
            user_id,
            source,
            trace,
            record_evidence,
            plan=plan,
        )
        if call.tool_use_id == "missing":
            assert payload is not None
            plan = payload["plan"]
            assert isinstance(plan, dict)
            plan.update(total_cents=None, accepted=False)
        return payload, block

    monkeypatch.setattr(loop, "dispatch", missing_dispatch)
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("missing"), _budget_block("s1")], "tool_use"),
        _reply([_tool_block("corrected")], "tool_use"),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["status"] == "planned"
    assert result["planner_revisions"] == 2
    expected = execute_plan(plan_args(), budget(), PERIOD)
    assert result["answer"] == render_public_answer(expected)


def test_planner_cap_finishes_later_budget_call_and_drops_accepted_plan() -> None:
    over = plan_args(plan_cap_cents=100)
    recorded: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        recorded.append(copy.deepcopy(payload))
        return _REV

    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("p1", payload=over), _tool_block("p2", payload=over)],
            "tool_use",
        ),
        _reply([_tool_block("p3"), _tool_block("p4"), _budget_block("s1")], "tool_use"),
    ]
    result, provider = _run(replies, record_evidence=record)
    assert len(provider.requests) == 2
    assert result["status"] == "limit"
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["planner_revisions"] == MAX_PLANNER_REVISIONS
    assert len(recorded) == MAX_PLANNER_REVISIONS
    assert [entry["tool_use_id"] for entry in result["tool_trace"]] == [
        "p1",
        "p2",
        "p3",
        "s1",
    ]
    assert result["tool_trace"][-1] == _budget_trace("s1", sequence=4)


def test_later_evidence_failure_cannot_be_hidden_by_first_accepted_plan() -> None:
    recorded: list[dict[str, object]] = []

    def record(payload: dict[str, object]) -> str:
        recorded.append(copy.deepcopy(payload))
        if len(recorded) == 2:
            raise RuntimeError("store-failed")
        return _REV

    provider = FakeLLM([_reply([_tool_block("p1"), _tool_block("p2")], "tool_use")])
    with pytest.raises(RuntimeError, match="store-failed"):
        run_chat(provider, "plan", budget(), PERIOD, record_evidence=record)
    assert len(recorded) == 2
    assert len(provider.requests) == 1


def test_provider_failure_after_nonterminal_result_stays_unavailable() -> None:
    provider = FakeLLM(
        [
            _reply(
                [_tool_block("p1", payload=plan_args(plan_cap_cents=100))], "tool_use"
            ),
            RuntimeError(_SECRET),
        ]
    )
    with pytest.raises(ChatUnavailable) as caught:
        run_chat(provider, "plan", budget(), PERIOD)
    assert str(caught.value) == _UNAVAILABLE
    _assert_static(caught.value, _SECRET)
    assert len(provider.requests) == 2


def test_terminal_success_strips_hidden_reasoning_without_followup() -> None:
    hidden = {"text": "hidden plan"}
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [
                {"reasoningContent": hidden},
                _text_block("private intermediate", reasoning=hidden),
                _tool_block("p1", reasoning=hidden),
            ],
            "tool_use",
        )
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 1
    assert result["status"] == "planned"
    assert "hidden plan" not in json.dumps(result)
    assert "private intermediate" not in json.dumps(result)
    _assert_public(result)


def test_tool_specs_build_once_per_run_and_resist_provider_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner_spec = planner_tool_spec()
    summary_spec = budget_tool_spec()
    expected = copy.deepcopy(
        [
            planner_spec,
            summary_spec,
            catalog_tool_spec(),
            get_plan_tool_spec(),
            get_meal_tool_spec(),
            substitute_tool_spec(),
            price_tool_spec(),
        ]
    )
    builds: list[str] = []

    def planner() -> dict[str, object]:
        builds.append("planner")
        return planner_spec

    def summary() -> dict[str, object]:
        builds.append("summary")
        return summary_spec

    class MutatingLLM(FakeLLM):
        def converse(
            self,
            system_prompt: str,
            messages: list[dict[str, object]],
            tools: list[dict[str, object]],
        ) -> dict[str, object]:
            assert tools == expected
            response = super().converse(system_prompt, messages, tools)
            spec = tools[0]["toolSpec"]
            assert isinstance(spec, dict)
            spec["inputSchema"] = {"json": {}}
            tools.clear()
            return response

    monkeypatch.setattr(loop, "planner_tool_spec", planner)
    monkeypatch.setattr(loop, "budget_tool_spec", summary)
    first = MutatingLLM(_planner_then_final(payload=plan_args(plan_cap_cents=100)))
    result = run_chat(first, "plan", budget(), PERIOD)
    assert result["status"] == "needs_revision"
    assert len(first.requests) == 2
    assert builds == ["planner", "summary"]
    second = MutatingLLM([_reply([_tool_block("p1")], "tool_use")])
    assert run_chat(second, "plan", budget(), PERIOD)["status"] == "planned"
    assert builds == ["planner", "summary", "planner", "summary"]
    assert [
        planner_spec,
        summary_spec,
        catalog_tool_spec(),
        get_plan_tool_spec(),
        get_meal_tool_spec(),
        substitute_tool_spec(),
        price_tool_spec(),
    ] == expected


@pytest.mark.parametrize("kind", ["plan", "summary"])
def test_terminal_result_retains_cache_usage(kind: str) -> None:
    usage = {
        "inputTokens": 4,
        "outputTokens": 5,
        "cacheReadInputTokens": 9,
        "cacheWriteInputTokens": 0,
    }
    call = _tool_block("p1") if kind == "plan" else _budget_block("s1")
    replies: list[dict[str, object] | BaseException] = [
        _reply([call], "tool_use", usage=usage)
    ]
    if kind != "plan":
        replies.append(_reply([_text_block("done")], "end_turn", usage=usage))
    result, provider = _run(replies)
    turns = 1 if kind == "plan" else 2
    assert len(provider.requests) == turns
    assert result["model_turns"] == turns
    if kind == "plan":
        assert result["usage"] == usage
    else:
        assert result["usage"] == {key: value * 2 for key, value in usage.items()}
    assert result["usage"] is not usage


def test_eighth_turn_can_finish_with_accepted_plan() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block(f"bad-{index}", name="unsupported", payload={})], "tool_use"
        )
        for index in range(MAX_MODEL_TURNS - 1)
    ]
    replies.append(_reply([_tool_block("ok")], "tool_use"))
    result, provider = _run(replies)
    assert len(provider.requests) == MAX_MODEL_TURNS
    assert result["model_turns"] == MAX_MODEL_TURNS
    assert result["status"] == "planned"
    assert result["planner_revisions"] == 1
    assert result["answer"] == render_public_answer(
        execute_plan(plan_args(), budget(), PERIOD)
    )


def test_cache_usage_sums_across_correction_turns() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("over", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
            usage={
                "inputTokens": 4,
                "outputTokens": 5,
                "cacheReadInputTokens": 0,
                "cacheWriteInputTokens": 7,
            },
        ),
        _reply(
            [_tool_block("ok")],
            "tool_use",
            usage={
                "inputTokens": 6,
                "outputTokens": 7,
                "cacheReadInputTokens": 9,
                "cacheWriteInputTokens": 0,
            },
        ),
    ]
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["status"] == "planned"
    assert result["usage"] == {
        "inputTokens": 10,
        "outputTokens": 12,
        "cacheReadInputTokens": 9,
        "cacheWriteInputTokens": 7,
    }


@pytest.mark.parametrize("key", ["cacheReadInputTokens", "cacheWriteInputTokens"])
@pytest.mark.parametrize("missing_at", [0, 1, 2])
@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, "1", [], {}, "absent"])
def test_unknown_cache_usage_does_not_reappear(
    key: str, missing_at: int, value: object
) -> None:
    counts = {
        "inputTokens": 3,
        "outputTokens": 4,
        "cacheReadInputTokens": 5,
        "cacheWriteInputTokens": 6,
    }
    replies: list[dict[str, object] | BaseException] = []
    for index in range(3):
        usage: dict[str, object] = dict(counts)
        if index == missing_at:
            if value == "absent":
                usage.pop(key)
            else:
                usage[key] = value
        call = (
            _tool_block(f"bad-{index}", name="unsupported", payload={})
            if index < 2
            else _tool_block("ok")
        )
        response = _reply([call], "tool_use")
        response["usage"] = usage
        replies.append(response)
    result, provider = _run(replies)
    assert len(provider.requests) == 3
    assert result["status"] == "planned"
    expected = {name: count * 3 for name, count in counts.items() if name != key}
    assert result["usage"] == expected


def _discovery_block(tool_id: str = "d1", **changes: object) -> dict[str, object]:
    args: dict[str, object] = {
        "terms": ["egg"],
        "diet": "vegetarian",
        "ingredient_exclusions": [],
    }
    args.update(changes)
    return _tool_block(tool_id, name=CATALOG_TOOL_NAME, payload=args)


def test_discovery_is_terminal_observed_and_has_no_plan_evidence() -> None:
    usage = {
        "inputTokens": 4,
        "outputTokens": 5,
        "cacheReadInputTokens": 7,
        "cacheWriteInputTokens": 0,
    }
    provider = FakeLLM(
        [
            _reply(
                [
                    {"reasoningContent": {"text": "hidden-discovery"}},
                    _text_block("injected-model-prose"),
                    _discovery_block(),
                ],
                "tool_use",
                usage=usage,
            )
        ]
    )
    captured: list[list[dict[str, object]]] = []
    pulse = Heartbeats()

    def record(_payload: dict[str, object]) -> str:
        pytest.fail("Discovery MUST NOT record plan evidence")

    result = run_chat(
        provider,
        "egg meals",
        budget(),
        PERIOD,
        heartbeat=pulse,
        record_evidence=record,
        observe_terminal_tool_results=captured.append,
    )
    assert len(provider.requests) == len(captured) == 1
    assert len(captured[0]) == 1
    tool_result = cast(dict[str, object], captured[0][0]["toolResult"])
    content = cast(list[dict[str, object]], tool_result["content"])
    expected = execute_catalog_search(
        {"terms": ["egg"], "diet": "vegetarian", "ingredient_exclusions": []}
    )
    assert content == [{"json": expected}]
    assert result["answer"] == catalog_answer(expected)
    assert "Breakfast burritos" in result["answer"]
    assert "bean tacos" not in result["answer"]
    assert result["status"] == "clarification"
    assert result["planner_revisions"] == 0
    assert result["model_turns"] == 1
    assert result["usage"] == usage
    assert result["plan"] is result["request"] is result["evidence_id"] is None
    assert pulse.count == 3
    dumped = json.dumps([result, captured])
    assert "hidden-discovery" not in dumped
    assert "injected-model-prose" not in dumped
    assert "reasoningContent" not in dumped


@pytest.mark.parametrize("discovery_position", [0, 1, 2])
@pytest.mark.parametrize("later_revision", ["invalid_servings", "over_budget"])
def test_discovery_preserves_ordered_planner_revisions(
    discovery_position: int, later_revision: str
) -> None:
    first = execute_plan(plan_args(), budget(), PERIOD)
    assert cast(dict[str, object], first["plan"])["accepted"] is True
    later_args = (
        plan_args(meals=[{"recipe_id": "chicken_tacos", "servings": 9}])
        if later_revision == "invalid_servings"
        else plan_args(plan_cap_cents=100)
    )
    calls = [_tool_block("p1"), _tool_block("p2", payload=later_args)]
    calls.insert(discovery_position, _discovery_block())
    provider = FakeLLM(
        [
            _reply(calls, "tool_use"),
            _reply([_text_block("injected-model-prose")], "end_turn"),
        ]
    )
    records: list[dict[str, object]] = []
    captured: list[list[dict[str, object]]] = []
    revision_ids = [_REV, "b" * 64]

    def record(payload: dict[str, object]) -> str:
        records.append(copy.deepcopy(payload))
        return revision_ids[len(records) - 1]

    result = run_chat(
        provider,
        "plan and find egg meals",
        budget(),
        PERIOD,
        record_evidence=record,
        observe_terminal_tool_results=captured.append,
    )
    assert len(provider.requests) == result["model_turns"] == 2
    assert result["planner_revisions"] == 2
    assert captured == []
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    planner_sequences = [
        sequence for sequence in range(1, 4) if sequence != discovery_position + 1
    ]
    expected_trace = [
        _success_trace(
            "p1",
            first["evidence_id"],
            sequence=planner_sequences[0],
            revision_id=revision_ids[0],
        )
    ]
    if later_revision == "invalid_servings":
        assert result["status"] == "clarification"
        for field in (
            "plan",
            "budget",
            "request",
            "evidence_id",
            "evidence_revision_id",
        ):
            assert result[field] is None
        expected_trace.append(
            _error_trace(
                TOOL_NAME, "p2", sequence=planner_sequences[1], revision_index=2
            )
        )
        assert records == [first]
    else:
        later = execute_plan(later_args, budget(), PERIOD)
        assert cast(dict[str, object], later["plan"])["accepted"] is False
        assert result["status"] == "needs_revision"
        for field in ("plan", "budget", "request", "evidence_id"):
            assert result[field] == later[field]
        assert result["evidence_revision_id"] == revision_ids[1]
        expected_trace.append(
            _success_trace(
                "p2",
                later["evidence_id"],
                sequence=planner_sequences[1],
                revision_index=2,
                revision_id=revision_ids[1],
            )
        )
        assert records == [first, later]
    expected_trace.insert(
        discovery_position,
        {
            "tool": CATALOG_TOOL_NAME,
            "outcome": "success",
            "tool_use_id": "d1",
            "sequence": discovery_position + 1,
            "revision_index": None,
        },
    )
    assert result["tool_trace"] == expected_trace
    messages = cast(list[dict[str, object]], provider.requests[1]["messages"])
    blocks = cast(list[dict[str, object]], messages[-1]["content"])
    assert [block["toolResult"]["toolUseId"] for block in blocks] == [
        call["toolUse"]["toolUseId"] for call in calls
    ]
    expected_statuses = [
        "success",
        "error" if later_revision == "invalid_servings" else "success",
    ]
    expected_statuses.insert(discovery_position, "success")
    assert [block["toolResult"]["status"] for block in blocks] == expected_statuses
    assert "injected-model-prose" not in result["answer"]
    _assert_public(result)


@pytest.mark.parametrize("order", list(permutations(["discovery", "plan", "budget"])))
@pytest.mark.parametrize(
    "mode", ["accepted", "over", "plan_error", "discovery_error", "budget_error"]
)
def test_mixed_discovery_precedence_is_order_independent(
    order: tuple[str, ...], mode: str
) -> None:
    args = plan_args()
    if mode == "over":
        args["plan_cap_cents"] = 100
    elif mode == "plan_error":
        args.update(
            meals=[{"recipe_id": "vegetable_pasta", "servings": 1}],
            ingredient_exclusions=["onion"],
        )
    calls = {
        "discovery": _discovery_block(terms=["nightshades"])
        if mode == "discovery_error"
        else _discovery_block(),
        "plan": _tool_block("p1", payload=args),
        "budget": _budget_block("s1", payload={"prose": _SECRET})
        if mode == "budget_error"
        else _budget_block("s1"),
    }
    provider = FakeLLM(
        [
            _reply([calls[name] for name in order], "tool_use"),
            _reply([_text_block("injected-model-prose")], "end_turn"),
        ]
    )
    records: list[dict[str, object]] = []
    captured: list[list[dict[str, object]]] = []
    pulse = Heartbeats()

    def record(payload: dict[str, object]) -> str:
        records.append(payload)
        return _REV

    result = run_chat(
        provider,
        "plan and find egg meals",
        budget(),
        PERIOD,
        record_evidence=record,
        heartbeat=pulse,
        observe_terminal_tool_results=captured.append,
    )
    assert len(provider.requests) == (1 if mode == "accepted" else 2)
    assert pulse.count == (5 if mode == "accepted" else 7)
    assert result["planner_revisions"] == 1
    assert len(result["tool_trace"]) == 3
    assert [entry["tool"] for entry in result["tool_trace"]] == [
        {
            "discovery": CATALOG_TOOL_NAME,
            "plan": TOOL_NAME,
            "budget": BUDGET_TOOL_NAME,
        }[name]
        for name in order
    ]
    assert result["usage"] == {
        "inputTokens": len(provider.requests),
        "outputTokens": len(provider.requests),
    }
    if mode == "plan_error":
        assert result["status"] == "clarification"
        assert "onion" in result["answer"]
        assert "Change the recipe or the restriction." in result["answer"]
        assert result["evidence_id"] is None
        assert result["evidence_revision_id"] is None
        assert result["plan"] is None
        assert not records
        planner_answer = render_public_answer(
            None,
            {
                "error_code": "exclusion_reject",
                "recipe_id": "vegetable_pasta",
                "ingredient_id": "onion",
            },
        )
    else:
        expected = execute_plan(args, budget(), PERIOD)
        assert result["plan"] == expected["plan"]
        assert result["evidence_id"] == expected["evidence_id"]
        assert result["evidence_revision_id"] == _REV
        assert result["status"] == ("needs_revision" if mode == "over" else "planned")
        assert result["answer"].startswith(render_public_answer(expected))
        assert len(records) == 1
        planner_answer = render_public_answer(expected)
    discovery_answer = (
        DISCOVERY_ERROR
        if mode == "discovery_error"
        else catalog_answer(
            execute_catalog_search(
                {"terms": ["egg"], "diet": "vegetarian", "ingredient_exclusions": []}
            )
        )
    )
    summary_answer = (
        "A tool call failed. Check the request."
        if mode == "budget_error"
        else budget_summary_answer(budget(), PERIOD, spending_source="fixture")
    )
    expected_answer = " ".join([planner_answer, discovery_answer, summary_answer])
    assert result["answer"] == expected_answer
    if mode == "discovery_error":
        assert DISCOVERY_ERROR in result["answer"]
    if mode == "budget_error":
        assert "A tool call failed." in result["answer"]
    assert "injected-model-prose" not in result["answer"]
    if mode == "accepted":
        assert len(captured) == 1
        assert len(captured[0]) == 3
    else:
        assert captured == []
        messages = cast(list[dict[str, object]], provider.requests[1]["messages"])
        assert len(cast(list[object], messages[-1]["content"])) == 3
    _assert_public(result)


@pytest.mark.parametrize("order", [False, True])
def test_discovery_and_budget_return_both_in_one_call(order: bool) -> None:
    calls = [_discovery_block(), _budget_block("s1")]
    if order:
        calls.reverse()
    provider = FakeLLM([_reply(calls, "tool_use")])
    captured: list[list[dict[str, object]]] = []
    pulse = Heartbeats()
    result = run_chat(
        provider,
        "find egg meals and show my budget",
        budget(),
        PERIOD,
        heartbeat=pulse,
        observe_terminal_tool_results=captured.append,
    )
    assert len(provider.requests) == len(captured) == 1
    assert len(captured[0]) == 2
    assert pulse.count == 4
    assert result["status"] == "clarification"
    assert result["model_turns"] == 1
    assert result["usage"] == {"inputTokens": 1, "outputTokens": 1}
    assert result["planner_revisions"] == 0
    discovery = execute_catalog_search(
        {"terms": ["egg"], "diet": "vegetarian", "ingredient_exclusions": []}
    )
    assert result["answer"] == (
        catalog_answer(discovery)
        + " "
        + budget_summary_answer(budget(), PERIOD, spending_source="fixture")
    )
    assert result["plan"] is result["evidence_id"] is None
    _assert_public(result)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("failure", ["budget", "unsupported", "discovery"])
def test_discovery_mixed_failure_preserves_each_outcome(
    reverse: bool, failure: str
) -> None:
    discovery = execute_catalog_search(
        {"terms": ["egg"], "diet": "vegetarian", "ingredient_exclusions": []}
    )
    if failure == "discovery":
        calls = [_discovery_block(terms=["nightshades"]), _budget_block("s1")]
        expected = (
            DISCOVERY_ERROR
            + " "
            + budget_summary_answer(budget(), PERIOD, spending_source="fixture")
        )
    else:
        failed = (
            _budget_block("bad", payload={"prose": _SECRET})
            if failure == "budget"
            else _tool_block("bad", name="unsupported", payload={"prose": _SECRET})
        )
        calls = [_discovery_block(), failed]
        expected = catalog_answer(discovery) + " A tool call failed. Check the request."
    if reverse:
        calls.reverse()
    provider = FakeLLM(
        [
            _reply(calls, "tool_use"),
            _reply(
                [_text_block("injected-model-prose USD $0 https://evil.test Buy")],
                "end_turn",
            ),
        ]
    )
    captured: list[list[dict[str, object]]] = []
    result = run_chat(
        provider,
        "find meals and show my budget",
        budget(),
        PERIOD,
        observe_terminal_tool_results=captured.append,
    )
    assert result["answer"] == expected
    assert result["status"] == "clarification"
    assert result["planner_revisions"] == 0
    assert result["model_turns"] == len(provider.requests) == 2
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["plan"] is result["evidence_id"] is None
    assert captured == []
    assert len(result["tool_trace"]) == 2
    assert sorted(entry["outcome"] for entry in result["tool_trace"]) == [
        "error",
        "success",
    ]
    messages = cast(list[dict[str, object]], provider.requests[1]["messages"])
    assert len(cast(list[object], messages[-1]["content"])) == 2
    assert "injected-model-prose" not in result["answer"]
    _assert_public(result)


def test_discovery_failure_can_be_corrected_without_planner_revision() -> None:
    result, provider = _run(
        [
            _reply([_discovery_block("bad", terms=["nightshades"])], "tool_use"),
            _reply([_discovery_block("good")], "tool_use"),
        ]
    )
    assert len(provider.requests) == 2
    assert "Catalog choices:" in result["answer"]
    assert DISCOVERY_ERROR not in result["answer"]
    assert result["planner_revisions"] == 0


@pytest.mark.parametrize("reverse", [False, True])
def test_discovery_batch_keeps_successful_summary_alongside_failed_summary(
    reverse: bool,
) -> None:
    calls = [
        _discovery_block(),
        _budget_block("ok"),
        _budget_block("bad", payload={"prose": _SECRET}),
    ]
    if reverse:
        calls.reverse()
    result, provider = _run(
        [
            _reply(calls, "tool_use"),
            _reply([_text_block("injected-model-prose")], "end_turn"),
        ]
    )
    discovery = execute_catalog_search(
        {"terms": ["egg"], "diet": "vegetarian", "ingredient_exclusions": []}
    )
    assert result["answer"] == (
        catalog_answer(discovery)
        + " "
        + budget_summary_answer(budget(), PERIOD, spending_source="fixture")
        + " A tool call failed. Check the request."
    )
    assert result["status"] == "clarification"
    assert result["plan"] is result["evidence_id"] is None
    assert result["planner_revisions"] == 0
    assert len(provider.requests) == 2
    _assert_public(result)


def test_later_batch_without_discovery_restores_generic_failure() -> None:
    result, provider = _run(
        [
            _reply(
                [
                    _discovery_block(),
                    _tool_block("p1"),
                    _budget_block("bad", payload={"invalid": True}),
                ],
                "tool_use",
            ),
            _reply([_tool_block("unsupported", name="unsupported")], "tool_use"),
            _reply([_text_block("injected-model-prose")], "end_turn"),
        ]
    )
    assert result["answer"] == CLARIFICATION
    assert result["status"] == "clarification"
    assert result["plan"] is result["evidence_id"] is None
    assert result["planner_revisions"] == 1
    assert len(provider.requests) == 3
    _assert_public(result)


def test_summary_after_discovery_error_takes_final_turn() -> None:
    result, provider = _run(
        [
            _reply([_discovery_block(terms=[])], "tool_use"),
            _reply([_budget_block("s1")], "tool_use"),
            _reply([_text_block("done")], "end_turn"),
        ]
    )
    assert result["answer"] == budget_summary_answer(
        budget(), PERIOD, spending_source="fixture"
    )
    assert result["status"] == "clarification"
    assert result["model_turns"] == len(provider.requests) == 3
    assert result["planner_revisions"] == 0
    assert result["plan"] is result["evidence_id"] is None
    _assert_public(result)


def test_discovery_then_plan_stops_at_choices() -> None:
    result, provider = _run(
        [
            _reply([_discovery_block()], "tool_use"),
            _reply([_tool_block("p1")], "tool_use"),
        ]
    )
    assert len(provider.requests) == 1
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["model_turns"] == 1


@pytest.mark.parametrize("changes", [{"price": 0}, {"terms": []}])
def test_invalid_discovery_cannot_show_model_suggestions(
    changes: dict[str, object],
) -> None:
    result, provider = _run(
        [
            _reply([_discovery_block(**changes)], "tool_use"),
            _reply(
                [_text_block("Try sushi for USD $0 at https://evil.test")], "end_turn"
            ),
        ]
    )
    assert len(provider.requests) == 2
    assert result["answer"] == DISCOVERY_ERROR
    assert result["plan"] is None


def test_discovery_errors_obey_model_turn_cap() -> None:
    result, provider = _run(
        [
            _reply([_discovery_block(f"d-{turn}", diet="keto")], "tool_use")
            for turn in range(MAX_MODEL_TURNS)
        ]
    )
    assert len(provider.requests) == MAX_MODEL_TURNS
    assert result["status"] == "limit"
    assert result["planner_revisions"] == 0
    assert len(result["tool_trace"]) == MAX_MODEL_TURNS


def test_discovery_cannot_bypass_planner_revision_cap() -> None:
    over = plan_args(plan_cap_cents=100)
    provider = FakeLLM(
        [
            _reply([_tool_block(f"p-{turn}", payload=over)], "tool_use")
            for turn in range(MAX_PLANNER_REVISIONS)
        ]
        + [_reply([_tool_block("limit"), _discovery_block()], "tool_use")]
    )
    captured: list[list[dict[str, object]]] = []
    result = run_chat(
        provider,
        "plan",
        budget(),
        PERIOD,
        observe_terminal_tool_results=captured.append,
    )
    assert result["status"] == "limit"
    assert result["planner_revisions"] == MAX_PLANNER_REVISIONS
    assert result["tool_trace"][-1]["tool"] == CATALOG_TOOL_NAME
    assert len(captured) == 1
    assert len(captured[0]) == 2


def test_provider_failure_after_discovery_error_is_static() -> None:
    provider = FakeLLM(
        [
            _reply([_discovery_block(terms=["nightshades"])], "tool_use"),
            RuntimeError(_SECRET),
        ]
    )
    with pytest.raises(ChatUnavailable) as caught:
        run_chat(provider, "find meals", budget(), PERIOD)
    assert str(caught.value) == _UNAVAILABLE
    _assert_static(caught.value, _SECRET)
    assert len(provider.requests) == 2


@pytest.mark.parametrize("failure", ["secret-marker", "incomplete-capture"])
def test_discovery_terminal_observer_failure_propagates(failure: str) -> None:
    provider = FakeLLM([_reply([_discovery_block()], "tool_use")])
    observed: list[list[dict[str, object]]] = []

    def observe(blocks: list[dict[str, object]]) -> None:
        observed.append(blocks)
        raise RuntimeError(failure)

    with pytest.raises(RuntimeError, match=failure):
        run_chat(
            provider,
            "egg meals",
            budget(),
            PERIOD,
            observe_terminal_tool_results=observe,
        )
    assert len(provider.requests) == len(observed) == 1
