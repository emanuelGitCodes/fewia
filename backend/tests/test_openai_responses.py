import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Literal, cast

import httpx
import pytest

from app.agent.chat_messages import parse_provider_response, tool_result_block
from app.agent.provider import LLMUnavailable
from app.provider_settings import ProviderConfigurationError
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
    assert (timeout.connect, timeout.read) == (3, 40)


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
