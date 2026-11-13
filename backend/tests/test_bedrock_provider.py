import asyncio
import gzip
import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from botocore.awsrequest import AWSPreparedRequest
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.httpsession import URLLib3Session

from app.agent.provider import LLMUnavailable
from app.providers import bedrock, http_client


class FakeEvents:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[..., object]] = {}

    def register_first(self, event: str, handler: Callable[..., object]) -> None:
        self.handlers[event] = handler


class FakeClient:
    def __init__(self, response: object) -> None:
        self.meta = SimpleNamespace(events=FakeEvents())
        self.response = response
        self.requests: list[dict[str, object]] = []

    def converse(self, **kwargs: object) -> dict[str, object]:
        self.requests.append(kwargs)
        if isinstance(self.response, BaseException):
            raise self.response
        return cast(dict[str, object], self.response)


class FakeSession:
    def __init__(self, client: FakeClient) -> None:
        self.client_instance = client
        self.session_kwargs: dict[str, object] | None = None
        self.client_kwargs: dict[str, object] | None = None

    def client(self, service_name: str, **kwargs: object) -> FakeClient:
        assert service_name == "bedrock-runtime"
        self.client_kwargs = kwargs
        return self.client_instance


def install_session(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    def factory(**kwargs: object) -> FakeSession:
        session.session_kwargs = kwargs
        return session

    monkeypatch.setattr(bedrock.boto3, "Session", factory)


def response() -> dict[str, object]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
        "stopReason": "end_turn",
    }


_LUNA_US_ID = "us.openai.gpt-6-luna"
_LUNA_US_ARN = (
    "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.openai.gpt-6-luna"
)
_NOVA2_US_ID = "us.amazon.nova-2-lite-v1:0"
_NOVA2_US_ARN = (
    "arn:aws:bedrock:us-east-1:123456789012:inference-profile/"
    "us.amazon.nova-2-lite-v1:0"
)
_NOVA2_FIELDS = {
    "reasoningConfig": {"type": "enabled", "maxReasoningEffort": "low"},
}


def provider(
    monkeypatch: pytest.MonkeyPatch,
    result: object,
    profile_name: str | None = None,
    model_id: str = "model-id",
) -> tuple[bedrock.BedrockConverseProvider, FakeSession, FakeClient]:
    client = FakeClient(result)
    session = FakeSession(client)
    install_session(monkeypatch, session)
    instance = bedrock.BedrockConverseProvider(model_id, profile_name=profile_name)
    return instance, session, client


def test_uses_explicit_real_endpoint_and_bounded_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://floci:4566")
    instance, session, _ = provider(monkeypatch, response())

    assert instance is not None
    assert session.session_kwargs == {}
    assert session.client_kwargs is not None
    assert session.client_kwargs["endpoint_url"] == (
        "https://bedrock-runtime.us-east-1.amazonaws.com"
    )
    assert "aws_access_key_id" not in session.session_kwargs
    assert "aws_secret_access_key" not in session.session_kwargs
    config = cast(Config, session.client_kwargs["config"])
    assert config.connect_timeout == 3
    assert config.read_timeout == 40
    assert config.retries["total_max_attempts"] == 1


def test_forwards_profile_without_dummy_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, session, _ = provider(monkeypatch, response(), profile_name="dev")

    assert session.session_kwargs == {"profile_name": "dev"}


def test_forwards_shape_and_omits_empty_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, client = provider(monkeypatch, response())
    messages = [{"role": "user", "content": [{"text": "hello"}]}]

    result = instance.converse("system", messages, [])

    assert result == response()
    assert client.requests == [
        {
            "modelId": "model-id",
            "system": [{"text": "system"}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0},
            "performanceConfig": {"latency": "standard"},
            "serviceTier": {"type": "default"},
        }
    ]


@pytest.mark.parametrize(
    ("latency", "tier"), [("standard", "default"), ("optimized", "priority")]
)
def test_selects_standard_default_and_preserves_reported_tiers(
    monkeypatch: pytest.MonkeyPatch, latency: str, tier: str
) -> None:
    reply = {
        **response(),
        "performanceConfig": {"latency": latency},
        "serviceTier": {"type": tier},
    }
    instance, _, client = provider(monkeypatch, reply, model_id=_NOVA2_US_ID)

    result = instance.converse("system", _USER_MESSAGES, [])

    assert client.requests[0]["performanceConfig"] == {"latency": "standard"}
    assert client.requests[0]["serviceTier"] == {"type": "default"}
    assert result is reply
    assert result["performanceConfig"] == {"latency": latency}
    assert result["serviceTier"] == {"type": tier}


def test_includes_nonempty_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    instance, _, client = provider(monkeypatch, response())
    tools = [{"toolSpec": {"name": "get_context"}}]

    instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], tools)

    assert client.requests[0]["toolConfig"] == {"tools": tools}
    assert "additionalModelRequestFields" not in client.requests[0]


