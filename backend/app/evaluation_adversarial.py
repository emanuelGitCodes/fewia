from copy import deepcopy
from hashlib import sha256
from json import dumps
from math import isfinite
from typing import cast

from app.agent.provider import LLMProvider

_MARKER_ERROR = "scenario marker is invalid"
_PUBLIC_ERROR = "public observation is invalid"
_INJECTION_ERROR = "scenario injection is invalid"


def scenario_markers(case: dict[str, object]) -> tuple[str, ...]:
    behavior = case.get("fixture_behavior", {})
    if not isinstance(behavior, dict):
        raise ValueError(_MARKER_ERROR)
    fixture = behavior.get("provider_fixture", {})
    if not isinstance(fixture, dict):
        raise ValueError(_MARKER_ERROR)
    if "secret_marker" not in fixture:
        return ()
    marker = fixture["secret_marker"]
    if type(marker) is not str or not marker or len(marker) > 200:
        raise ValueError(_MARKER_ERROR)
    return (marker,)


def sanitize_public(value: object, markers: tuple[str, ...]) -> object:
    if any(
        type(marker) is not str or not marker or len(marker) > 200 for marker in markers
    ):
        raise ValueError(_PUBLIC_ERROR)
    ordered = sorted(set(markers), key=len, reverse=True)
    active: set[int] = set()

    def redact(text: str) -> str:
        for marker in ordered:
            text = text.replace(marker, "[redacted]")
        if any(marker in text for marker in ordered):
            raise ValueError(_PUBLIC_ERROR)
        return text

    def copy(item: object) -> object:
        if item is None or type(item) in (bool, int):
            return item
        if type(item) is float:
            if not isfinite(item):
                raise ValueError(_PUBLIC_ERROR)
            return item
        if type(item) is str:
            return redact(item)
        if type(item) not in (dict, list) or id(item) in active:
            raise ValueError(_PUBLIC_ERROR)
        active.add(id(item))
        try:
            if type(item) is list:
                return [copy(child) for child in cast(list[object], item)]
            result: dict[str, object] = {}
            for key, child in cast(dict[object, object], item).items():
                if type(key) is not str:
                    raise ValueError(_PUBLIC_ERROR)
                if key == "reasoningContent":
                    continue
                copied = copy(child)
                public_key = redact(key)
                if (
                    public_key in result
                    or public_key == "reasoningContent"
                    or any(marker in public_key for marker in ordered)
                ):
                    raise ValueError(_PUBLIC_ERROR)
                result[public_key] = copied
            return result
        finally:
            active.remove(id(item))

    try:
        return copy(value)
    except RecursionError:
        raise ValueError(_PUBLIC_ERROR) from None


class ScenarioProvider:
    def __init__(self, provider: LLMProvider, case: dict[str, object]) -> None:
        self._provider = provider
        self._injected_text: str | None = None
        self.injected_text_hash: str | None = None
        self.injection_applied = False
        if case.get("id") != "A02":
            return
        behavior = case.get("fixture_behavior")
        if not isinstance(behavior, dict):
            raise ValueError(_INJECTION_ERROR)
        text = behavior.get("provider_text")
        if (
            behavior.get("kind") != "untrusted_provider_text"
            or type(text) is not str
            or not text.strip()
            or len(text) > 4000
        ):
            raise ValueError(_INJECTION_ERROR)
        try:
            markers = scenario_markers(case)
            if any(marker in text for marker in markers):
                raise ValueError(_INJECTION_ERROR)
            self.injected_text_hash = sha256(text.encode("utf-8")).hexdigest()
        except (UnicodeEncodeError, ValueError):
            raise ValueError(_INJECTION_ERROR) from None
        self._injected_text = dumps({"untrusted_provider_text": text})

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        if self._injected_text is None:
            return self._provider.converse(system_prompt, messages, tools)
        copied = deepcopy(messages)
        for message in reversed(copied):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                raise ValueError(_INJECTION_ERROR)
            message["content"] = [*content, {"text": self._injected_text}]
            self.injection_applied = True
            return self._provider.converse(system_prompt, copied, tools)
        raise ValueError(_INJECTION_ERROR)
