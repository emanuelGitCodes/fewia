import json
from copy import deepcopy
from typing import cast

import pytest

from app.agent.provider import LLMProvider, LLMUnavailable
from app.evaluation_fault_provider import (
    PROTOCOL_VARIANTS,
    UNAVAILABLE_VARIANTS,
    FaultProvider,
)


def _messages(*statuses: str) -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {"toolResult": {"toolUseId": f"t{i}", "status": status}}
                for i, status in enumerate(statuses)
            ],
        }
    ]


def test_exported_variant_limits_and_outcomes_match_protocol_source() -> None:
    assert UNAVAILABLE_VARIANTS == {"unavailable": (1, 0, "chat_unavailable")}
    assert PROTOCOL_VARIANTS == {
        "unknown_tool": (8, 0, "limit"),
        "invalid_planner": (4, 3, "limit"),
        "malformed_input": (1, 0, "chat_protocol_error"),
        "duplicate_id": (2, 0, "chat_protocol_error"),
        "too_many_tools": (1, 0, "chat_protocol_error"),
        "stop_mismatch": (1, 0, "chat_protocol_error"),
    }


@pytest.mark.parametrize(
    ("variant", "name", "payload", "first_ids", "second_ids", "stop_reason"),
    [
        (
            "unknown_tool",
            "unknown_tool",
            {"meals": "invalid"},
            ["t1"],
            ["t2"],
            "tool_use",
        ),
        (
            "invalid_planner",
            "plan_groceries",
            {"meals": "invalid"},
            ["t1"],
            ["t2"],
            "tool_use",
        ),
        ("malformed_input", "unknown_tool", [], ["t1"], ["t2"], "tool_use"),
        (
            "duplicate_id",
            "unknown_tool",
            {"meals": "invalid"},
            ["t1"],
            ["t1"],
            "tool_use",
        ),
        (
            "too_many_tools",
            "unknown_tool",
            {"meals": "invalid"},
            ["t0", "t1", "t2", "t3"],
            ["t0", "t1", "t2", "t3"],
            "tool_use",
        ),
        (
            "stop_mismatch",
            "unknown_tool",
            {"meals": "invalid"},
            ["t1"],
            ["t2"],
            "end_turn",
        ),
    ],
)
def test_variants_return_exact_envelopes_without_mutating_inputs(
    variant: str,
    name: str,
    payload: dict[str, object] | list[object],
    first_ids: list[str],
    second_ids: list[str],
    stop_reason: str,
) -> None:
    scripted = FaultProvider(variant, cutoff=2)
    provider: LLMProvider = scripted
    messages = _messages("error")
    tools: list[dict[str, object]] = [{"toolSpec": {"name": "plan_groceries"}}]
    original = deepcopy((messages, tools))
    assert (scripted.calls, scripted.errors) == (0, 0)
    for call, ids in enumerate((first_ids, second_ids), start=1):
        response = provider.converse("Guard probe.", messages, tools)
        assert response == {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"toolUse": {"toolUseId": key, "name": name, "input": payload}}
                        for key in ids
                    ],
                }
            },
            "stopReason": stop_reason,
        }
        assert "SYNTHETIC_PROTOCOL_SECRET_SENTINEL" not in json.dumps(response)
        assert (scripted.calls, scripted.errors) == (call, call)
        assert (messages, tools) == original


@pytest.mark.parametrize(
    ("variant", "calls", "errors"),
    [
        ("unknown_tool", 8, 7),
        ("invalid_planner", 4, 3),
        ("malformed_input", 1, 0),
        ("duplicate_id", 2, 1),
        ("too_many_tools", 1, 0),
        ("stop_mismatch", 1, 0),
    ],
)
def test_source_call_sequences_preserve_counters_and_cutoff(
    variant: str, calls: int, errors: int
) -> None:
    provider = FaultProvider(variant, cutoff=calls)
    provider.converse("", _messages(), [])
    for _ in range(calls - 1):
        provider.converse("", _messages("error"), [])
    assert (provider.calls, provider.errors) == (calls, errors)
    messages = _messages("error")
    original = deepcopy(messages)
    for extra in (1, 2):
        with pytest.raises(LLMUnavailable) as exc:
            provider.converse("", messages, [])
        assert exc.value.args == ("SYNTHETIC_PROTOCOL_SECRET_SENTINEL",)
        assert (provider.calls, provider.errors) == (calls + extra, errors)
        assert messages == original


