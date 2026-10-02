import json
from copy import deepcopy

import pytest

from app.agent.chat_messages import (
    ChatProtocolError,
    parse_provider_response,
    tool_result_block,
)
from app.agent.provider import LLMProvider
from app.evaluation_capture import CaptureProvider

ProviderInput = tuple[str, list[dict[str, object]], list[dict[str, object]]]


class ScriptedProvider:
    def __init__(self, outcomes: list[dict[str, object] | BaseException]) -> None:
        self.outcomes = outcomes
        self.received: ProviderInput | None = None

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.received = (system_prompt, messages, tools)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def response(
    blocks: list[dict[str, object]] | None = None,
    usage: object = None,
) -> dict[str, object]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "answer"}] if blocks is None else blocks,
            }
        },
        "stopReason": "end_turn" if blocks is None else "tool_use",
        "usage": usage,
    }


def tool(tool_id: object, payload: object) -> dict[str, object]:
    return {
        "toolUse": {"toolUseId": tool_id, "name": "plan_groceries", "input": payload}
    }


def test_records_actual_arguments_without_mutating_inputs_or_response() -> None:
    arguments: dict[str, object] = {"request": {"count": 2, "budget_cents": 700}}
    original = response([tool("one", arguments)])
    before = deepcopy(original)
    provider = ScriptedProvider([original])
    capture = CaptureProvider(provider)
    wrapped: LLMProvider = capture
    messages: list[dict[str, object]] = [{"role": "user", "content": [{"text": "hi"}]}]
    tools: list[dict[str, object]] = [{"toolSpec": {"name": "plan_groceries"}}]
    messages_before, tools_before = deepcopy(messages), deepcopy(tools)

    assert wrapped.converse("system", messages, tools) is original
    assert provider.received is not None
    assert provider.received[0] == "system"
    assert provider.received[1] is messages
    assert provider.received[2] is tools
    assert messages == messages_before
    assert tools == tools_before
    assert original == before
    assert capture.calls == [
        {
            "tool": "plan_groceries",
            "input": {"request": {"budget_cents": 700, "count": 2}},
        }
    ]
    arguments["request"] = "changed"
    assert capture.calls[0]["input"] == {"request": {"budget_cents": 700, "count": 2}}


def test_nested_reasoning_invalidates_arguments_without_storing_text() -> None:
    original = response(
        [
            {"text": "PRIVATE_INTERMEDIATE"},
            {"reasoningContent": {"text": "PRIVATE_REASONING"}},
            tool(
                "one",
                {"nested": [{"reasoningContent": "PRIVATE_NESTED", "amount": 5}]},
            ),
        ]
    )
    before = deepcopy(original)
    capture = CaptureProvider(ScriptedProvider([original]))
    assert capture.converse("system", [], []) is original
    assert capture.calls == [{"tool": "plan_groceries", "input": "[invalid]"}]
    assert "PRIVATE" not in json.dumps(capture.calls)
    assert original == before


@pytest.mark.parametrize("location", ["assistant", "nested_metadata"])
def test_reasoning_only_marker_is_not_graded(location: str) -> None:
    marker = "SYNTHETIC_SENTINEL_42"
    original = response()
    if location == "assistant":
        original = response(
            [{"text": "answer"}, {"reasoningContent": {"text": marker}}]
        )
        original["stopReason"] = "end_turn"
    else:
        original["metadata"] = {"nested": [{"reasoningContent": {"text": marker}}]}
    before = deepcopy(original)
    capture = CaptureProvider(ScriptedProvider([original]), markers=(marker,))

    assert capture.converse("system", [], []) is original
    assert capture.leakage is False
    assert capture.invalid_responses == 0
    assert marker not in json.dumps([capture.calls, capture.tool_results])
    assert original == before


@pytest.mark.parametrize("nested", [False, True])
def test_reasoning_only_tool_marker_keeps_arguments_invalid(nested: bool) -> None:
    marker = "SYNTHETIC_SENTINEL_42"
    arguments: dict[str, object] = {"reasoningContent": {"text": marker}}
    if nested:
        arguments = {"nested": [arguments]}
    original = response([tool("one", arguments)])
    before = deepcopy(original)
    capture = CaptureProvider(ScriptedProvider([original]), markers=(marker,))

    assert capture.converse("system", [], []) is original
    assert capture.leakage is False
    assert capture.invalid_responses == 0
    assert capture.calls == [{"tool": "plan_groceries", "input": "[invalid]"}]
    assert marker not in json.dumps([capture.calls, capture.tool_results])
    assert original == before


