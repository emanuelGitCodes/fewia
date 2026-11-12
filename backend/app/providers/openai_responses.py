import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Literal, cast

import httpx
from pydantic import SecretStr

from app.agent.chat_messages import MAX_TOOL_CALLS, MAX_TOOL_FIELD_LEN
from app.agent.provider import LLMUnavailable
from app.provider_settings import ProviderConfigurationError
from app.providers.http_client import build_http_client, request_bounded

_ENDPOINTS = {
    "us": "https://us.api.openai.com/v1/responses",
    "global": "https://api.openai.com/v1/responses",
}
_IDENTIFIER = re.compile(rf"[A-Za-z0-9_-]{{1,{MAX_TOOL_FIELD_LEN}}}")
_MAX_KEY_BYTES = 65536
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_ITEMS = 128
_SCHEMA_TYPES = frozenset("object array string number integer boolean null".split())


_LABEL = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class _Invalid(ValueError):
    def __init__(self, item_type: str | None = None) -> None:
        super().__init__()
        self.item_type = item_type


def _label(value: object) -> str | None:
    if isinstance(value, str) and _LABEL.fullmatch(value) is not None:
        return value
    return None


def _error_labels(response: httpx.Response) -> tuple[str | None, str | None]:
    try:
        body = json.loads(response.text)
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            return _label(error.get("type")), _label(error.get("code"))
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _log_failure(
    reason: str,
    *,
    http_status: int | None = None,
    exception: str | None = None,
    error_type: str | None = None,
    error_code: str | None = None,
    item_type: str | None = None,
) -> None:
    print(
        json.dumps(
            {
                "event": "openai_responses_failed",
                "reason": reason,
                "http_status": http_status,
                "exception": exception,
                "error_type": error_type,
                "error_code": error_code,
                "item_type": item_type,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise _Invalid()
    return cast(dict[str, object], value)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise _Invalid()
    return value


def _encode(value: object) -> str:
    _json_value(value)
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


def _json_value(value: object) -> None:
    if isinstance(value, dict):
        for child in _mapping(value).values():
            _json_value(child)
    elif isinstance(value, list):
        for child in value:
            _json_value(child)
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise _Invalid()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _Invalid()
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise _Invalid()


def _decode(value: str) -> object:
    decoded: object = json.loads(
        value, object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )
    return decoded


def _read_key(path: Path) -> SecretStr:
    key: str | None = None
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        )
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if stat.S_ISREG(metadata.st_mode) and metadata.st_size <= _MAX_KEY_BYTES:
                payload = handle.read(_MAX_KEY_BYTES + 1)
                if len(payload) <= _MAX_KEY_BYTES:
                    key = payload.decode("ascii").strip()
    except (OSError, ValueError):
        pass
    if not key or any(not 33 <= ord(char) <= 126 for char in key):
        raise ProviderConfigurationError()
    return SecretStr(key)


def _schema(value: object) -> dict[str, object]:
    schema = _mapping(value)
    kind = schema.get("type")
    kinds = [kind] if isinstance(kind, str) else kind
    if kinds is not None and (
        not isinstance(kinds, list)
        or not kinds
        or any(not isinstance(item, str) or item not in _SCHEMA_TYPES for item in kinds)
    ):
        raise _Invalid()
    properties = _mapping(schema.get("properties", {}))
    for child in properties.values():
        _schema(child)
    required = schema.get("required", [])
    if (
        not isinstance(required, list)
        or any(not isinstance(name, str) or name not in properties for name in required)
        or len(set(required)) != len(required)
    ):
        raise _Invalid()
    if "items" in schema:
        _schema(schema["items"])
    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if type(additional) is not bool:
            _schema(additional)
    for keyword in ("$defs", "definitions"):
        if keyword in schema:
            for child in _mapping(schema[keyword]).values():
                _schema(child)
    if "enum" in schema:
        choices = schema["enum"]
        if not isinstance(choices, list) or not choices:
            raise _Invalid()
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword in schema:
            alternatives = schema[keyword]
            if not isinstance(alternatives, list) or not alternatives:
                raise _Invalid()
            for child in alternatives:
                _schema(child)
    _encode(schema)
    return schema


def _tools(value: list[dict[str, object]]) -> tuple[list[dict[str, object]], set[str]]:
    if not isinstance(value, list):
        raise _Invalid()
    result: list[dict[str, object]] = []
    names: set[str] = set()
    for tool in value:
        wrapper = _mapping(tool)
        if set(wrapper) != {"toolSpec"}:
            raise _Invalid()
        spec = _mapping(wrapper["toolSpec"])
        name = _identifier(spec.get("name"))
        description = spec.get("description")
        schema = _schema(_mapping(spec.get("inputSchema")).get("json"))
        if (
            name in names
            or not isinstance(description, str)
            or not description.strip()
            or schema.get("type") != "object"
        ):
            raise _Invalid()
        names.add(name)
        result.append(
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": schema,
                "strict": False,
            }
        )
    return result, names


def _result(value: object, pending: set[str]) -> dict[str, object]:
    result = _mapping(value)
    call_id = _identifier(result.get("toolUseId"))
    content = result.get("content")
    status = result.get("status", "success")
    if call_id not in pending or status not in ("success", "error"):
        raise _Invalid()
    if not isinstance(content, list) or not content:
        raise _Invalid()
    for raw in content:
        block = _mapping(raw)
        if set(block) == {"text"} and isinstance(block["text"], str):
            continue
        if set(block) != {"json"}:
            raise _Invalid()
    pending.remove(call_id)
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": _encode({"status": status, "content": content}),
    }