@pytest.mark.parametrize("model_id", [_LUNA_US_ID, _LUNA_US_ARN])
def test_luna_low_effort_omits_temperature_and_bounds_tokens(
    monkeypatch: pytest.MonkeyPatch, model_id: str
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=model_id)
    messages = [{"role": "user", "content": [{"text": "hello"}]}]

    instance.converse("system", messages, [])

    request = client.requests[0]
    assert request["modelId"] == model_id
    assert request["inferenceConfig"] == {"maxTokens": 4096}
    assert "temperature" not in request["inferenceConfig"]
    assert request["additionalModelRequestFields"] == {"reasoning_effort": "low"}
    assert "toolConfig" not in request


def test_luna_forwards_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=_LUNA_US_ID)
    tools = [{"toolSpec": {"name": "get_context"}}]

    instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], tools)

    request = client.requests[0]
    assert request["toolConfig"] == {"tools": tools}
    assert request["additionalModelRequestFields"] == {"reasoning_effort": "low"}
    assert request["inferenceConfig"] == {"maxTokens": 4096}


@pytest.mark.parametrize(
    "model_id",
    [
        "openai.gpt-6-luna",
        "global.openai.gpt-6-luna",
        "us.openai.gpt-6-luna-extra",
    ],
)
def test_non_us_luna_identifiers_keep_default_inference(
    monkeypatch: pytest.MonkeyPatch, model_id: str
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=model_id)

    instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    request = client.requests[0]
    assert request["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0}
    assert "additionalModelRequestFields" not in request


@pytest.mark.parametrize("model_id", [_NOVA2_US_ID, _NOVA2_US_ARN])
def test_nova2_low_effort_sets_tokens_temperature_and_reasoning_config(
    monkeypatch: pytest.MonkeyPatch, model_id: str
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=model_id)
    messages = [{"role": "user", "content": [{"text": "hello"}]}]

    instance.converse("system", messages, [])

    request = client.requests[0]
    extra = request["additionalModelRequestFields"]
    assert request["modelId"] == model_id
    assert request["inferenceConfig"] == {"maxTokens": 4096, "temperature": 0}
    assert extra == _NOVA2_FIELDS
    assert "reasoning_effort" not in extra
    assert "toolConfig" not in request


_TOOL_RESULT = {"toolResult": {"toolUseId": "t1", "content": [{"text": "r"}]}}


@pytest.mark.parametrize(
    ("content", "reasoning"),
    [
        ([{"text": "hello"}], True),
        ([_TOOL_RESULT], False),
        ([{"text": "note"}, _TOOL_RESULT], False),
    ],
)
def test_nova2_reasoning_only_when_not_answering_tool_results(
    monkeypatch: pytest.MonkeyPatch, content: list[object], reasoning: bool
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=_NOVA2_US_ID)
    messages = [
        {"role": "user", "content": [{"text": "hi"}]},
        {"role": "assistant", "content": [{"toolUse": {"name": "x"}}]},
        {"role": "user", "content": content},
    ]

    instance.converse("system", messages, [])

    request = client.requests[0]
    if reasoning:
        assert request["additionalModelRequestFields"] == _NOVA2_FIELDS
    else:
        assert "additionalModelRequestFields" not in request


def test_luna_keeps_reasoning_on_tool_result_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=_LUNA_US_ID)

    instance.converse("system", [{"role": "user", "content": [_TOOL_RESULT]}], [])

    extra = client.requests[0]["additionalModelRequestFields"]
    assert extra == {"reasoning_effort": "low"}


@pytest.mark.parametrize("cache", [False, True])
def test_prompt_cache_point_follows_setting(
    monkeypatch: pytest.MonkeyPatch, cache: bool
) -> None:
    client = FakeClient(response())
    install_session(monkeypatch, FakeSession(client))
    instance = bedrock.BedrockConverseProvider("model-id", prompt_cache=cache)

    instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    expected: list[dict[str, object]] = [{"text": "system"}]
    if cache:
        expected.append({"cachePoint": {"type": "default"}})
    assert client.requests[0]["system"] == expected


def test_nova2_forwards_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=_NOVA2_US_ID)
    tools = [{"toolSpec": {"name": "get_context"}}]

    instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], tools)

    request = client.requests[0]
    extra = request["additionalModelRequestFields"]
    assert request["toolConfig"] == {"tools": tools}
    assert extra == _NOVA2_FIELDS
    assert "reasoning_effort" not in extra
    assert request["inferenceConfig"] == {"maxTokens": 4096, "temperature": 0}