def test_only_latest_rejected_tool_results_count_per_invocation() -> None:
    provider = FaultProvider("unknown_tool", cutoff=2)
    messages = [*_messages("error"), *_messages("success", "error", "error")]
    content = cast(list[dict[str, object]], messages[-1]["content"])
    content.extend([{"text": "error"}, {"toolResult": "error"}, {"toolResult": {}}])
    original = deepcopy(messages)
    for call in (1, 2):
        provider.converse("", messages, [])
        assert (provider.calls, provider.errors) == (call, 2 * call)
        assert messages == original


def test_missing_content_observes_no_rejected_results() -> None:
    provider = FaultProvider("unknown_tool", cutoff=1)
    provider.converse("", [{"role": "user"}], [])
    assert (provider.calls, provider.errors) == (1, 0)


@pytest.mark.parametrize("variant", ["unavailable", "unknown_tool"])
def test_zero_cutoff_raises_before_reading_messages(variant: str) -> None:
    provider = FaultProvider(variant, cutoff=0)
    with pytest.raises(LLMUnavailable) as exc:
        provider.converse("", [], [])
    assert exc.value.args == ("SYNTHETIC_PROTOCOL_SECRET_SENTINEL",)
    assert (provider.calls, provider.errors) == (1, 0)


def test_unavailable_counts_every_attempt_without_counting_errors() -> None:
    provider = FaultProvider("unavailable", cutoff=8)
    messages = _messages("error")
    tools: list[dict[str, object]] = [{"toolSpec": {"name": "plan_groceries"}}]
    original = deepcopy((messages, tools))
    for call in (1, 2):
        with pytest.raises(LLMUnavailable) as exc:
            provider.converse("Guard probe.", messages, tools)
        assert exc.value.args == ("SYNTHETIC_PROTOCOL_SECRET_SENTINEL",)
        assert (provider.calls, provider.errors) == (call, 0)
        assert (messages, tools) == original


@pytest.mark.parametrize("variant", list(PROTOCOL_VARIANTS))
def test_expected_and_evidence_fields_do_not_control_behavior(variant: str) -> None:
    baseline = FaultProvider(variant, cutoff=1).converse("", _messages(), [])
    messages = _messages()
    messages[0].update(expected={"accepted": True}, evidence={"outcome": "success"})
    tools: list[dict[str, object]] = [{"expected": "end_turn", "evidence": "quality"}]
    original = deepcopy((messages, tools))
    response = FaultProvider(variant, cutoff=1).converse(
        "Different prompt.", messages, tools
    )
    assert response == baseline
    assert (messages, tools) == original


@pytest.mark.parametrize("variant", list(PROTOCOL_VARIANTS))
def test_response_mutation_does_not_affect_later_envelopes(variant: str) -> None:
    provider = FaultProvider(variant, cutoff=2)
    response = provider.converse("", _messages(), [])
    output = cast(dict[str, object], response["output"])
    message = cast(dict[str, object], output["message"])
    content = cast(list[dict[str, object]], message["content"])
    tool = cast(dict[str, object], content[0]["toolUse"])
    tool.update(toolUseId="changed", name="changed", input={"changed": True})
    content.clear()
    fresh = FaultProvider(variant, cutoff=2)
    fresh.converse("", _messages(), [])
    assert provider.converse("", _messages(), []) == fresh.converse("", _messages(), [])