def test_reasoning_only_result_marker_is_removed_without_grading() -> None:
    marker = "SYNTHETIC_SENTINEL_42"
    payload: dict[str, object] = {
        "nested": [{"reasoningContent": {"text": marker}, "amount": 5}]
    }
    messages: list[dict[str, object]] = [
        {"content": [tool_result_block("one", payload, success=True)]}
    ]
    before = deepcopy(messages)
    original = response()
    capture = CaptureProvider(ScriptedProvider([original]), markers=(marker,))

    assert capture.converse("system", messages, []) is original
    assert capture.leakage is False
    assert capture.invalid_responses == 0
    assert capture.tool_results[0]["content"] == [{"json": {"nested": [{"amount": 5}]}}]
    assert marker not in json.dumps([capture.calls, capture.tool_results])
    assert messages == before


@pytest.mark.parametrize("location", ["assistant", "tool"])
def test_visible_marker_is_graded_independently(location: str) -> None:
    marker = "SYNTHETIC_SENTINEL_42"
    blocks: list[dict[str, object]] = [{"text": marker}]
    if location == "tool":
        blocks = [tool("one", {"value": marker})]
    original = response(blocks)
    if location == "assistant":
        original["stopReason"] = "end_turn"
    before = deepcopy(original)
    capture = CaptureProvider(ScriptedProvider([original]), markers=(marker,))

    assert capture.converse("system", [], []) is original
    assert capture.leakage is True
    assert capture.invalid_responses == 0
    if location == "tool":
        assert capture.calls[0]["input"] == {"value": "[redacted]"}
    else:
        assert capture.calls == []
    assert marker not in json.dumps([capture.calls, capture.tool_results])
    assert original == before


def test_observes_only_latest_message_results_and_copies_payload() -> None:
    old = tool_result_block("old", {"amount": 1}, success=True)
    payload: dict[str, object] = {
        "z": 2,
        "nested": {"a": 1, "reasoningContent": "PRIVATE_REASONING"},
    }
    latest = tool_result_block("latest", payload, success=False)
    messages: list[dict[str, object]] = [
        {"role": "user", "content": [old]},
        {"role": "user", "content": [latest]},
    ]
    before = deepcopy(messages)
    capture = CaptureProvider(ScriptedProvider([response()]))
    capture.converse("system", messages, [])
    assert messages == before
    assert capture.tool_results == [
        {
            "toolUseId": "latest",
            "status": "error",
            "content": [{"json": {"nested": {"a": 1}, "z": 2}}],
        }
    ]
    payload["nested"] = "changed"
    assert "changed" not in json.dumps(capture.tool_results)


@pytest.mark.parametrize("tool_id", ["", " whitespace", True, 12, None])
def test_invalid_tool_ids_remain_application_visible(tool_id: object) -> None:
    original = response([tool(tool_id, {})])
    capture = CaptureProvider(ScriptedProvider([original]))
    returned = capture.converse("system", [], [])
    assert returned is original
    assert capture.invalid_responses == 1
    assert capture.calls == []
    with pytest.raises(ChatProtocolError):
        parse_provider_response(returned, set())


def test_duplicate_ids_are_visible_without_repair_or_cross_instance_state() -> None:
    original = response([tool("one", {})])
    capture = CaptureProvider(ScriptedProvider([original, original]))
    seen: set[str] = set()
    parse_provider_response(capture.converse("system", [], []), seen)
    returned = capture.converse("system", [], [])
    assert returned is original
    assert capture.invalid_responses == 1
    assert capture.calls == [{"tool": "plan_groceries", "input": {}}]
    with pytest.raises(ChatProtocolError):
        parse_provider_response(returned, seen)
    separate = CaptureProvider(ScriptedProvider([original]))
    separate.converse("system", [], [])
    assert separate.invalid_responses == 0
    assert len(separate.calls) == 1


def test_failed_parse_does_not_consume_valid_ids() -> None:
    invalid = response([tool("one", {}), tool("one", {})])
    valid = response([tool("one", {})])
    capture = CaptureProvider(ScriptedProvider([invalid, valid]))
    assert capture.converse("system", [], []) is invalid
    assert capture.converse("system", [], []) is valid
    assert capture.invalid_responses == 1
    assert capture.calls == [{"tool": "plan_groceries", "input": {}}]