@pytest.mark.parametrize(
    "model_id",
    [
        "amazon.nova-2-lite-v1:0",
        "global.amazon.nova-2-lite-v1:0",
        "us.amazon.nova-2-lite-v1:0-extra",
        "us.amazon.nova-2-lite-v1",
        "eu.amazon.nova-2-lite-v1:0",
    ],
)
def test_non_us_nova2_identifiers_keep_default_inference(
    monkeypatch: pytest.MonkeyPatch, model_id: str
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=model_id)

    instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    request = client.requests[0]
    assert request["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0}
    assert "additionalModelRequestFields" not in request


_NOVA2_PRO_ID = "us.amazon.nova-2-pro-v1:0"
_NOVA2_PRO_ARN = (
    "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.amazon.nova-2-pro-v1:0"
)
_CLAUDE_ID = "us.anthropic.claude-haiku-5-5"
_CLAUDE_ARN = (
    "arn:aws:bedrock:us-east-1:123456789012:inference-profile/"
    "us.anthropic.claude-haiku-5-5"
)


@pytest.mark.parametrize("model_id", [_NOVA2_PRO_ID, _NOVA2_PRO_ARN])
def test_nova2_pro_gets_nova_fields_and_tool_result_rule(
    monkeypatch: pytest.MonkeyPatch, model_id: str
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=model_id)
    tools = [{"toolSpec": {"name": "get_context"}}]

    instance.converse("system", [{"role": "user", "content": [{"text": "hi"}]}], tools)
    instance.converse("system", [{"role": "user", "content": [_TOOL_RESULT]}], tools)

    first, second = client.requests
    assert first["modelId"] == model_id
    assert first["inferenceConfig"] == {"maxTokens": 4096, "temperature": 0}
    assert first["additionalModelRequestFields"] == _NOVA2_FIELDS
    assert first["toolConfig"] == {"tools": tools}
    assert "additionalModelRequestFields" not in second


@pytest.mark.parametrize("model_id", [_CLAUDE_ID, _CLAUDE_ARN])
@pytest.mark.parametrize("cache", [False, True])
def test_claude_omits_temperature_and_nova_fields_but_keeps_tools(
    monkeypatch: pytest.MonkeyPatch, model_id: str, cache: bool
) -> None:
    client = FakeClient(response())
    install_session(monkeypatch, FakeSession(client))
    instance = bedrock.BedrockConverseProvider(model_id, prompt_cache=cache)
    tools = [{"toolSpec": {"name": "get_context"}}]

    instance.converse("system", [{"role": "user", "content": [{"text": "hi"}]}], tools)

    request = client.requests[0]
    system: list[dict[str, object]] = [{"text": "system"}]
    if cache:
        system.append({"cachePoint": {"type": "default"}})
    assert request["modelId"] == model_id
    assert request["inferenceConfig"] == {"maxTokens": 4096}
    assert "additionalModelRequestFields" not in request
    assert request["toolConfig"] == {"tools": tools}
    assert request["system"] == system


@pytest.mark.parametrize(
    "model_id",
    [
        "anthropic.claude-haiku-5-5",
        "global.anthropic.claude-haiku-5-5",
        "us.anthropic.claude-haiku-5-5-extra",
        "us.amazon.nova-2-pro-v1",
        "eu.amazon.nova-2-pro-v1:0",
    ],
)
def test_other_claude_and_pro_identifiers_keep_default_inference(
    monkeypatch: pytest.MonkeyPatch, model_id: str
) -> None:
    instance, _, client = provider(monkeypatch, response(), model_id=model_id)

    instance.converse("system", _USER_MESSAGES, [])

    request = client.requests[0]
    assert request["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0}
    assert "additionalModelRequestFields" not in request


@pytest.mark.parametrize(
    "bad_messages",
    [
        [{}],
        [{"content": [{"text": "hello"}]}],
        [{"role": "system", "content": [{"text": "hello"}]}],
        [{"role": "user", "content": []}],
        [{"role": "user", "content": [{}]}],
        [{"role": "user", "content": [123]}],
        [{"role": "user", "content": [{"text": 1}]}],
        [{"role": "user", "content": [{"toolUse": []}]}],
        [{"role": "user", "content": [{"guardContent": "text"}]}],
    ],
)
def test_rejects_invalid_messages_before_client(
    monkeypatch: pytest.MonkeyPatch, bad_messages: object
) -> None:
    instance, _, client = provider(monkeypatch, response())

    with pytest.raises(ValueError):
        instance.converse("system", cast(list[dict[str, object]], bad_messages), [])

    assert client.requests == []


def test_preserves_tool_result_and_extra_content_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, client = provider(monkeypatch, response())
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "toolUse": {
                        "toolUseId": "call-1",
                        "name": "get_context",
                        "input": {},
                    }
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"toolResult": {"toolUseId": "call-1", "content": [{"text": "ok"}]}},
                {"guardContent": {"text": {"text": "safe"}}},
            ],
        },
    ]

    instance.converse("system", messages, [])

    assert client.requests[0]["messages"] == messages


_GUARDRAIL = ("abc123def456", "2")
_GUARDRAIL_CONFIG = {
    "guardrailIdentifier": "abc123def456",
    "guardrailVersion": "2",
    "trace": "disabled",
}


def guarded_provider(
    monkeypatch: pytest.MonkeyPatch, model_id: str = "model-id"
) -> tuple[bedrock.BedrockConverseProvider, FakeClient]:
    client = FakeClient(response())
    install_session(monkeypatch, FakeSession(client))
    instance = bedrock.BedrockConverseProvider(model_id, guardrail=_GUARDRAIL)
    return instance, client