def _messages(
    messages: list[dict[str, object]], names: set[str]
) -> tuple[list[dict[str, object]], set[str]]:
    if not isinstance(messages, list) or not messages:
        raise _Invalid()
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    pending: set[str] = set()
    for raw in messages:
        message = _mapping(raw)
        role, content = message.get("role"), message.get("content")
        if (
            role not in ("user", "assistant")
            or not isinstance(content, list)
            or not content
        ):
            raise _Invalid()
        if role == "assistant" and pending:
            raise _Invalid()
        calls = 0
        for raw_block in content:
            block = _mapping(raw_block)
            if set(block) == {"text"}:
                if not isinstance(block["text"], str) or (role == "user" and pending):
                    raise _Invalid()
                items.append({"role": role, "content": block["text"]})
            elif set(block) == {"toolUse"} and role == "assistant":
                call = _mapping(block["toolUse"])
                call_id = _identifier(call.get("toolUseId"))
                name = _identifier(call.get("name"))
                arguments = _mapping(call.get("input"))
                if call_id in seen or name not in names:
                    raise _Invalid()
                calls += 1
                seen.add(call_id)
                pending.add(call_id)
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": name,
                        "arguments": _encode(arguments),
                    }
                )
            elif set(block) == {"toolResult"} and role == "user":
                items.append(_result(block["toolResult"], pending))
            else:
                raise _Invalid()
        if calls > MAX_TOOL_CALLS:
            raise _Invalid()
    if pending:
        raise _Invalid()
    return items, seen


def _usage(value: object) -> dict[str, int] | None:
    if value is None:
        return None
    usage = _mapping(value)
    incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
    if type(incoming) is not int or type(outgoing) is not int:
        raise _Invalid()
    if incoming < 0 or outgoing < 0:
        raise _Invalid()
    result = {"inputTokens": incoming, "outputTokens": outgoing}
    details = usage.get("input_tokens_details")
    if details is not None:
        cached = _mapping(details).get("cached_tokens")
        if cached is not None:
            if type(cached) is not int or not 0 <= cached <= incoming:
                raise _Invalid()
            result["cacheReadInputTokens"] = cached
    return result