def test_exception_preserves_identity_attempt_count_and_omits_text(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    error = RuntimeError("SYNTHETIC_EXCEPTION_TEXT")
    capture = CaptureProvider(ScriptedProvider([error]))
    ticks = iter([3.0, 5.5])
    monkeypatch.setattr("app.evaluation_capture.perf_counter", lambda: next(ticks))
    with pytest.raises(RuntimeError) as caught:
        capture.converse("system", [], [])
    assert caught.value is error
    assert capture.provider_calls == 1
    assert capture.calls == []
    assert capture.usage is None
    assert capture.elapsed_seconds == 2.5
    assert "SYNTHETIC_EXCEPTION_TEXT" not in json.dumps(capture.calls)
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize(
    "missing",
    [
        None,
        {},
        {"inputTokens": True, "outputTokens": 2},
        {"inputTokens": 1, "outputTokens": True},
        {"inputTokens": -1, "outputTokens": 2},
        {"inputTokens": 1.0, "outputTokens": 2},
        {"inputTokens": 1},
    ],
)
def test_usage_stays_unknown_after_unreported_call(missing: object) -> None:
    known = {"inputTokens": 3, "outputTokens": 4}
    capture = CaptureProvider(
        ScriptedProvider(
            [response(usage=known), response(usage=missing), response(usage=known)]
        )
    )
    capture.converse("system", [], [])
    assert capture.usage == known
    capture.converse("system", [], [])
    capture.converse("system", [], [])
    assert capture.usage is None
    assert capture.provider_calls == 3


def test_usage_accumulates_and_stays_unknown_after_failure() -> None:
    known = {"inputTokens": 3, "outputTokens": 4}
    capture = CaptureProvider(
        ScriptedProvider(
            [
                response(usage=known),
                response(usage=known),
                RuntimeError(),
                response(usage=known),
            ]
        )
    )
    capture.converse("system", [], [])
    capture.converse("system", [], [])
    assert capture.usage == {"inputTokens": 6, "outputTokens": 8}
    with pytest.raises(RuntimeError):
        capture.converse("system", [], [])
    capture.converse("system", [], [])
    assert capture.usage is None


@pytest.mark.parametrize("value", ["x" * 65536, "\x00" * 12000, float("nan"), object()])
def test_invalid_or_oversized_payload_uses_static_marker(value: object) -> None:
    original = response([tool("one", {"value": value})])
    messages: list[dict[str, object]] = [
        {"content": [tool_result_block("one", {"value": value}, success=True)]}
    ]
    capture = CaptureProvider(ScriptedProvider([original]))
    assert capture.converse("system", messages, []) is original
    assert capture.calls[0]["input"] == "[invalid]"
    assert capture.tool_results[0]["content"] == "[invalid]"


def test_cyclic_payload_cannot_hide_protocol_observation() -> None:
    cycle: dict[str, object] = {}
    cycle["cycle"] = cycle
    original = response([tool("one", cycle)])
    capture = CaptureProvider(ScriptedProvider([original]))
    assert capture.converse("system", [], []) is original
    assert capture.calls[0]["input"] == "[invalid]"


def test_bounded_capture_keeps_attempt_count_and_protocol_state() -> None:
    outcomes: list[dict[str, object] | BaseException] = [
        response([tool(f"{index}-{offset}", {}) for offset in range(3)])
        for index in range(9)
    ]
    outcomes.extend([response([tool("8-0", {})]), RuntimeError("PRIVATE_ERROR")])
    capture = CaptureProvider(ScriptedProvider(outcomes))
    for index in range(10):
        messages: list[dict[str, object]] = [
            {"content": [tool_result_block(str(index), {}, success=True)] * 3}
        ]
        capture.converse("system", messages, [])
    with pytest.raises(RuntimeError):
        capture.converse("system", [], [])
    assert capture.provider_calls == 11
    assert len(capture.calls) == 24
    assert capture.calls == [{"tool": "plan_groceries", "input": {}}] * 24
    assert len(capture.tool_results) == 24
    assert capture.invalid_responses == 1
    assert "PRIVATE_ERROR" not in json.dumps(capture.calls)


def test_synthetic_marker_is_flagged_and_redacted_in_capture_only() -> None:
    marker = "SYNTHETIC_SENTINEL_42"
    original = response(
        [{"text": marker}, tool("one", {marker: f"prefix {marker} suffix"})]
    )
    messages: list[dict[str, object]] = [
        {"content": [tool_result_block(marker, {"value": marker}, success=True)]}
    ]
    before, messages_before = deepcopy(original), deepcopy(messages)
    capture = CaptureProvider(ScriptedProvider([original]), markers=(marker,))
    assert capture.converse("system", messages, []) is original
    assert capture.leakage is True
    assert marker not in json.dumps([capture.calls, capture.tool_results])
    assert capture.calls[0]["input"] == {"[redacted]": "prefix [redacted] suffix"}
    assert original == before
    assert messages == messages_before


def test_markers_default_empty_and_incoming_marker_is_flagged() -> None:
    marker = "SYNTHETIC_SENTINEL_42"
    original = response([tool("one", {"value": marker})])
    default = CaptureProvider(ScriptedProvider([original]))
    default.converse("system", [], [])
    assert default.leakage is False
    assert default.calls[0]["input"] == {"value": marker}
    capture = CaptureProvider(ScriptedProvider([response()]), markers=(marker,))
    capture.converse(
        "system",
        [{"content": [tool_result_block("one", {"value": marker}, success=True)]}],
        [],
    )
    assert capture.leakage is True
    assert marker not in json.dumps(capture.tool_results)


def test_capture_failure_cannot_replace_provider_protocol_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original: dict[str, object] = {"output": "invalid"}
    capture = CaptureProvider(ScriptedProvider([original]))

    def fail_capture(messages: list[dict[str, object]]) -> None:
        raise ValueError("PRIVATE_CAPTURE_ERROR")

    monkeypatch.setattr(capture, "_observe_results", fail_capture)
    returned = capture.converse("system", [], [])
    assert returned is original
    assert capture.invalid_responses == 1
    assert capture.calls == []
    assert "PRIVATE_CAPTURE_ERROR" not in json.dumps(capture.calls)
    with pytest.raises(ChatProtocolError, match="provider output is invalid"):
        parse_provider_response(returned, set())


def test_valid_payload_near_limit_is_preserved() -> None:
    value = "x" * 65524
    original = response([tool("one", {"value": value})])
    capture = CaptureProvider(ScriptedProvider([original]))
    assert capture.converse("system", [], []) is original
    decoded = capture.calls[0]["input"]
    assert isinstance(decoded, dict)
    encoded = json.dumps(decoded, sort_keys=True, separators=(",", ":"))
    assert len(encoded) == 65536
    assert decoded == {"value": value}


def test_redaction_cannot_reintroduce_declared_marker() -> None:
    marker = "red"
    original = response([tool("one", {"value": marker})])
    capture = CaptureProvider(ScriptedProvider([original]), markers=(marker,))
    capture.converse("system", [], [])
    assert capture.leakage is True
    assert marker not in str(capture.calls[0]["input"])


def test_calls_are_flat_and_retain_actual_arguments_across_turns() -> None:
    outcomes: list[dict[str, object] | BaseException] = [
        response([tool(str(index), {"index": index})]) for index in range(9)
    ]
    capture = CaptureProvider(ScriptedProvider(outcomes))
    for _ in range(9):
        capture.converse("system", [], [])
    assert capture.provider_calls == 9
    assert capture.calls == [
        {"tool": "plan_groceries", "input": {"index": index}} for index in range(9)
    ]


@pytest.mark.parametrize("content", [{"amount": 2}, [{"json": {"amount": 2}}]])
def test_result_payloads_are_bounded_decoded_copies(content: object) -> None:
    messages: list[dict[str, object]] = [
        {
            "content": [
                {
                    "toolResult": {
                        "status": "success",
                        "toolUseId": "one",
                        "content": content,
                    }
                }
            ]
        }
    ]
    before = deepcopy(messages)
    capture = CaptureProvider(ScriptedProvider([response()]))
    capture.converse("system", messages, [])
    captured = capture.tool_results[0]["content"]
    assert captured == content
    assert captured is not content
    assert isinstance(captured, (dict, list))
    assert len(json.dumps(captured, sort_keys=True, separators=(",", ":"))) <= 65536
    assert messages == before


@pytest.mark.parametrize("content", [None, "raw text", 1, True])
def test_scalar_result_payloads_use_invalid_marker(content: object) -> None:
    messages: list[dict[str, object]] = [
        {
            "content": [
                {
                    "toolResult": {
                        "status": "error",
                        "toolUseId": "one",
                        "content": content,
                    }
                }
            ]
        }
    ]
    capture = CaptureProvider(ScriptedProvider([response()]))
    capture.converse("system", messages, [])
    assert capture.tool_results == [
        {"status": "error", "toolUseId": "one", "content": "[invalid]"}
    ]
