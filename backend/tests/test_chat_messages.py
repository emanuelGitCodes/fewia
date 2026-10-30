from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from app.agent.chat_messages import (
    MAX_TOOL_CALLS,
    MAX_TOOL_FIELD_LEN,
    ChatProtocolError,
    ToolCall,
    build_chat_result,
    parse_assistant_message,
    parse_provider_response,
    tool_result_block,
)

_SECRET = "do-not-echo-raw-input"


def _assistant(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _text_block(text: str) -> dict[str, Any]:
    return {"text": text}


def _tool_block(
    tool_id: str,
    name: str = "plan_groceries",
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "toolUse": {
            "toolUseId": tool_id,
            "name": name,
            "input": {} if payload is None else payload,
        }
    }


def _response(message: dict[str, Any], stop: object) -> dict[str, Any]:
    return {"output": {"message": message}, "stopReason": stop}


def _candidate() -> dict[str, object]:
    return {
        "plan": {"meals": 1},
        "budget": {"cents": 100},
        "request": {"servings": 2},
        "meal_nutrition": {"total": {"energy_kcal": 10}},
        "evidence_id": "ev-1",
        "evidence_revision_id": "ab" * 32,
    }


def test_parse_assistant_message_valid_text() -> None:
    message = _assistant([_text_block("hello")])
    seen: set[str] = set()
    text, calls, sanitized = parse_assistant_message(message, seen)
    assert text == "hello"
    assert calls == []
    assert sanitized == {"role": "assistant", "content": [{"text": "hello"}]}
    assert seen == set()


def test_parse_assistant_message_valid_tool() -> None:
    payload: dict[str, object] = {"meals": 1}
    message = _assistant([_tool_block("call-1", payload=payload)])
    seen: set[str] = set()
    text, calls, sanitized = parse_assistant_message(message, seen)
    assert text == ""
    assert calls == [ToolCall("call-1", "plan_groceries", payload)]
    assert sanitized == {
        "role": "assistant",
        "content": [
            {
                "toolUse": {
                    "toolUseId": "call-1",
                    "name": "plan_groceries",
                    "input": payload,
                }
            }
        ],
    }
    assert seen == {"call-1"}


def test_parse_provider_response_valid_text_end_turn() -> None:
    message = _assistant([_text_block("done")])
    stop, text, calls, sanitized = parse_provider_response(
        _response(message, "end_turn"), set()
    )
    assert stop == "end_turn"
    assert text == "done"
    assert calls == []
    assert sanitized["role"] == "assistant"


def test_parse_provider_response_valid_tool_use() -> None:
    message = _assistant([_tool_block("call-1")])
    seen: set[str] = set()
    stop, text, calls, sanitized = parse_provider_response(
        _response(message, "tool_use"), seen
    )
    assert stop == "tool_use"
    assert text == ""
    assert len(calls) == 1
    assert calls[0].tool_use_id == "call-1"
    assert seen == {"call-1"}
    content = sanitized["content"]
    assert isinstance(content, list)
    assert content[0]["toolUse"]["toolUseId"] == "call-1"


def test_tool_result_block_success_and_error_shape() -> None:
    ok = tool_result_block("call-1", {"evidence_id": "ev-1"}, success=True)
    assert ok == {
        "toolResult": {
            "toolUseId": "call-1",
            "content": [{"json": {"evidence_id": "ev-1"}}],
            "status": "success",
        }
    }
    err = tool_result_block("call-2", {"error": "bounded"}, success=False)
    assert err["toolResult"]["status"] == "error"
    assert err["toolResult"]["toolUseId"] == "call-2"


def test_duplicate_ids_in_message_are_invalid() -> None:
    message = _assistant([_tool_block("dup"), _tool_block("dup")])
    seen: set[str] = set()
    with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
        parse_assistant_message(message, seen)
    assert seen == set()


def test_duplicate_ids_across_seen_set_are_invalid() -> None:
    message = _assistant([_tool_block("seen-1")])
    seen = {"seen-1"}
    with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
        parse_assistant_message(message, seen)
    assert seen == {"seen-1"}


def test_more_than_three_tool_calls_are_invalid() -> None:
    blocks = [_tool_block(f"call-{index}") for index in range(MAX_TOOL_CALLS + 1)]
    message = _assistant(blocks)
    seen: set[str] = set()
    with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
        parse_assistant_message(message, seen)
    assert seen == set()


def test_blank_and_oversized_ids_and_names_are_invalid() -> None:
    seen: set[str] = set()
    long_id = "i" * (MAX_TOOL_FIELD_LEN + 1)
    long_name = "n" * (MAX_TOOL_FIELD_LEN + 1)
    cases = [
        _assistant([_tool_block("")]),
        _assistant([_tool_block("   ")]),
        _assistant([_tool_block("call-1", name="")]),
        _assistant([_tool_block("call-1", name="   ")]),
        _assistant([_tool_block(long_id)]),
        _assistant([_tool_block("call-1", name=long_name)]),
    ]
    for message in cases:
        with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
            parse_assistant_message(message, seen)
    assert seen == set()


def test_bad_role_is_invalid() -> None:
    message = {"role": "user", "content": [_text_block("hi")]}
    with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
        parse_assistant_message(message, set())


def test_bad_content_is_invalid() -> None:
    seen: set[str] = set()
    cases: list[object] = [
        {"role": "assistant", "content": []},
        {"role": "assistant", "content": "text"},
        {"role": "assistant", "content": [None]},
        {"role": "assistant", "content": ["text"]},
        _assistant([{"text": 1}]),
        _assistant([{"text": "x", "toolUse": {"toolUseId": "a"}}]),
    ]
    for message in cases:
        with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
            parse_assistant_message(message, seen)
    assert seen == set()


def test_bad_tool_input_is_invalid() -> None:
    message = _assistant(
        [
            {
                "toolUse": {
                    "toolUseId": "call-1",
                    "name": "plan_groceries",
                    "input": ["not", "a", "map"],
                }
            }
        ]
    )
    seen: set[str] = set()
    with pytest.raises(ChatProtocolError, match="assistant message is invalid"):
        parse_assistant_message(message, seen)
    assert seen == set()


def test_dict_and_list_stop_reason_raise_protocol_error() -> None:
    message = _assistant([_text_block("hi")])
    for stop in ({"reason": "end_turn"}, ["end_turn"]):
        with pytest.raises(
            ChatProtocolError, match="provider output is invalid"
        ) as caught:
            parse_provider_response(_response(message, stop), set())
        assert "end_turn" not in str(caught.value)
        assert _SECRET not in str(caught.value)


def test_end_turn_with_tool_calls_is_invalid() -> None:
    message = _assistant([_tool_block("call-1")])
    seen: set[str] = set()
    with pytest.raises(ChatProtocolError, match="provider output is invalid"):
        parse_provider_response(_response(message, "end_turn"), seen)
    assert seen == set()


def test_incomplete_stop_with_tool_calls_is_invalid() -> None:
    message = _assistant([_tool_block("call-1")])
    seen: set[str] = set()
    for stop in (
        "max_tokens",
        "stop_sequence",
        "guardrail_intervened",
        "content_filtered",
        "model_context_window_exceeded",
    ):
        with pytest.raises(ChatProtocolError, match="provider output is invalid"):
            parse_provider_response(_response(message, stop), seen)
    assert seen == set()


def test_tool_use_without_calls_is_invalid() -> None:
    message = _assistant([_text_block("asking")])
    seen: set[str] = set()
    with pytest.raises(ChatProtocolError, match="provider output is invalid"):
        parse_provider_response(_response(message, "tool_use"), seen)
    assert seen == set()


def test_failed_parse_does_not_mutate_seen_ids() -> None:
    valid_then_bad = _assistant(
        [_tool_block("keep-me"), _tool_block("keep-me"), _text_block("later")]
    )
    seen: set[str] = set()
    with pytest.raises(ChatProtocolError):
        parse_assistant_message(valid_then_bad, seen)
    assert seen == set()
    four = _assistant([_tool_block(f"id-{index}") for index in range(4)])
    with pytest.raises(ChatProtocolError):
        parse_assistant_message(four, seen)
    assert seen == set()
    mismatch = _assistant([_tool_block("id-a"), _tool_block("id-b")])
    with pytest.raises(ChatProtocolError):
        parse_provider_response(_response(mismatch, "end_turn"), seen)
    assert seen == set()


def test_reasoning_only_is_ignored_and_mixed_does_not_leak() -> None:
    thinking = {"text": "hidden plan"}
    original_input: dict[str, object] = {"meals": 2, "secret": _SECRET}
    message = _assistant(
        [
            {"reasoningContent": thinking},
            {
                "text": "public",
                "reasoningContent": thinking,
            },
            {
                "toolUse": {
                    "toolUseId": "call-1",
                    "name": "plan_groceries",
                    "input": original_input,
                },
                "reasoningContent": thinking,
            },
        ]
    )
    seen: set[str] = set()
    text, calls, sanitized = parse_assistant_message(message, seen)
    assert text == "public"
    assert "hidden" not in text
    assert calls == [
        ToolCall("call-1", "plan_groceries", {"meals": 2, "secret": _SECRET})
    ]
    dumped = str(sanitized)
    assert "reasoningContent" not in dumped
    assert "hidden plan" not in dumped
    content = sanitized["content"]
    assert isinstance(content, list)
    assert content[0] == {"text": "public"}
    assert content[1]["toolUse"]["toolUseId"] == "call-1"
    assert message["content"][0]["reasoningContent"] == thinking
    assert message["content"][1]["reasoningContent"] == thinking
    assert message["content"][2]["reasoningContent"] == thinking
    assert original_input == {"meals": 2, "secret": _SECRET}


def test_errors_omit_raw_input() -> None:
    message = _assistant(
        [
            {
                "toolUse": {
                    "toolUseId": "call-1",
                    "name": "plan_groceries",
                    "input": {"token": _SECRET},
                }
            },
            {
                "toolUse": {
                    "toolUseId": "call-1",
                    "name": "plan_groceries",
                    "input": {"token": _SECRET},
                }
            },
        ]
    )
    with pytest.raises(ChatProtocolError) as caught:
        parse_assistant_message(message, set())
    assert _SECRET not in str(caught.value)
    with pytest.raises(ChatProtocolError) as provider_caught:
        parse_provider_response(_response(message, {_SECRET: True}), set())
    assert _SECRET not in str(provider_caught.value)


def test_build_chat_result_keeps_candidate_for_allowed_status() -> None:
    candidate = _candidate()
    trace: list[dict[str, object]] = [{"tool": "plan_groceries"}]
    for status in ("planned", "needs_revision", "clarification"):
        result = build_chat_result(status, "ok", candidate, "ledger", trace, 2, 1)
        assert result["status"] == status
        assert result["plan"] == candidate["plan"]
        assert result["budget"] == candidate["budget"]
        assert result["request"] == candidate["request"]
        assert result["meal_nutrition"] == candidate["meal_nutrition"]
        assert result["evidence_id"] == "ev-1"
        assert result["evidence_revision_id"] == "ab" * 32
        assert result["spending_source"] == "ledger"
        assert result["tool_trace"] is trace
        assert result["model_turns"] == 2
        assert result["planner_revisions"] == 1


def test_build_chat_result_defaults_to_a_template_reply_with_a_hash() -> None:
    result = build_chat_result("planned", "ok", None, "ledger", [], 1, 0)
    assert result["reply_source"] == "template"
    assert result["reply_check"] is None
    assert result["reply_sha256"] == hashlib.sha256(b"ok").hexdigest()


def test_build_chat_result_records_the_reply_source_check_and_utf8_hash() -> None:
    check: dict[str, object] = {"ok": True, "reasons": [], "unmatched": []}
    result = build_chat_result(
        "clarification",
        "café",
        None,
        "ledger",
        [],
        2,
        0,
        reply_source="model",
        reply_check=check,
    )
    assert result["reply_source"] == "model"
    assert result["reply_check"] == check
    assert result["reply_sha256"] == hashlib.sha256("café".encode()).hexdigest()


def test_reasoning_block_beside_text_yields_only_the_text() -> None:
    message = {
        "role": "assistant",
        "content": [
            {"reasoningContent": {"reasoningText": {"text": "hidden-thoughts"}}},
            {"text": "visible", "reasoningContent": {"text": "hidden-thoughts"}},
        ],
    }
    text, calls, sanitized = parse_assistant_message(message, set())
    assert text == "visible"
    assert calls == []
    assert sanitized == {"role": "assistant", "content": [{"text": "visible"}]}
    assert "hidden-thoughts" not in json.dumps(sanitized)


def test_build_chat_result_drops_candidate_outside_keep_set() -> None:
    candidate = _candidate()
    result = build_chat_result("failed", "stopped", candidate, "ledger", [], 8, 3)
    assert result["plan"] is None
    assert result["budget"] is None
    assert result["request"] is None
    assert result["meal_nutrition"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["answer"] == "stopped"
    assert result["status"] == "failed"
    empty = build_chat_result("planned", "ok", None, "none", [], 1, 0)
    assert empty["plan"] is None
    assert empty["meal_nutrition"] is None
    assert empty["evidence_id"] is None
    assert empty["evidence_revision_id"] is None
    plain = {
        "plan": {"meals": 1},
        "budget": {"cents": 100},
        "request": {"servings": 2},
        "evidence_id": "ev-1",
    }
    missing = build_chat_result("planned", "ok", plain, "ledger", [], 1, 0)
    assert missing["evidence_id"] == "ev-1"
    assert missing["meal_nutrition"] is None
    assert missing["evidence_revision_id"] is None