def test_no_guardrail_leaves_the_request_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, client = provider(monkeypatch, response())
    messages = [{"role": "user", "content": [{"text": "ctx"}, {"text": "hello"}]}]

    instance.converse("system", messages, [{"toolSpec": {"name": "t"}}])

    request = client.requests[0]
    assert "guardrailConfig" not in request
    assert request["messages"] == messages
    assert "guardContent" not in json.dumps(request)


def test_guardrail_adds_config_and_wraps_only_the_latest_user_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, client = guarded_provider(monkeypatch)
    earlier = {"role": "user", "content": [{"text": "earlier question"}]}
    reply = {"role": "assistant", "content": [{"text": "earlier answer"}]}
    latest = {"role": "user", "content": [{"text": "ctx"}, {"text": "hello"}]}
    messages = [earlier, reply, latest]

    instance.converse("system", messages, [])

    request = client.requests[0]
    assert request["guardrailConfig"] == _GUARDRAIL_CONFIG
    assert request["messages"] == [
        earlier,
        reply,
        {
            "role": "user",
            "content": [
                {"text": "ctx"},
                {"guardContent": {"text": {"text": "hello"}}},
            ],
        },
    ]
    sent = cast(list[dict[str, object]], request["messages"])
    context_block = cast(list[object], sent[2]["content"])[0]
    assert "guardContent" not in json.dumps(context_block)
    assert latest["content"] == [{"text": "ctx"}, {"text": "hello"}]


def test_guardrail_skips_tool_result_messages_to_find_user_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, client = guarded_provider(monkeypatch)
    call = {"toolUse": {"toolUseId": "c1", "name": "t", "input": {}}}
    result = {"toolResult": {"toolUseId": "c1", "content": [{"text": "tool out"}]}}
    messages = [
        {"role": "user", "content": [{"text": "hello"}]},
        {"role": "assistant", "content": [call]},
        {"role": "user", "content": [result]},
    ]

    instance.converse("system", messages, [])

    sent = cast(list[dict[str, object]], client.requests[0]["messages"])
    assert sent[0]["content"] == [{"guardContent": {"text": {"text": "hello"}}}]
    assert sent[1:] == messages[1:]
    assert "tool out" in json.dumps(sent[2])
    assert client.requests[0]["guardrailConfig"] == _GUARDRAIL_CONFIG


def test_guardrail_without_user_text_still_sends_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, client = guarded_provider(monkeypatch)
    messages = [{"role": "user", "content": [_TOOL_RESULT]}]

    instance.converse("system", messages, [])

    assert client.requests[0]["messages"] == messages
    assert client.requests[0]["guardrailConfig"] == _GUARDRAIL_CONFIG


def test_guardrail_keeps_nova_reasoning_rule_on_original_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, client = guarded_provider(monkeypatch, model_id=_NOVA2_US_ID)

    instance.converse("system", [{"role": "user", "content": [{"text": "hi"}]}], [])

    assert client.requests[0]["additionalModelRequestFields"] == _NOVA2_FIELDS


def test_guardrail_intervention_response_is_returned_and_not_logged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    blocked = {
        "stopReason": "guardrail_intervened",
        "output": {"message": {"role": "assistant", "content": [{"text": "x"}]}},
    }
    client = FakeClient(blocked)
    install_session(monkeypatch, FakeSession(client))
    instance = bedrock.BedrockConverseProvider("model-id", guardrail=_GUARDRAIL)

    result = instance.converse(
        "system", [{"role": "user", "content": [{"text": "private words"}]}], []
    )

    assert result == blocked
    assert capsys.readouterr().err == ""


def test_guardrail_failure_line_holds_no_id_or_user_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeClient(client_error("ValidationException", 400, "abc123def456"))
    install_session(monkeypatch, FakeSession(client))
    instance = bedrock.BedrockConverseProvider("model-id", guardrail=_GUARDRAIL)

    with pytest.raises(LLMUnavailable):
        instance.converse(
            "system", [{"role": "user", "content": [{"text": "private words"}]}], []
        )

    err = capsys.readouterr().err
    assert "abc123def456" not in err
    assert "private words" not in err


@pytest.mark.parametrize(
    "bad_message",
    [
        {"role": "user", "content": [{"text": "ok"}]},
        {"content": [{"text": "ok"}]},
        {"role": "assistant"},
        {"role": "assistant", "content": []},
        {"role": "assistant", "content": [{}]},
        {"role": "assistant", "content": [123]},
        {"role": "assistant", "content": [{"text": 1}]},
        {"role": "assistant", "content": [{"toolUse": []}]},
    ],
)
def test_rejects_invalid_output_message(
    monkeypatch: pytest.MonkeyPatch, bad_message: object
) -> None:
    instance, _, _ = provider(
        monkeypatch,
        {"stopReason": "end_turn", "output": {"message": bad_message}},
    )

    with pytest.raises(LLMUnavailable) as error:
        instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    assert str(error.value) == ""


@pytest.mark.parametrize("stop_reason", ["invented", "", 1])
def test_rejects_unsupported_stop_reason(
    monkeypatch: pytest.MonkeyPatch, stop_reason: object
) -> None:
    instance, _, _ = provider(
        monkeypatch,
        {"stopReason": stop_reason, "output": {"message": response()["output"]}},
    )

    with pytest.raises(LLMUnavailable) as error:
        instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    assert str(error.value) == ""


