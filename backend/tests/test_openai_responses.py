import asyncio
import gzip
import json
import socket
import time
import zlib
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from threading import enumerate as enumerate_threads
from typing import Literal, NoReturn, cast

import httpx
import pytest

from app.agent.chat_messages import parse_provider_response, tool_result_block
from app.agent.provider import LLMUnavailable
from app.provider_settings import ProviderConfigurationError
from app.providers import http_client
from app.providers.openai_responses import OpenAIResponsesProvider

_KEY = "TEST_ONLY_OPENAI_KEY_MARKER"


def _key_file(tmp_path: Path) -> Path:
    path = tmp_path / "test-key"
    path.write_text(f"{_KEY}\n", encoding="ascii")
    return path


def _tools() -> list[dict[str, object]]:
    return [
        {
            "toolSpec": {
                "name": "lookup",
                "description": "Look up sample prices.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["item"],
                        "additionalProperties": False,
                    }
                },
            }
        }
    ]


def _messages() -> list[dict[str, object]]:
    return [{"role": "user", "content": [{"text": "Find sample prices."}]}]


def _call(
    call_id: str = "call_1", arguments: str = '{"item":"beans"}'
) -> dict[str, object]:
    return {
        "type": "function_call",
        "id": "fc_provider_only",
        "call_id": call_id,
        "name": "lookup",
        "arguments": arguments,
        "status": "completed",
    }


def _text(text: str = "Sample prices are estimates.") -> dict[str, object]:
    return {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text}],
    }


def _response(output: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [_text()] if output is None else output,
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 60},
            "output_tokens": 12,
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }


def test_full_tool_round_trip_is_stateless_and_preserves_order(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []
    replies = [_response([_text("Checking."), _call(), _call("call_2")]), _response()]

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        assert request.headers["authorization"] == f"Bearer {_KEY}"
        return httpx.Response(200, json=replies.pop(0))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        key_file = _key_file(tmp_path)
        provider = OpenAIResponsesProvider(key_file, client=client)
        messages, tools = _messages(), _tools()
        original = deepcopy((messages, tools))
        first = provider.converse("Use sample values.", messages, tools)
        stop, text, calls, assistant = parse_provider_response(first, set())
        assert stop == "tool_use"
        assert text == "Checking."
        assert [call.tool_use_id for call in calls] == ["call_1", "call_2"]
        assert (messages, tools) == original
        messages.extend(
            [
                assistant,
                {
                    "role": "user",
                    "content": [
                        tool_result_block("call_1", {"sample": True}, success=True),
                        tool_result_block(
                            "call_2", {"error": "Unavailable"}, success=False
                        ),
                    ],
                },
            ]
        )
        second_provider = OpenAIResponsesProvider(key_file, client=client)
        second = second_provider.converse("Use sample values.", messages, tools)
    assert parse_provider_response(second, {"call_1", "call_2"})[0] == "end_turn"
    assert first["usage"] == {
        "inputTokens": 100,
        "outputTokens": 12,
        "cacheReadInputTokens": 60,
    }
    first_request = requests[0]
    spec = cast(dict[str, object], tools[0]["toolSpec"])
    schema = cast(dict[str, object], spec["inputSchema"])["json"]
    assert first_request == {
        "model": "gpt-6-luna",
        "instructions": "Use sample values.",
        "input": [{"role": "user", "content": "Find sample prices."}],
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "description": "Look up sample prices.",
                "parameters": schema,
                "strict": False,
            }
        ],
        "reasoning": {"effort": "none"},
        "store": False,
        "max_output_tokens": 4096,
        "parallel_tool_calls": False,
    }
    items = cast(list[dict[str, object]], requests[1]["input"])
    assert items[:2] == [
        {"role": "user", "content": "Find sample prices."},
        {"role": "assistant", "content": "Checking."},
    ]
    assert items[2:4] == [
        {
            "type": "function_call",
            "call_id": call_id,
            "name": "lookup",
            "arguments": '{"item":"beans"}',
        }
        for call_id in ("call_1", "call_2")
    ]
    assert [item["call_id"] for item in items[4:]] == ["call_1", "call_2"]
    assert [item["type"] for item in items[4:]] == ["function_call_output"] * 2
    statuses = [json.loads(str(item["output"]))["status"] for item in items[4:]]
    assert statuses == ["success", "error"]
    assert "fc_provider_only" not in json.dumps(requests)
    assert _KEY not in json.dumps(requests)


@pytest.mark.parametrize("count", [1, 3])
def test_calls_within_shared_bound_are_preserved(tmp_path: Path, count: int) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_response([_call(f"call_{index}") for index in range(count)])
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        response = provider.converse("System", _messages(), _tools())
    calls = parse_provider_response(response, set())[2]
    assert [call.tool_use_id for call in calls] == [f"call_{i}" for i in range(count)]


