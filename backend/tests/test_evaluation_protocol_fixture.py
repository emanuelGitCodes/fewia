from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from app.agent.chat_messages import (
    ChatProtocolError,
    parse_provider_response,
    tool_result_block,
)
from app.agent.provider import LLMProvider
from app.evaluation_protocol_fixture import (
    CLOCK_ERROR,
    FakeProtocolProvider,
    as_map,
    period,
)

SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _tool_id(response: dict[str, object]) -> str:
    output = response["output"]
    assert isinstance(output, dict)
    message = output["message"]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, list)
    block = content[0]
    assert isinstance(block, dict)
    tool = block["toolUse"]
    assert isinstance(tool, dict)
    tool_id = tool["toolUseId"]
    assert isinstance(tool_id, str)
    return tool_id


def _input_of(response: dict[str, object]) -> object:
    output = response["output"]
    assert isinstance(output, dict)
    message = output["message"]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, list)
    block = content[0]
    assert isinstance(block, dict)
    tool = block["toolUse"]
    assert isinstance(tool, dict)
    return tool["input"]


def _assert_static(exc: BaseException, raw: str) -> None:
    assert type(exc) is ValueError
    assert exc.args == (CLOCK_ERROR,)
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert raw not in str(exc)
    assert raw not in repr(exc)
    assert SECRET_MARKER not in str(exc)
    assert SECRET_MARKER not in repr(exc)


def test_as_map_non_map_returns_empty() -> None:
    assert as_map(None) == {}
    assert as_map(0) == {}
    assert as_map("x") == {}
    assert as_map([{"a": 1}]) == {}
    src = {"a": 1}
    out = as_map(src)
    out["b"] = 2
    assert src == {"a": 1}
    assert as_map({1: "x"}) == {"1": "x"}


def test_period_static_bad_clock_no_marker() -> None:
    marker = f"{SECRET_MARKER}-not-a-clock"
    with pytest.raises(ValueError) as bad_text:
        period({"budget_period": marker})
    _assert_static(bad_text.value, marker)

    with pytest.raises(ValueError) as not_first:
        period({"budget_period": "2026-09-15"})
    _assert_static(not_first.value, "2026-09-15")

    with pytest.raises(ValueError) as not_string:
        period({"budget_period": date(2026, 9, 1)})
    _assert_static(not_string.value, "2026-09-01")

    assert period({"budget_period": "2026-09-01"}) == date(2026, 9, 1)


def test_protocol_shape_unique_ids_and_counter() -> None:
    payload: dict[str, object] = {"meals": 1}
    concrete = FakeProtocolProvider("plan_groceries", payload)
    provider: LLMProvider = concrete
    messages: list[dict[str, object]] = [{"role": "user", "content": [{"text": "hi"}]}]
    first = provider.converse("system", messages, [])
    second = provider.converse("system", messages, [])
    assert first.keys() == {"output", "stopReason"}
    assert first["stopReason"] == "tool_use"
    assert second["stopReason"] == "tool_use"
    assert concrete.calls == 2
    seen: set[str] = set()
    stop, text, calls, sanitized = parse_provider_response(first, seen)
    assert stop == "tool_use"
    assert text == ""
    assert calls[0].tool_use_id == "t1"
    assert calls[0].name == "plan_groceries"
    assert calls[0].tool_input == payload
    assert _tool_id(first) == "t1"
    assert _tool_id(second) == "t2"
    parse_provider_response(second, seen)
    assert seen == {"t1", "t2"}
    assert sanitized["role"] == "assistant"


def test_malformed_payload_is_intentional() -> None:
    provider = FakeProtocolProvider("plan_groceries", 0)
    response = provider.converse("system", [{"role": "user", "content": []}], [])
    assert _input_of(response) == 0
    with pytest.raises(ChatProtocolError) as exc:
        parse_provider_response(response, set())
    assert str(exc.value) == "assistant message is invalid"


def test_error_result_filter_ignores_nonerror_success_nonjson() -> None:
    provider = FakeProtocolProvider("plan_groceries", {})
    prior = {
        "role": "user",
        "content": [tool_result_block("old", {"error": "old-error"}, success=False)],
    }
    last = {
        "role": "user",
        "content": [
            tool_result_block("ok", {"error": "from-success"}, success=True),
            {
                "toolResult": {
                    "toolUseId": "bad-json",
                    "status": "error",
                    "content": [{"text": "not-json"}],
                }
            },
            {
                "toolResult": {
                    "toolUseId": "bad-type",
                    "status": "error",
                    "content": [{"json": {"error": 1}}],
                }
            },
            {"text": "ignore"},
            tool_result_block("err", {"error": "real-error"}, success=False),
        ],
    }
    provider.converse("system", [prior, last], [])
    assert provider.result_errors == ["real-error"]


def test_messages_not_mutated_and_no_retained_secret_metadata() -> None:
    marker = f"{SECRET_MARKER}-raw"
    payload: dict[str, object] = {"ok": True}
    messages: list[dict[str, object]] = [
        {"role": "user", "content": [{"text": marker}], "credentials": marker}
    ]
    tools: list[dict[str, object]] = [{"name": marker, "secret": marker}]
    snapshot = copy.deepcopy(messages)
    tool_snapshot = copy.deepcopy(tools)
    provider = FakeProtocolProvider("plan_groceries", payload)
    response = provider.converse(marker, messages, tools)
    assert messages == snapshot
    assert tools == tool_snapshot
    blob = json.dumps(response)
    assert marker not in blob
    assert SECRET_MARKER not in blob
    assert not hasattr(provider, "messages")
    assert not hasattr(provider, "system_prompt")
    assert not hasattr(provider, "tools")
    mutated = _input_of(response)
    assert isinstance(mutated, dict)
    mutated["ok"] = False
    assert payload == {"ok": True}
    assert provider.payload is payload
    again = provider.converse(marker, messages, tools)
    assert _input_of(again) == {"ok": True}
    assert payload == {"ok": True}