@pytest.mark.parametrize(
    "stop_reason",
    [
        "end_turn",
        "tool_use",
        "max_tokens",
        "stop_sequence",
        "guardrail_intervened",
        "content_filtered",
        "model_context_window_exceeded",
    ],
)
def test_accepts_supported_stop_reasons(
    monkeypatch: pytest.MonkeyPatch, stop_reason: str
) -> None:
    tool_use = {
        "toolUse": {
            "toolUseId": "call-1",
            "name": "get_context",
            "input": {},
        }
    }
    expected = {
        "stopReason": stop_reason,
        "output": {"message": {"role": "assistant", "content": [tool_use]}},
    }
    instance, _, _ = provider(monkeypatch, expected)

    assert (
        instance.converse(
            "system", [{"role": "user", "content": [{"text": "hello"}]}], []
        )
        == expected
    )


@pytest.mark.parametrize(
    "bad_response",
    [
        {},
        {"stopReason": "end_turn"},
        {"stopReason": "end_turn", "output": {}},
        {"stopReason": 1, "output": {"message": {"content": []}}},
    ],
)
def test_malformed_response_is_static_unavailable(
    monkeypatch: pytest.MonkeyPatch, bad_response: object
) -> None:
    instance, _, _ = provider(monkeypatch, bad_response)

    with pytest.raises(LLMUnavailable) as error:
        instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    assert str(error.value) == ""


def test_provider_error_is_static_and_hides_original_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, _ = provider(monkeypatch, RuntimeError("secret-provider-detail"))

    with pytest.raises(LLMUnavailable) as error:
        instance.converse("system", [{"role": "user", "content": [{"text": "ok"}]}], [])

    assert str(error.value) == ""
    assert "secret-provider-detail" not in str(error.value)


_USER_MESSAGES = [{"role": "user", "content": [{"text": "ok"}]}]


def failure_line(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    return cast(dict[str, object], json.loads(lines[0]))


def client_error(code: str, status: int, message: str = "msg") -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "Converse",
    )


def test_logs_client_error_code_and_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance, _, _ = provider(monkeypatch, client_error("ExpiredTokenException", 403))

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    assert failure_line(capsys) == {
        "event": "bedrock_converse_failed",
        "reason": "client_error",
        "exception": "ClientError",
        "error_code": "ExpiredTokenException",
        "http_status": 403,
        "stop_reason": None,
    }


def test_overlong_error_code_is_not_logged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance, _, _ = provider(monkeypatch, client_error("x" * 65, 400))

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    line = failure_line(capsys)
    assert line["error_code"] is None
    assert line["http_status"] == 400


def test_logs_plain_exception_without_code_or_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance, _, _ = provider(monkeypatch, RuntimeError("boom"))

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    line = failure_line(capsys)
    assert line["reason"] == "client_error"
    assert line["exception"] == "RuntimeError"
    assert line["error_code"] is None
    assert line["http_status"] is None


@pytest.mark.parametrize(
    "bad_response",
    [
        "text",
        {"Error": "x", "ResponseMetadata": []},
        {"Error": {"Code": 5}, "ResponseMetadata": {"HTTPStatusCode": "403"}},
    ],
)
def test_malformed_exception_response_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_response: object,
) -> None:
    error = RuntimeError("boom")
    error.response = bad_response  # type: ignore[attr-defined]
    instance, _, _ = provider(monkeypatch, error)

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    line = failure_line(capsys)
    assert line["error_code"] is None
    assert line["http_status"] is None


@pytest.mark.parametrize("bad_response", ["nope", {"stopReason": "end_turn"}])
def test_logs_unexpected_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_response: object,
) -> None:
    instance, _, _ = provider(monkeypatch, bad_response)

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    line = failure_line(capsys)
    assert line["reason"] == "unexpected_response"
    assert line["exception"] is None


def test_logs_unsupported_stop_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance, _, _ = provider(
        monkeypatch, {"stopReason": "invented", "output": response()["output"]}
    )

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    line = failure_line(capsys)
    assert line["reason"] == "unsupported_stop_reason"
    assert line["stop_reason"] == "invented"


def test_overlong_stop_reason_is_not_logged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance, _, _ = provider(
        monkeypatch, {"stopReason": "x" * 65, "output": response()["output"]}
    )

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    assert failure_line(capsys)["stop_reason"] is None


def test_logs_invalid_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance, _, _ = provider(
        monkeypatch,
        {"stopReason": "end_turn", "output": {"message": {"role": "user"}}},
    )

    with pytest.raises(LLMUnavailable):
        instance.converse("system", _USER_MESSAGES, [])

    line = failure_line(capsys)
    assert line["reason"] == "invalid_message"
    assert line["stop_reason"] == "end_turn"