@pytest.mark.parametrize("cached", [None, 0])
def test_plain_text_without_tools_and_optional_cache_usage(
    tmp_path: Path, cached: int | None
) -> None:
    usage: dict[str, object] = {"input_tokens": 10, "output_tokens": 5}
    if cached is not None:
        usage["input_tokens_details"] = {"cached_tokens": cached}

    def handle(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["tools"] == []
        return httpx.Response(200, json={**_response(), "usage": usage})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        response = provider.converse("System", _messages(), [])
    stop, text, calls, _ = parse_provider_response(response, set())
    assert (stop, text, calls) == ("end_turn", "Sample prices are estimates.", [])
    expected = {"inputTokens": 10, "outputTokens": 5}
    if cached is not None:
        expected["cacheReadInputTokens"] = cached
    assert response["usage"] == expected


@pytest.mark.parametrize("region", ["us", "global"])
def test_fixed_endpoint_auth_and_no_redirect(
    tmp_path: Path, region: Literal["us", "global"]
) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.headers["authorization"] == f"Bearer {_KEY}"
        return httpx.Response(302, headers={"Location": "https://other.invalid"})

    with httpx.Client(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as client:
        provider = OpenAIResponsesProvider(
            _key_file(tmp_path), region=region, client=client
        )
        with pytest.raises(LLMUnavailable):
            provider.converse("System", _messages(), _tools())
    host = "us.api.openai.com" if region == "us" else "api.openai.com"
    assert seen == [f"https://{host}/v1/responses"]


@pytest.mark.parametrize(
    "failure", ["timeout", "auth", "server", "invalid_json", "duplicate_json"]
)
def test_failures_are_generic_and_never_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], failure: str
) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise httpx.ReadTimeout(_KEY, request=request)
        if failure == "auth":
            return httpx.Response(401, json={"error": {"message": _KEY}})
        if failure == "server":
            return httpx.Response(500, text=_KEY)
        if failure == "duplicate_json":
            return httpx.Response(
                200, text='{"status":"completed","status":"failed","output":[]}'
            )
        return httpx.Response(200, text=_KEY)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable) as raised:
            provider.converse("System", _messages(), _tools())
    assert calls == 1
    assert str(raised.value) == "The language model is unavailable"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert _KEY not in repr(raised.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert _KEY not in captured.err
    assert len(captured.err.splitlines()) == 1
    assert json.loads(captured.err)["event"] == "openai_responses_failed"


@pytest.mark.parametrize(
    "arguments",
    [
        "{",
        "[]",
        "null",
        "1",
        '{"item":1,"item":2}',
        '{"nested":{"a":1,"a":2}}',
        '{"item":NaN}',
        '{"item":1e999}',
    ],
)
def test_malformed_arguments_never_reach_dispatch(
    tmp_path: Path, arguments: str
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response([_call(arguments=arguments)]))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable):
            provider.converse("System", _messages(), _tools())


@pytest.mark.parametrize(
    "output",
    [
        [_call(), _call()],
        [_call("bad id")],
        [_call("x" * 65)],
        [_call("")],
        [_call("bad\n")],
        [{**_call(), "name": "unknown"}],
        [{**_call(), "call_id": None}],
        [{**_call(), "arguments": {"item": "beans"}}],
        [{**_call(), "status": "in_progress"}],
        [_call(str(index)) for index in range(4)],
        [{"type": "unknown"}],
        [{**_text(), "role": "user"}],
        [{**_text(), "content": [{"type": "output_text", "text": 3}]}],
        [{**_text(), "status": "incomplete"}],
        [{**_text(), "content": []}, _call()],
        [],
    ],
)
def test_invalid_output_is_unavailable(
    tmp_path: Path, output: list[dict[str, object]]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response(output))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable):
            provider.converse("System", _messages(), _tools())


_REASONING: dict[str, object] = {
    "type": "reasoning",
    "summary": [],
    "encrypted_content": "opaque",
}


def _run(
    tmp_path: Path, handle: Callable[[httpx.Request], httpx.Response]
) -> dict[str, object]:
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        return provider.converse("System", _messages(), _tools())


def _failure_line(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert len(lines) == 1
    for secret in (_KEY, "Bearer", "PRIVATE_MESSAGE", "Find sample prices."):
        assert secret not in captured.err
    line = json.loads(lines[0])
    assert line["event"] == "openai_responses_failed"
    return cast(dict[str, object], line)


def test_reasoning_items_are_skipped_before_text(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        lambda request: httpx.Response(200, json=_response([_REASONING, _text()])),
    )
    stop, text, calls, _ = parse_provider_response(result, set())
    assert (stop, text, calls) == ("end_turn", "Sample prices are estimates.", [])


def test_reasoning_items_are_skipped_before_tool_call(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        lambda request: httpx.Response(200, json=_response([_REASONING, _call()])),
    )
    stop, _, calls, _ = parse_provider_response(result, {"lookup"})
    assert stop == "tool_use"
    assert len(calls) == 1


def test_reasoning_only_output_is_unavailable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(LLMUnavailable):
        _run(
            tmp_path, lambda request: httpx.Response(200, json=_response([_REASONING]))
        )
    line = _failure_line(capsys)
    assert line["reason"] == "invalid_response"
    assert line["item_type"] is None


def test_unknown_item_type_is_logged_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output: list[dict[str, object]] = [{"type": "web_search_call"}]
    with pytest.raises(LLMUnavailable):
        _run(tmp_path, lambda request: httpx.Response(200, json=_response(output)))
    line = _failure_line(capsys)
    assert line["reason"] == "invalid_response"
    assert line["http_status"] == 200
    assert line["exception"] == "_Invalid"
    assert line["item_type"] == "web_search_call"


def test_request_disables_reasoning_and_storage(tmp_path: Path) -> None:
    bodies: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_response())

    _run(tmp_path, handle)
    assert bodies[0]["reasoning"] == {"effort": "none"}
    assert bodies[0]["store"] is False


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_log_bounded_error_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    body = {
        "error": {
            "message": f"PRIVATE_MESSAGE {_KEY}",
            "type": "invalid_request_error",
            "code": "bad.code-1",
        }
    }
    with pytest.raises(LLMUnavailable):
        _run(tmp_path, lambda request: httpx.Response(status, json=body))
    line = _failure_line(capsys)
    assert line["reason"] == "http_error"
    assert line["http_status"] == status
    assert line["error_type"] == "invalid_request_error"
    assert line["error_code"] == "bad.code-1"


