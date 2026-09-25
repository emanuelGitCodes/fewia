from collections.abc import Mapping
from typing import NotRequired, Protocol, TypedDict, Unpack, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from app.agent.provider import LLMUnavailable

_ALLOWED_REGIONS = frozenset({"us-east-1", "us-west-2"})
_SUPPORTED_STOP_REASONS = frozenset(
    "end_turn tool_use max_tokens stop_sequence "
    "guardrail_intervened content_filtered model_context_window_exceeded".split()
)
_LUNA_US_MODEL_ID = "us.openai.gpt-6-luna"
_NOVA2_US_MODEL_ID = "us.amazon.nova-2-lite-v1:0"
_LUNA_MAX_TOKENS = 4096
_NOVA2_MAX_TOKENS = 4096
_NOVA2_REASONING_FIELDS: dict[str, object] = {
    "reasoningConfig": {"type": "enabled", "maxReasoningEffort": "low"},
}


class ConverseRequest(TypedDict):
    modelId: str
    system: list[dict[str, str]]
    messages: list[dict[str, object]]
    inferenceConfig: dict[str, int | float]
    toolConfig: NotRequired[dict[str, object]]
    additionalModelRequestFields: NotRequired[dict[str, object]]


class BedrockClient(Protocol):
    def converse(self, **kwargs: Unpack[ConverseRequest]) -> dict[str, object]: ...


def _valid_content(content: object) -> bool:
    if not isinstance(content, list) or not content:
        return False
    for block in content:
        if (
            not isinstance(block, Mapping)
            or not block
            or ("text" in block and not isinstance(block["text"], str))
            or ("toolUse" in block and not isinstance(block["toolUse"], Mapping))
        ):
            return False
    return True


def _valid_message(message: object, role: str) -> bool:
    return (
        isinstance(message, Mapping)
        and message.get("role") == role
        and _valid_content(message.get("content"))
    )


def _is_us_profile(model_id: str, profile_id: str) -> bool:
    if model_id == profile_id:
        return True
    return model_id.startswith("arn:aws:bedrock:") and model_id.endswith(
        f":inference-profile/{profile_id}"
    )


def _is_luna_us_model(model_id: str) -> bool:
    return _is_us_profile(model_id, _LUNA_US_MODEL_ID)


def _is_nova2_us_model(model_id: str) -> bool:
    return _is_us_profile(model_id, _NOVA2_US_MODEL_ID)


class BedrockConverseProvider:
    def __init__(
        self,
        model_id: str,
        region: str = "us-east-1",
        profile_name: str | None = None,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 256:
            raise ValueError("model_id MUST be nonblank and at most 256 characters")
        if region not in _ALLOWED_REGIONS:
            raise ValueError("region MUST be us-east-1 or us-west-2")
        try:
            session = (
                boto3.Session(profile_name=profile_name)
                if profile_name is not None
                else boto3.Session()
            )
            self._client = cast(
                BedrockClient,
                session.client(
                    "bedrock-runtime",
                    region_name=region,
                    endpoint_url=f"https://bedrock-runtime.{region}.amazonaws.com",
                    config=Config(
                        connect_timeout=3,
                        read_timeout=40,
                        retries={"total_max_attempts": 1},
                    ),
                ),
            )
        except Exception:
            raise LLMUnavailable from None
        self._model_id = model_id

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt MUST be nonblank")
        if (
            not isinstance(messages, list)
            or not messages
            or not all(
                _valid_message(message, "user") or _valid_message(message, "assistant")
                for message in messages
            )
        ):
            raise ValueError("messages MUST contain valid user or assistant messages")
        if not isinstance(tools, list) or not all(
            isinstance(tool, dict) for tool in tools
        ):
            raise ValueError("tools MUST be a list of dictionaries")
        luna = _is_luna_us_model(self._model_id)
        nova2 = _is_nova2_us_model(self._model_id)
        if luna:
            # Converse MUST omit temperature for this reasoning model.
            inference: dict[str, int | float] = {"maxTokens": _LUNA_MAX_TOKENS}
        elif nova2:
            inference = {"maxTokens": _NOVA2_MAX_TOKENS, "temperature": 0}
        else:
            inference = {"maxTokens": 1024, "temperature": 0}
        request: ConverseRequest = {
            "modelId": self._model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "inferenceConfig": inference,
        }
        if luna:
            request["additionalModelRequestFields"] = {"reasoning_effort": "low"}
        elif nova2:
            request["additionalModelRequestFields"] = _NOVA2_REASONING_FIELDS
        if tools:
            request["toolConfig"] = {"tools": tools}
        try:
            response = self._client.converse(**request)
        except Exception:
            raise LLMUnavailable from None
        if not isinstance(response, dict):
            raise LLMUnavailable
        stop_reason = response.get("stopReason")
        output = response.get("output")
        if (
            not isinstance(stop_reason, str)
            or stop_reason not in _SUPPORTED_STOP_REASONS
            or not isinstance(output, dict)
        ):
            raise LLMUnavailable
        message = output.get("message")
        if not _valid_message(message, "assistant"):
            raise LLMUnavailable
        return response