def test_failure_line_has_no_secrets_or_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/secret"
    message = f"Invalid request for account 123456789012 and {arn}"
    instance, _, _ = provider(
        monkeypatch,
        client_error("ValidationException", 400, message),
        model_id="secret-model-id",
    )

    with pytest.raises(LLMUnavailable):
        instance.converse("secret-system-prompt", _USER_MESSAGES, [])

    err = capsys.readouterr().err
    for secret in (message, arn, "123456789012", "secret-model-id", "us-east-1"):
        assert secret not in err
    assert "secret-system-prompt" not in err
    assert json.loads(err)["error_code"] == "ValidationException"


def test_rejects_invalid_model_region_and_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError):
        bedrock.BedrockConverseProvider(" ")
    with pytest.raises(ValueError):
        bedrock.BedrockConverseProvider("model", region="eu-west-1")
    instance, _, _ = provider(monkeypatch, response())
    with pytest.raises(ValueError):
        instance.converse("system", [], [])
    with pytest.raises(ValueError):
        instance.converse(" ", [{"role": "user", "content": [{"text": "ok"}]}], [])


def _prepared() -> AWSPreparedRequest:
    body = b'{"text": "\\u00e9", "value": 1}\n'
    return AWSPreparedRequest(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/model/a%2Fb/converse?q=%2F",
        headers={
            "Host": b"bedrock-runtime.us-east-1.amazonaws.com",
            "Content-Type": b"application/json",
            "Content-Length": str(len(body)).encode("ascii"),
            "Accept-Encoding": b"identity",
            "Authorization": b"TEST_ONLY_SIGNATURE_MARKER",
            "X-Amz-Date": b"20260101T000000Z",
            "X-Amz-Security-Token": b"TEST_ONLY_SESSION_MARKER",
        },
        body=body,
        stream_output=False,
    )


class _AsyncBody(httpx.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for offset in range(0, len(self.content), 31):
            yield self.content[offset : offset + 31]

    async def aclose(self) -> None:
        self.closed = True


def test_prepared_request_retains_signed_bytes_and_decodes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared()
    content = json.dumps(response()).encode("utf-8")
    compressed = gzip.compress(content)
    stream = _AsyncBody(compressed)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == prepared.method
        assert str(request.url) == prepared.url
        assert request.content == prepared.body
        assert request.headers.raw == [
            (name.encode("ascii"), value) for name, value in prepared.headers.items()
        ]
        assert request.extensions["timeout"]["connect"] == 5.0
        return httpx.Response(
            200,
            stream=stream,
            headers={
                "Content-Encoding": "gzip",
                "Content-Length": str(len(compressed)),
                "X-Amzn-Requestid": "fake-request",
            },
        )

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        assert kwargs == {"retries": 0, "trust_env": False}
        return httpx.MockTransport(handle)

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    result = bedrock._send_prepared(prepared)  # noqa: SLF001
    assert result.content == content
    assert result.status_code == 200
    assert result.headers["content-length"] == str(len(content))
    assert "content-encoding" not in result.headers
    assert result.headers["x-amzn-requestid"] == "fake-request"
    assert stream.closed
    assert len(seen) == 1


@pytest.mark.parametrize("mapping_failure", [False, True])
def test_prepared_response_closes_after_mapping(
    monkeypatch: pytest.MonkeyPatch, mapping_failure: bool
) -> None:
    bounded = httpx.Response(200, content=b"bounded")
    close_calls: list[bool] = []
    close = bounded.close

    def close_response() -> None:
        close_calls.append(True)
        close()

    def send(*args: object, **kwargs: object) -> httpx.Response:
        return bounded

    def fail_mapping(*args: object, **kwargs: object) -> None:
        raise RuntimeError("TEST_ONLY_MAPPING_ERROR")

    monkeypatch.setattr(bounded, "close", close_response)
    monkeypatch.setattr(bedrock, "send_prepared_bounded", send)
    if mapping_failure:
        monkeypatch.setattr(bedrock, "AWSResponse", fail_mapping)
        with pytest.raises(RuntimeError, match="TEST_ONLY_MAPPING_ERROR"):
            bedrock._send_prepared(_prepared())  # noqa: SLF001
    else:
        result = bedrock._send_prepared(_prepared())  # noqa: SLF001
        assert result.content == b"bounded"
    assert close_calls == [True]
    assert bounded.is_closed


@pytest.mark.parametrize(
    ("encoding", "content", "error"),
    [
        ("identity", b"x" * (1024 * 1024 + 1), http_client.ResponseTooLarge),
        (
            "gzip",
            gzip.compress(b"x" * (1024 * 1024 + 1), mtime=0),
            http_client.ResponseTooLarge,
        ),
        ("gzip", b"invalid gzip", httpx.DecodingError),
        ("gzip", gzip.compress(b"ok", mtime=0)[:-1], httpx.DecodingError),
        ("br", b"unsupported", httpx.DecodingError),
    ],
    ids=[
        "identity-oversize",
        "gzip-oversize",
        "invalid-gzip",
        "truncated-gzip",
        "unsupported-encoding",
    ],
)
def test_prepared_response_failures_close_streams(
    monkeypatch: pytest.MonkeyPatch,
    encoding: str,
    content: bytes,
    error: type[httpx.RequestError],
) -> None:
    stream = _AsyncBody(content)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, stream=stream, headers={"Content-Encoding": encoding}
        )

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    with pytest.raises(error):
        bedrock._send_prepared(_prepared())  # noqa: SLF001
    assert stream.closed
    assert len(seen) == 1