@pytest.mark.parametrize(
    "body",
    [
        httpx.Response(500, text="not json"),
        httpx.Response(500, json=["error"]),
        httpx.Response(500, json={"error": "PRIVATE_MESSAGE"}),
        httpx.Response(500, json={"error": {"type": "x" * 65, "code": "has space\n"}}),
        httpx.Response(500, json={"error": {"type": 5, "code": None}}),
    ],
)
def test_unbounded_error_fields_are_not_logged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], body: httpx.Response
) -> None:
    with pytest.raises(LLMUnavailable):
        _run(tmp_path, lambda request: body)
    line = _failure_line(capsys)
    assert line["http_status"] == 500
    assert line["error_type"] is None
    assert line["error_code"] is None


def test_transport_timeout_is_logged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(_KEY, request=request)

    with pytest.raises(LLMUnavailable):
        _run(tmp_path, handle)
    line = _failure_line(capsys)
    assert line["reason"] == "transport_error"
    assert line["exception"] == "ReadTimeout"
    assert line["http_status"] is None


def test_invalid_input_is_logged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(ValueError, match="Provider input is invalid"):
            provider.converse(" ", _messages(), _tools())
    line = _failure_line(capsys)
    assert line["reason"] == "invalid_input"
    assert line["exception"] == "_Invalid"


def test_default_client_timeout(tmp_path: Path) -> None:
    provider = OpenAIResponsesProvider(_key_file(tmp_path))
    timeout = provider._client.timeout  # noqa: SLF001
    assert (timeout.connect, timeout.read) == (5, 45)
    provider._client.close()  # noqa: SLF001


@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
def test_incomplete_reply_never_dispatches_tools(tmp_path: Path, reason: str) -> None:
    response = {
        **_response([_call(arguments="{")]),
        "status": "incomplete",
        "incomplete_details": {"reason": reason},
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        result = provider.converse("System", _messages(), _tools())
    stop, _, calls, _ = parse_provider_response(result, set())
    expected = "max_tokens" if reason == "max_output_tokens" else "content_filtered"
    assert stop == expected
    assert calls == []


def test_refusal_suppresses_text_and_calls(tmp_path: Path) -> None:
    refusal = {
        **_text(),
        "content": [{"type": "refusal", "refusal": "Provider details"}],
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response([_call(), refusal]))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        result = provider.converse("System", _messages(), _tools())
    stop, text, calls, _ = parse_provider_response(result, set())
    assert (stop, text, calls) == ("guardrail_intervened", "", [])


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True, "output_tokens": 1},
        {"input_tokens": -1, "output_tokens": 1},
        {"input_tokens": 1},
        {
            "input_tokens": 1,
            "output_tokens": 1,
            "input_tokens_details": {"cached_tokens": 2},
        },
        {
            "input_tokens": 1,
            "output_tokens": 1,
            "input_tokens_details": {"cached_tokens": False},
        },
    ],
)
def test_invalid_usage_fails_closed(tmp_path: Path, usage: dict[str, object]) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**_response(), "usage": usage})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable):
            provider.converse("System", _messages(), _tools())


@pytest.mark.parametrize(
    "response",
    [
        {"status": "failed", "error": {"message": "private"}, "output": [_call()]},
        {"status": "in_progress", "output": [_call()]},
        {
            "status": "incomplete",
            "incomplete_details": {"reason": "unknown"},
            "output": [_call()],
        },
        {"status": "completed", "error": {"message": "private"}, "output": [_call()]},
        {"status": "completed", "output": {}},
    ],
)
def test_error_statuses_fail_closed(
    tmp_path: Path, response: dict[str, object]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable):
            provider.converse("System", _messages(), _tools())


