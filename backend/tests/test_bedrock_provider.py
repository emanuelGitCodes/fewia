from typing import cast

import pytest
from botocore.config import Config

from app.agent.provider import LLMUnavailable
from app.providers import bedrock


class FakeClient:
    def __init__(self, response: object) -> None:
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
        }
    ]


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
                {"guardContent": {"text": "safe"}},
            ],
        },
    ]

    instance.converse("system", messages, [])

    assert client.requests[0]["messages"] == messages


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