def test_oversized_prepared_body_rejects_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared()
    prepared.body = b"x" * (bedrock.MAX_INPUT_BYTES + 1)

    def deny_send(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("Oversized prepared input MUST NOT reach the transport")

    monkeypatch.setattr(bedrock, "send_prepared_bounded", deny_send)
    with pytest.raises(LLMUnavailable):
        bedrock._send_prepared(prepared)  # noqa: SLF001


@pytest.mark.parametrize("phase", ["headers", "body", "drip"])
def test_prepared_deadline_cancels_pending_io(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    events: list[str] = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            try:
                while True:
                    if phase == "body":
                        await asyncio.Event().wait()
                    await asyncio.sleep(0.005)
                    events.append("chunk")
                    yield b"x"
            finally:
                events.append("cancelled")

        async def aclose(self) -> None:
            events.append("closed")

    async def handle(request: httpx.Request) -> httpx.Response:
        events.append("sent")
        if phase == "headers":
            try:
                await asyncio.Event().wait()
            finally:
                events.append("cancelled")
        return httpx.Response(200, stream=SlowBody())

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    monkeypatch.setattr(http_client, "REQUEST_SECONDS", 0.05)
    started = time.monotonic()
    with pytest.raises(httpx.ReadTimeout):
        bedrock._send_prepared(_prepared())  # noqa: SLF001
    assert time.monotonic() - started < 2.0
    assert events.count("sent") == events.count("cancelled") == 1
    assert events.count("closed") == int(phase != "headers")
    if phase == "drip":
        assert "chunk" in events


@pytest.mark.parametrize("field", ["system", "messages", "tools"])
def test_oversized_serialized_input_rejects_before_client(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    instance, _, client = provider(monkeypatch, response())
    expanded = "\u00e9" * (12 * 1024)
    system = expanded if field == "system" else "system"
    messages = [
        {
            "role": "user",
            "content": [{"text": expanded if field == "messages" else "ok"}],
        }
    ]
    tools = (
        [{"toolSpec": {"name": "tool", "description": expanded}}]
        if field == "tools"
        else []
    )
    with pytest.raises(LLMUnavailable):
        instance.converse(system, messages, tools)
    assert client.requests == []


def test_serialized_input_limit_accepts_exactly_64_kib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, client = provider(monkeypatch, response())
    request: bedrock.ConverseRequest = {
        "modelId": "model-id",
        "system": [{"text": "s"}],
        "messages": _USER_MESSAGES,
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0},
        "performanceConfig": {"latency": "standard"},
        "serviceTier": {"type": "default"},
    }
    baseline = bedrock._serialized_input_size(request)  # noqa: SLF001
    system = "s" * (bedrock.MAX_INPUT_BYTES - baseline + 1)
    assert instance.converse(system, _USER_MESSAGES, []) == response()
    assert len(client.requests) == 1
    with pytest.raises(LLMUnavailable):
        instance.converse(system + "s", _USER_MESSAGES, [])
    assert len(client.requests) == 1


def test_blob_expansion_counts_toward_serialized_input_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, client = provider(monkeypatch, response())
    messages = [
        {
            "role": "user",
            "content": [
                {"image": {"format": "png", "source": {"bytes": b"x" * (49 * 1024)}}}
            ],
        }
    ]
    with pytest.raises(LLMUnavailable):
        instance.converse("system", messages, [])
    assert client.requests == []


def _sdk_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> bedrock.BedrockConverseProvider:
    for name in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE", "BOTO_CONFIG"):
        monkeypatch.setenv(name, str(tmp_path / "absent"))
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    session = bedrock.boto3.Session(
        aws_access_key_id="TEST_ONLY_ACCESS_MARKER",
        aws_secret_access_key="TEST_ONLY_SECRET_MARKER",
        aws_session_token="TEST_ONLY_SESSION_MARKER",
    )

    def factory(**kwargs: object) -> object:
        assert kwargs == {}
        return session

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Botocore MUST use the bounded transport")

    monkeypatch.setattr(bedrock.boto3, "Session", factory)
    monkeypatch.setattr(URLLib3Session, "send", deny_network)
    return bedrock.BedrockConverseProvider("model-id")


@pytest.mark.parametrize(
    ("latency", "tier"), [("standard", "default"), ("optimized", "priority")]
)
def test_sdk_signs_and_parses_through_the_bounded_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, latency: str, tier: str
) -> None:
    prepared_requests: list[AWSPreparedRequest] = []
    sender = bedrock._send_prepared  # noqa: SLF001
    reply = {
        **response(),
        "performanceConfig": {"latency": latency},
        "serviceTier": {"type": tier},
    }
    stream = _AsyncBody(json.dumps(reply).encode())

    def send(request: AWSPreparedRequest, **kwargs: object) -> object:
        prepared_requests.append(request)
        return sender(request, **kwargs)

    def handle(request: httpx.Request) -> httpx.Response:
        prepared = prepared_requests[-1]
        assert request.method == prepared.method
        assert str(request.url) == prepared.url
        assert request.content == prepared.body
        for name, value in prepared.headers.items():
            expected_value = value.encode("utf-8") if isinstance(value, str) else value
            assert request.headers[name].encode("utf-8") == expected_value
        assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 ")
        assert request.headers["x-amz-security-token"] == "TEST_ONLY_SESSION_MARKER"
        assert request.url.host == "bedrock-runtime.us-east-1.amazonaws.com"
        body = json.loads(request.content)
        assert body["performanceConfig"] == {"latency": "standard"}
        assert body["serviceTier"] == {"type": "default"}
        expected: bedrock.ConverseRequest = {
            "modelId": "model-id",
            "system": [{"text": "system"}],
            "messages": _USER_MESSAGES,
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0},
            "performanceConfig": {"latency": "standard"},
            "serviceTier": {"type": "default"},
        }
        expected_size = bedrock._serialized_input_size(expected)  # noqa: SLF001
        assert len(prepared.body) == expected_size
        return httpx.Response(200, stream=stream)

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://floci:4566")
    monkeypatch.setattr(bedrock, "_send_prepared", send)
    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    instance = _sdk_provider(monkeypatch, tmp_path)
    result = instance.converse("system", _USER_MESSAGES, [])
    assert result["output"] == response()["output"]
    assert result["stopReason"] == "end_turn"
    assert result["performanceConfig"] == {"latency": latency}
    assert result["serviceTier"] == {"type": tier}
    metadata = cast(dict[str, object], result["ResponseMetadata"])
    assert metadata["RetryAttempts"] == 0
    assert len(prepared_requests) == 1
    assert stream.closed