@pytest.mark.parametrize(
    "case",
    [
        "orphan",
        "crossed",
        "duplicate_result",
        "pending",
        "reused",
        "wrong_role",
        "mixed",
        "bad_status",
        "bad_schema",
        "duplicate_tool",
        "nested_keys",
    ],
)
def test_invalid_history_and_tools_fail_before_network(
    tmp_path: Path, case: str
) -> None:
    messages, tools = _messages(), _tools()
    assistant: dict[str, object] = {
        "role": "assistant",
        "content": [
            {
                "toolUse": {
                    "toolUseId": "call_1",
                    "name": "lookup",
                    "input": {"item": "beans"},
                }
            }
        ],
    }
    result = tool_result_block("call_1", {"sample": True}, success=True)
    if case == "orphan":
        messages.append({"role": "user", "content": [result]})
    elif case == "crossed":
        messages.extend(
            [
                assistant,
                {
                    "role": "user",
                    "content": [tool_result_block("call_other", {}, success=True)],
                },
            ]
        )
    elif case == "duplicate_result":
        messages.extend([assistant, {"role": "user", "content": [result, result]}])
    elif case == "pending":
        messages.append(assistant)
    elif case == "reused":
        messages.extend(
            [
                assistant,
                {"role": "user", "content": [result]},
                assistant,
                {"role": "user", "content": [result]},
            ]
        )
    elif case == "wrong_role":
        messages.append({"role": "system", "content": [{"text": "private"}]})
    elif case == "mixed":
        messages.append({"role": "user", "content": [{"text": "hi", "toolResult": {}}]})
    elif case == "bad_status":
        cast(dict[str, object], result["toolResult"])["status"] = "unknown"
        messages.extend([assistant, {"role": "user", "content": [result]}])
    elif case == "bad_schema":
        cast(dict[str, object], tools[0]["toolSpec"])["inputSchema"] = {
            "json": {"type": "object", "required": ["missing"]}
        }
    elif case == "nested_keys":
        result = tool_result_block(
            "call_1", {"nested": {1: "a", "1": "b"}}, success=True
        )
        messages.extend([assistant, {"role": "user", "content": [result]}])
    else:
        tools.append(deepcopy(tools[0]))

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Network MUST NOT run")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(ValueError, match="Provider input is invalid") as raised:
            provider.converse("System", messages, tools)
    assert raised.value.__context__ is None


def test_provider_cannot_reuse_historical_call_id(tmp_path: Path) -> None:
    messages = _messages() + [
        {
            "role": "assistant",
            "content": [
                {"toolUse": {"toolUseId": "call_1", "name": "lookup", "input": {}}}
            ],
        },
        {"role": "user", "content": [tool_result_block("call_1", {}, success=True)]},
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response([_call()]))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable):
            provider.converse("System", messages, _tools())


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": []},
        {"type": "object", "properties": {"x": {"type": "unknown"}}},
        {"type": "object", "required": "x"},
        {"type": "object", "additionalProperties": "false"},
        {"type": "object", "$defs": []},
        {"type": "object", "properties": {"x": {"enum": "one"}}},
    ],
)
def test_invalid_typed_schemas_fail_before_network(
    tmp_path: Path, schema: dict[str, object]
) -> None:
    tools = _tools()
    cast(dict[str, object], tools[0]["toolSpec"])["inputSchema"] = {"json": schema}

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Network MUST NOT run")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(ValueError, match="Provider input is invalid"):
            provider.converse("System", _messages(), tools)


@pytest.mark.parametrize("case", ["blank_system", "empty_history", "bad_text"])
def test_invalid_base_input_fails_before_network(tmp_path: Path, case: str) -> None:
    system, messages = "System", _messages()
    if case == "blank_system":
        system = " "
    elif case == "empty_history":
        messages = []
    else:
        messages = [{"role": "user", "content": [{"text": 1}]}]

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Network MUST NOT run")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(ValueError, match="Provider input is invalid"):
            provider.converse(system, messages, [])


@pytest.mark.parametrize(
    "content", [b"", b" \n", b"bad\x00key", b"bad key", b"\xff", b"a" * 65537]
)
def test_invalid_key_files_are_generic(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "invalid-key"
    path.write_bytes(content)
    with pytest.raises(ProviderConfigurationError) as raised:
        OpenAIResponsesProvider(path)
    assert str(raised.value) == "Provider configuration is invalid"
    assert raised.value.__context__ is None
    assert str(path) not in repr(raised.value)


class _Stream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes], *, fail: bool = False) -> None:
        self.chunks = chunks
        self.fail = fail
        self.closed = False
        self.reads = 0

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.fail:
            raise httpx.ReadTimeout("TEST_ONLY_BODY_MARKER")

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
@pytest.mark.parametrize("size", [1024 * 1024, 1024 * 1024 + 1])
def test_shared_transport_caps_decoded_bytes_and_closes_streams(
    encoding: str, size: int
) -> None:
    content = b"x" * size
    if encoding == "gzip":
        content = gzip.compress(content)
    elif encoding == "deflate":
        content = zlib.compress(content)
    stream = _Stream([content])

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["connect"] == 5.0
        assert request.headers["accept-encoding"] == "gzip, deflate"
        return httpx.Response(
            201,
            stream=stream,
            headers={"Content-Encoding": encoding, "Cache-Control": "max-age=1"},
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        if size > http_client.MAX_RESPONSE_BYTES:
            with pytest.raises(http_client.ResponseTooLarge):
                http_client.request_bounded(client, "GET", "https://fake.invalid")
        else:
            result = http_client.request_bounded(client, "GET", "https://fake.invalid")
            assert result.content == b"x" * size
            assert result.status_code == 201
            assert result.headers["cache-control"] == "max-age=1"
            assert result.headers["content-encoding"] == encoding
            assert result.is_closed
    assert stream.closed


@pytest.mark.parametrize(
    ("encoding", "content", "fail"),
    [
        ("identity", b"partial", True),
        ("gzip", b"bad gzip", False),
        ("gzip", gzip.compress(b"text")[:-1], False),
        ("br", b"unsupported", False),
    ],
)
def test_shared_transport_closes_streams_on_read_and_decode_errors(
    encoding: str, content: bytes, fail: bool
) -> None:
    stream = _Stream([content], fail=fail)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, stream=stream, headers={"Content-Encoding": encoding}
            )
        )
    ) as client:
        with pytest.raises(httpx.RequestError):
            http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert stream.closed