def _response(
    value: object, names: set[str], history_ids: set[str]
) -> dict[str, object]:
    response = _mapping(value)
    status, output = response.get("status"), response.get("output")
    if (
        response.get("error") is not None
        or not isinstance(output, list)
        or len(output) > MAX_RESPONSE_ITEMS
    ):
        raise _Invalid()
    if status not in ("completed", "incomplete"):
        raise _Invalid()
    content: list[dict[str, object]] = []
    seen = set(history_ids)
    calls = 0
    block_count = 0
    refused = False
    for raw in output:
        item = _mapping(raw)
        kind = item.get("type")
        if kind == "reasoning":
            # FEWIA sends reasoning.effort "none" and store false, so it skips
            # reasoning items and does not replay them. A non-"none" effort
            # needs replayed reasoning items.
            continue
        if kind not in ("function_call", "message"):
            raise _Invalid(_label(kind))
        if status == "incomplete":
            continue
        if kind == "function_call":
            call_id = _identifier(item.get("call_id"))
            name = _identifier(item.get("name"))
            arguments = item.get("arguments")
            if (
                call_id in seen
                or name not in names
                or not isinstance(arguments, str)
                or item.get("status", "completed") != "completed"
            ):
                raise _Invalid()
            payload = _mapping(_decode(arguments))
            _encode(payload)
            seen.add(call_id)
            calls += 1
            content.append(
                {"toolUse": {"toolUseId": call_id, "name": name, "input": payload}}
            )
        elif kind == "message":
            blocks = item.get("content")
            if (
                item.get("role") != "assistant"
                or not isinstance(blocks, list)
                or not blocks
                or item.get("status", "completed") not in ("completed", "incomplete")
                or (status == "completed" and item.get("status") == "incomplete")
            ):
                raise _Invalid()
            block_count += len(blocks)
            if block_count > MAX_RESPONSE_ITEMS:
                raise _Invalid()
            for raw_block in blocks:
                block = _mapping(raw_block)
                if block.get("type") == "output_text" and isinstance(
                    block.get("text"), str
                ):
                    content.append({"text": block["text"]})
                elif block.get("type") == "refusal" and isinstance(
                    block.get("refusal"), str
                ):
                    refused = True
                else:
                    raise _Invalid()
    if calls > MAX_TOOL_CALLS:
        raise _Invalid()
    stop = "tool_use" if calls else "end_turn"
    if refused:
        stop, content = "guardrail_intervened", [{"text": ""}]
    elif status == "incomplete":
        reason = _mapping(response.get("incomplete_details")).get("reason")
        if reason == "max_output_tokens":
            stop = "max_tokens"
        elif reason == "content_filter":
            stop = "content_filtered"
        else:
            raise _Invalid()
        content = [{"text": ""}]
    elif not content:
        raise _Invalid()
    result: dict[str, object] = {
        "stopReason": stop,
        "output": {"message": {"role": "assistant", "content": content}},
    }
    usage = _usage(response.get("usage"))
    if usage is not None:
        result["usage"] = usage
    return result


class OpenAIResponsesProvider:
    def __init__(
        self,
        api_key_file: Path,
        *,
        region: Literal["us", "global"] = "us",
        client: httpx.Client | None = None,
    ) -> None:
        if region not in _ENDPOINTS or not isinstance(api_key_file, Path):
            raise ProviderConfigurationError()
        self._key = _read_key(api_key_file)
        self._endpoint = _ENDPOINTS[region]
        self._client = client or build_http_client(self._endpoint)

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        request: dict[str, object] | None = None
        serialized = b""
        names: set[str] = set()
        history_ids: set[str] = set()
        invalid: str | None = None
        try:
            if not isinstance(system_prompt, str) or not system_prompt.strip():
                raise _Invalid()
            translated, names = _tools(tools)
            items, history_ids = _messages(messages, names)
            request = {
                "model": "gpt-6-luna",
                "instructions": system_prompt,
                "input": items,
                "tools": translated,
                "reasoning": {"effort": "none"},
                "store": False,
                "max_output_tokens": 4096,
                "parallel_tool_calls": False,
            }
            serialized = _encode(request).encode("utf-8")
            if len(serialized) > MAX_REQUEST_BYTES:
                raise _Invalid()
        except (ValueError, TypeError, RecursionError, OverflowError) as exc:
            request = None
            invalid = type(exc).__name__
        if request is None:
            _log_failure("invalid_input", exception=invalid)
            raise ValueError("Provider input is invalid")
        result: dict[str, object] | None = None
        try:
            response = request_bounded(
                self._client,
                "POST",
                self._endpoint,
                content=serialized,
                headers={
                    "Authorization": f"Bearer {self._key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:  # noqa: BLE001
            _log_failure("transport_error", exception=type(exc).__name__)
        else:
            if response.status_code != 200:
                error_type, error_code = _error_labels(response)
                _log_failure(
                    "http_error",
                    http_status=response.status_code,
                    error_type=error_type,
                    error_code=error_code,
                )
            else:
                try:
                    result = _response(_decode(response.text), names, history_ids)
                except Exception as exc:  # noqa: BLE001
                    _log_failure(
                        "invalid_response",
                        http_status=200,
                        exception=type(exc).__name__,
                        item_type=exc.item_type if isinstance(exc, _Invalid) else None,
                    )
        if result is None:
            raise LLMUnavailable("The language model is unavailable")
        return result