@pytest.mark.parametrize("status", [403, 429, 503])
def test_sdk_errors_remain_static_without_retries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status: int,
) -> None:
    calls: list[httpx.Request] = []
    stream = _AsyncBody(b'{"message":"TEST_ONLY_PRIVATE_ERROR"}')

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            stream=stream,
            headers={"X-Amzn-Errortype": "AccessDeniedException"},
        )

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    instance = _sdk_provider(monkeypatch, tmp_path)
    with pytest.raises(LLMUnavailable) as raised:
        instance.converse("system", _USER_MESSAGES, [])
    assert str(raised.value) == ""
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert len(calls) == 1
    assert stream.closed
    logged = capsys.readouterr().err
    assert "TEST_ONLY_PRIVATE_ERROR" not in logged
    assert json.loads(logged) == {
        "event": "bedrock_converse_failed",
        "reason": "client_error",
        "exception": "AccessDeniedException",
        "error_code": "AccessDeniedException",
        "http_status": status,
        "stop_reason": None,
    }
    for marker in (
        "TEST_ONLY_ACCESS_MARKER",
        "TEST_ONLY_SECRET_MARKER",
        "TEST_ONLY_SESSION_MARKER",
    ):
        assert marker not in logged


@pytest.mark.parametrize("failure", ["connect", "deadline", "decode", "oversize"])
def test_sdk_transport_failures_are_static_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    calls: list[httpx.Request] = []
    content = (
        gzip.compress(b"x" * (http_client.MAX_RESPONSE_BYTES + 1))
        if failure == "oversize"
        else b"TEST_ONLY_INVALID_GZIP"
    )
    stream = _AsyncBody(content)

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "connect":
            raise httpx.ConnectTimeout("TEST_ONLY_PRIVATE_ERROR")
        if failure == "deadline":
            raise httpx.ReadTimeout("TEST_ONLY_PRIVATE_ERROR")
        return httpx.Response(200, stream=stream, headers={"Content-Encoding": "gzip"})

    def make_transport(**kwargs: object) -> httpx.MockTransport:
        return httpx.MockTransport(handle)

    monkeypatch.setattr(http_client.httpx, "AsyncHTTPTransport", make_transport)
    instance = _sdk_provider(monkeypatch, tmp_path)
    with pytest.raises(LLMUnavailable) as raised:
        instance.converse("system", _USER_MESSAGES, [])
    assert str(raised.value) == ""
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert len(calls) == 1
    assert stream.closed == (failure in ("decode", "oversize"))
    logged = capsys.readouterr().err
    assert "TEST_ONLY_PRIVATE_ERROR" not in logged
    assert "TEST_ONLY_INVALID_GZIP" not in logged
    assert json.loads(logged) == {
        "event": "bedrock_converse_failed",
        "reason": "client_error",
        "exception": {
            "connect": "ConnectTimeout",
            "deadline": "ReadTimeout",
            "decode": "DecodingError",
            "oversize": "ResponseTooLarge",
        }[failure],
        "error_code": None,
        "http_status": None,
        "stop_reason": None,
    }
    for marker in (
        "TEST_ONLY_ACCESS_MARKER",
        "TEST_ONLY_SECRET_MARKER",
        "TEST_ONLY_SESSION_MARKER",
    ):
        assert marker not in logged