@pytest.mark.parametrize("gzip_body", [False, True])
def test_oversized_model_response_is_static_and_never_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], gzip_body: bool
) -> None:
    content = b"x" * (http_client.MAX_RESPONSE_BYTES + 1)
    stream = _Stream([gzip.compress(content) if gzip_body else content, b"unread"])
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            stream=stream,
            headers={"Content-Encoding": "gzip" if gzip_body else "identity"},
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable) as raised:
            provider.converse("System", _messages(), [])
    assert raised.value.__context__ is None
    assert stream.closed and stream.reads == 1 and calls == 1
    line = _failure_line(capsys)
    assert line["exception"] == "ResponseTooLarge"


@pytest.mark.parametrize("field", ["system", "message", "tool"])
def test_serialized_model_input_limit_rejects_before_send(
    tmp_path: Path, field: str
) -> None:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=_response())

    system, messages, tools = "System", _messages(), _tools()
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        provider.converse(system, messages, tools)
        base_size = len(sent.pop().content)
        padding = "x" * (64 * 1024 - base_size)
        if field == "system":
            system += padding
        elif field == "message":
            messages[0]["content"] = [{"text": "Find sample prices." + padding}]
        else:
            cast(dict[str, object], tools[0]["toolSpec"])["description"] = (
                "Look up sample prices." + padding
            )
        provider.converse(system, messages, tools)
        assert len(sent.pop().content) == 64 * 1024
        with pytest.raises(ValueError, match="^Provider input is invalid$"):
            provider.converse(system + "x", messages, tools)
    assert sent == []


def test_serialized_model_input_counts_json_escaping(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("request sent")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(ValueError, match="^Provider input is invalid$"):
            provider.converse("\U0001f600" * 6000, _messages(), [])


@pytest.mark.parametrize("collection", ["output", "blocks"])
def test_model_response_collections_are_bounded(
    tmp_path: Path, collection: str
) -> None:
    response = _response([_text()] * 129)
    if collection == "blocks":
        response = _response(
            [{**_text(), "content": [{"type": "output_text", "text": "x"}] * 129}]
        )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response)
        )
    ) as client:
        provider = OpenAIResponsesProvider(_key_file(tmp_path), client=client)
        with pytest.raises(LLMUnavailable):
            provider.converse("System", _messages(), [])


@pytest.mark.parametrize("phase", ["headers", "drip", "stalled_body"])
def test_absolute_deadline_cancels_owned_transport_and_closes_stream(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    events: list[str] = []
    transport_options: dict[str, object] = {}

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            try:
                while True:
                    if phase == "stalled_body":
                        await asyncio.Event().wait()
                    await asyncio.sleep(0.005)
                    events.append("chunk")
                    yield b"x"
            finally:
                events.append("cancelled")

        async def aclose(self) -> None:
            events.append("closed")

    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["connect"] == 5.0
        events.append("sent")
        if phase == "headers":
            try:
                await asyncio.Event().wait()
            finally:
                events.append("cancelled")
        return httpx.Response(200, stream=SlowStream())

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        transport_options.update(kwargs)
        return httpx.MockTransport(handle)

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    monkeypatch.setattr(http_client, "REQUEST_SECONDS", 0.05)
    monkeypatch.setenv("HTTPS_PROXY", "http://ambient-proxy.invalid")
    started = time.monotonic()
    with http_client.build_http_client("https://fake.invalid") as client:
        with pytest.raises(httpx.ReadTimeout):
            http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert time.monotonic() - started < 2.0
    assert events.count("sent") == 1
    assert events.count("cancelled") == 1
    assert ("closed" in events) == (phase != "headers")
    if phase == "drip":
        assert "chunk" in events
    assert transport_options == {"retries": 0, "trust_env": False}


@pytest.mark.parametrize("phase", ["headers", "stalled_body", "drip"])
def test_network_deadline_closes_the_peer_socket(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    request_received = Event()
    peer_closed = Event()
    chunks: list[bool] = []
    monkeypatch.setattr(http_client, "REQUEST_SECONDS", 0.5)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2.0)
        port = listener.getsockname()[1]

        def serve() -> None:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2.0)
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = connection.recv(65536)
                    assert chunk
                    request += chunk
                assert request.startswith(b"GET / HTTP/1.1\r\n")
                request_received.set()
                if phase != "headers":
                    connection.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n"
                    )
                connection.settimeout(0.02)
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    try:
                        data = connection.recv(65536)
                    except TimeoutError:
                        if phase == "drip":
                            connection.sendall(b"x")
                            chunks.append(True)
                        continue
                    assert data == b""
                    peer_closed.set()
                    return
                raise AssertionError("The provider did not close the peer socket")

        with ThreadPoolExecutor(max_workers=1) as executor:
            server = executor.submit(serve)
            started = time.monotonic()
            with http_client.build_http_client(f"http://127.0.0.1:{port}") as client:
                with pytest.raises(httpx.ReadTimeout):
                    http_client.request_bounded(client, "GET", "/")
            assert time.monotonic() - started < 2.0
            server.result(timeout=2.0)
    assert request_received.is_set()
    assert peer_closed.is_set()
    assert bool(chunks) == (phase == "drip")
    assert not any(
        thread.name.startswith("provider-request") for thread in enumerate_threads()
    )


def test_absolute_deadline_cancels_connection_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    sockets: list[socket.socket] = []

    async def connect(
        loop: asyncio.BaseEventLoop, sock: socket.socket, address: object
    ) -> NoReturn:
        sockets.append(sock)
        events.append("connecting")
        try:
            await asyncio.Event().wait()
            raise AssertionError("Connection wait completed")
        finally:
            events.append("cancelled")

    def make_transport(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("A cancelled connection created a transport to send a request")

    monkeypatch.setattr(http_client._ResolverEventLoop, "sock_connect", connect)
    monkeypatch.setattr(
        http_client._ResolverEventLoop, "_make_socket_transport", make_transport
    )
    monkeypatch.setattr(http_client, "REQUEST_SECONDS", 0.1)
    started = time.monotonic()
    with http_client.build_http_client("https://127.0.0.1") as client:
        with pytest.raises(httpx.ReadTimeout):
            http_client.request_bounded(client, "GET", "/")
    assert time.monotonic() - started < 2.0
    assert events == ["connecting", "cancelled"]
    assert len(sockets) == 1
    assert sockets[0].fileno() == -1
    assert not any(
        thread.name.startswith("provider-request") for thread in enumerate_threads()
    )


def test_absolute_deadline_cancels_tls_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handshake_started = Event()
    peer_closed = Event()
    transports: list[asyncio.Transport] = []
    closed_before_loop_close: list[bool] = []
    make_transport = http_client._ResolverEventLoop._make_socket_transport  # type: ignore[attr-defined]  # noqa: SLF001
    close_loop = http_client._ResolverEventLoop.close

    def track_transport(*args: object, **kwargs: object) -> asyncio.Transport:
        transport = cast(asyncio.Transport, make_transport(*args, **kwargs))
        transports.append(transport)
        return transport

    def close(loop: http_client._ResolverEventLoop) -> None:
        closed_before_loop_close.extend(
            transport.get_extra_info("socket").fileno() == -1
            for transport in transports
        )
        close_loop(loop)

    monkeypatch.setattr(
        http_client._ResolverEventLoop, "_make_socket_transport", track_transport
    )
    monkeypatch.setattr(http_client._ResolverEventLoop, "close", close)
    monkeypatch.setattr(http_client, "REQUEST_SECONDS", 0.5)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2.0)
        port = listener.getsockname()[1]

        def serve() -> None:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2.0)
                hello = connection.recv(65536)
                assert hello.startswith(b"\x16")
                handshake_started.set()
                while connection.recv(65536):
                    pass
                peer_closed.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            server = executor.submit(serve)
            started = time.monotonic()
            with http_client.build_http_client(f"https://127.0.0.1:{port}") as client:
                with pytest.raises(httpx.ReadTimeout):
                    http_client.request_bounded(client, "GET", "/")
            assert time.monotonic() - started < 2.0
            server.result(timeout=2.0)
    assert handshake_started.is_set()
    assert peer_closed.is_set()
    assert len(transports) == 1
    assert closed_before_loop_close == [True]
    assert not any(
        thread.name.startswith("provider-request") for thread in enumerate_threads()
    )


def test_absolute_deadline_cancels_pool_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport_type = httpx.AsyncHTTPTransport

    def make_transport(**kwargs: object) -> httpx.AsyncHTTPTransport:
        assert kwargs == {"retries": 0, "trust_env": False}
        return transport_type(
            limits=httpx.Limits(max_connections=0), retries=0, trust_env=False
        )

    async def connect(
        loop: asyncio.BaseEventLoop, sock: socket.socket, address: object
    ) -> NoReturn:
        pytest.fail("Pool wait opened a connection")

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    monkeypatch.setattr(http_client._ResolverEventLoop, "sock_connect", connect)
    monkeypatch.setattr(http_client, "REQUEST_SECONDS", 0.1)
    started = time.monotonic()
    with http_client.build_http_client("https://127.0.0.1") as client:
        with pytest.raises(httpx.ReadTimeout):
            http_client.request_bounded(client, "GET", "/")
    assert time.monotonic() - started < 2.0
    assert not any(
        thread.name.startswith("provider-request") for thread in enumerate_threads()
    )


def test_timed_out_dns_calls_share_a_fixed_worker_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = Event()
    saturated = Event()
    resolved = Event()
    recovering = Event()
    lock = Lock()
    resolver_threads: list[Thread] = []
    deadlines: dict[asyncio.AbstractEventLoop, asyncio.Timeout] = {}
    connections: list[bool] = []
    submissions: list[Future[object]] = []
    completed = 0
    workers = http_client.DNS_WORKERS
    existing_threads = set(enumerate_threads())
    assert http_client._resolver_executor._max_workers == workers  # noqa: SLF001
    resolver_pool = ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="provider-dns-test"
    )
    callers = ThreadPoolExecutor(max_workers=workers * 2)
    submit_resolver = resolver_pool.submit
    timeout_factory = asyncio.timeout
    connect_socket = http_client._ResolverEventLoop.sock_connect

    def timeout(delay: float | None) -> asyncio.Timeout:
        context = timeout_factory(delay)
        with lock:
            deadlines[asyncio.get_running_loop()] = context
        return context

    def submit(
        function: Callable[..., object], /, *args: object, **kwargs: object
    ) -> Future[object]:
        with lock:
            future = submit_resolver(function, *args, **kwargs)
            submissions.append(future)
        return future

    def resolver_done(future: Future[object]) -> None:
        nonlocal completed
        with lock:
            completed += 1
            if completed == workers:
                resolved.set()

    def resolve(
        host: object, port: object, *args: object, **kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        assert host in ("blocked.invalid", b"blocked.invalid")
        assert isinstance(port, int)
        with lock:
            resolver_threads.append(current_thread())
            if len(resolver_threads) == workers:
                saturated.set()
        if not release.wait(10.0):
            raise AssertionError("Resolver was not released")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    async def connect(
        loop: asyncio.BaseEventLoop, sock: socket.socket, address: tuple[str, int]
    ) -> None:
        connections.append(True)
        assert recovering.is_set(), "A timed-out resolver resumed a provider request"
        await connect_socket(loop, sock, address)

    def invoke(error: type[httpx.RequestError] = httpx.ReadTimeout) -> None:
        with http_client.build_http_client("https://blocked.invalid") as client:
            with pytest.raises(error):
                http_client.request_bounded(client, "GET", "/")

    def assert_worker_bound() -> None:
        with lock:
            assert len(resolver_threads) == workers
            assert len(set(resolver_threads)) == workers
            assert all(thread.is_alive() for thread in resolver_threads)
            assert len(submissions) == workers
            assert all(future.running() for future in submissions)
        assert resolver_pool._work_queue.qsize() == 0  # noqa: SLF001
        assert (
            sum(
                (
                    thread.name.startswith("provider-dns")
                    or thread.name.startswith("asyncio_")
                )
                for thread in enumerate_threads()
                if thread not in existing_threads
            )
            == workers
        )

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(http_client.asyncio, "timeout", timeout)
    monkeypatch.setattr(http_client, "_resolver_executor", resolver_pool)
    monkeypatch.setattr(resolver_pool, "submit", submit)
    monkeypatch.setattr(http_client._ResolverEventLoop, "sock_connect", connect)
    try:
        initial = [callers.submit(invoke) for _ in range(workers)]
        assert saturated.wait(5.0)
        assert_worker_bound()
        with lock:
            initial_deadlines = list(deadlines.items())
        for loop, context in initial_deadlines:
            loop.call_soon_threadsafe(context.reschedule, loop.time())
        for call in initial:
            call.result(timeout=2.0)

        concurrent = [
            callers.submit(invoke, httpx.ConnectError) for _ in range(workers * 2)
        ]
        for call in concurrent:
            call.result(timeout=2.0)
        assert_worker_bound()
        for _ in range(workers * 2):
            started = time.monotonic()
            invoke(httpx.ConnectError)
            assert time.monotonic() - started < 2.0
            assert_worker_bound()
        assert not any(
            thread.name.startswith("provider-request") for thread in enumerate_threads()
        )
        for future in submissions:
            future.add_done_callback(resolver_done)
        release.set()
        assert resolved.wait(2.0)
        assert connections == []
        recovering.set()
        monkeypatch.setattr(http_client, "REQUEST_SECONDS", 1.0)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(2.0)
            port = listener.getsockname()[1]

            def serve() -> bytes:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2.0)
                    request = b""
                    while b"\r\n\r\n" not in request:
                        chunk = connection.recv(65536)
                        assert chunk
                        request += chunk
                    connection.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
                    )
                    assert connection.recv(1) == b""
                    return request

            server = callers.submit(serve)
            with http_client.build_http_client(
                f"http://blocked.invalid:{port}"
            ) as client:
                assert http_client.request_bounded(client, "GET", "/").content == b"ok"
            assert server.result(timeout=2.0).startswith(b"GET / HTTP/1.1\r\n")
        assert len(connections) == 1
        assert len(submissions) == workers + 1
    finally:
        release.set()
        callers.shutdown(wait=True, cancel_futures=True)
        resolver_pool.shutdown(wait=True, cancel_futures=True)
        for thread in resolver_threads:
            thread.join(timeout=2.0)
            assert not thread.is_alive()
    assert len(resolver_threads) == workers + 1
    assert len(set(resolver_threads)) == workers
    assert not any(
        thread.name.startswith("provider-request") for thread in enumerate_threads()
    )


def test_fake_slow_drip_obeys_the_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    closed: list[bool] = []

    class Drip(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            for _ in range(100):
                now[0] += 1.0
                yield b"x"

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(http_client.time, "monotonic", lambda: now[0])
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Drip())
        )
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert now[0] == 45.0
    assert closed == [True]


@pytest.mark.parametrize("oversize", [False, True])
def test_owned_transport_bounds_compressed_bodies_and_closes_async_streams(
    monkeypatch: pytest.MonkeyPatch, oversize: bool
) -> None:
    closed: list[bool] = []
    size = http_client.MAX_RESPONSE_BYTES + int(oversize)
    compressed = gzip.compress(b"x" * size)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for start in range(0, len(compressed), 17):
                yield compressed[start : start + 17]

        async def aclose(self) -> None:
            closed.append(True)

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=Stream(), headers={"Content-Encoding": "gzip"}
        )

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncHTTPTransport",
        make_transport,
    )

    async def invoke() -> None:
        with http_client.build_http_client("https://fake.invalid") as client:
            if oversize:
                with pytest.raises(http_client.ResponseTooLarge):
                    http_client.request_bounded(client, "GET", "https://fake.invalid")
            else:
                result = http_client.request_bounded(
                    client, "GET", "https://fake.invalid"
                )
                assert result.content == b"x" * size

    asyncio.run(invoke())
    assert closed == [True]


def test_owned_transport_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(307, headers={"Location": "https://other.invalid"})

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setattr(
        http_client.httpx,
        "AsyncHTTPTransport",
        make_transport,
    )
    with http_client.build_http_client("https://fake.invalid") as client:
        client.follow_redirects = True
        result = http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert result.status_code == 307
    assert seen == ["fake.invalid"]


@pytest.mark.parametrize("kind", ["custom", "network", "fake_subclass"])
def test_unsupported_injected_transport_is_rejected_before_send(kind: str) -> None:
    seen: list[httpx.Request] = []

    class Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    class FakeSubclass(httpx.MockTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    transport: httpx.BaseTransport
    if kind == "custom":
        transport = Transport()
    elif kind == "network":
        transport = httpx.HTTPTransport()
    else:
        transport = FakeSubclass(lambda request: httpx.Response(200))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectError):
            http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert seen == []


@pytest.mark.parametrize("mount_kind", ["none", "fake", "network"])
def test_transport_contract_checks_every_mount(mount_kind: str) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, content=b"ok")

    mount: httpx.BaseTransport | None = None
    if mount_kind == "network":
        mount = httpx.HTTPTransport()
    elif mount_kind == "fake":
        mount = httpx.MockTransport(handle)
    with httpx.Client(
        base_url="https://fake.invalid",
        transport=httpx.MockTransport(handle),
        mounts={"https://mounted.invalid": mount},
    ) as client:
        if mount_kind == "network":
            with pytest.raises(httpx.ConnectError):
                http_client.request_bounded(client, "GET", "/")
            with pytest.raises(httpx.ConnectError):
                http_client.request_bounded(client, "GET", "https://mounted.invalid")
        else:
            assert http_client.request_bounded(client, "GET", "/").content == b"ok"
            assert (
                http_client.request_bounded(
                    client, "GET", "https://mounted.invalid"
                ).content
                == b"ok"
            )
    assert seen == (
        [] if mount_kind == "network" else ["fake.invalid", "mounted.invalid"]
    )


def test_httpx_private_transport_contract_version() -> None:
    assert httpx.__version__ == "0.28.1"
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    with httpx.Client(
        transport=transport,
        mounts={"https://mounted.invalid": None},
        trust_env=False,
    ) as client:
        assert client._transport is transport  # noqa: SLF001
        assert type(client._mounts) is dict  # noqa: SLF001
        assert list(client._mounts.values()) == [None]  # noqa: SLF001


def test_unsupported_httpx_version_is_rejected_before_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(http_client.httpx, "__version__", "unsupported")
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.ConnectError):
            http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert seen == []


def test_client_subclass_is_rejected_before_send() -> None:
    seen: list[httpx.Request] = []

    class Client(httpx.Client):
        def send(
            self, request: httpx.Request, *args: object, **kwargs: object
        ) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    with Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    ) as client:
        with pytest.raises(httpx.ConnectError):
            http_client.request_bounded(client, "GET", "https://fake.invalid")
    assert seen == []


def test_key_file_must_be_a_scoped_regular_file(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(_key_file(tmp_path))
    for path in (tmp_path / "missing", tmp_path, link):
        with pytest.raises(ProviderConfigurationError):
            OpenAIResponsesProvider(path)


def test_arbitrary_region_is_rejected_before_file_access(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigurationError):
        OpenAIResponsesProvider(
            tmp_path / "missing",
            region="https://other.invalid",  # type: ignore[arg-type]
        )
