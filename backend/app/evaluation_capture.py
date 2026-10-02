from json import JSONEncoder
from time import perf_counter

from app.agent.chat_context import read_usage
from app.agent.chat_messages import parse_provider_response
from app.agent.provider import LLMProvider

_LIMIT, _INVALID, _REDACTED = 65536, "[invalid]", "[redacted]"
_ENCODER = JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)


class CaptureProvider:
    def __init__(self, provider: LLMProvider, markers: tuple[str, ...] = ()) -> None:
        self.provider = provider
        self.markers = tuple(marker for marker in markers if marker)
        self.calls: list[dict[str, object]] = []
        self.tool_results: list[dict[str, object]] = []
        self.provider_calls = 0
        self.usage: dict[str, int] | None = {"inputTokens": 0, "outputTokens": 0}
        self.elapsed_seconds = 0.0
        self.invalid_responses = 0
        self.leakage = False
        self._seen_ids: set[str] = set()

    def _leaks(self, value: object, seen: set[int]) -> bool:
        if len(seen) >= _LIMIT:
            raise ValueError(_INVALID)
        if type(value) is str:
            return any(marker in value for marker in self.markers)
        if isinstance(value, (dict, list)) and id(value) not in seen:
            seen.add(id(value))
            if isinstance(value, dict):
                return any(
                    self._leaks(key, seen) or self._leaks(item, seen)
                    for key, item in value.items()
                    if key != "reasoningContent"
                )
            return any(self._leaks(item, seen) for item in value)
        return False

    def _text(self, value: str) -> str:
        for marker in self.markers:
            value = value.replace(marker, _REDACTED)
        return "" if any(marker in value for marker in self.markers) else value

    def _clean(self, value: object, budget: list[int], reject: bool) -> object:
        budget[0] -= 1 + (len(value) if type(value) is str else 0)
        if budget[0] < 0:
            raise ValueError(_INVALID)
        if type(value) is str:
            return self._text(value)
        if isinstance(value, dict):
            result: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError(_INVALID)
                if key == "reasoningContent":
                    if reject:
                        raise ValueError(_INVALID)
                    continue
                clean_key = self._clean(key, budget, reject)
                if not isinstance(clean_key, str) or clean_key in result:
                    raise ValueError(_INVALID)
                result[clean_key] = self._clean(item, budget, reject)
            return result
        if isinstance(value, list):
            return [self._clean(item, budget, reject) for item in value]
        if type(value) not in {bool, float, int, type(None)}:
            raise ValueError(_INVALID)
        return value

    def _payload(self, value: object, *, reject_reasoning: bool = False) -> object:
        try:
            encoded = ""
            clean = self._clean(value, [_LIMIT], reject_reasoning)
            for chunk in _ENCODER.iterencode(clean):
                if len(encoded) + len(chunk) > _LIMIT:
                    return self._text(_INVALID)
                encoded += chunk
            return clean if isinstance(clean, (dict, list)) else self._text(_INVALID)
        except (RecursionError, TypeError, ValueError):
            return self._text(_INVALID)

    def _observe_results(self, messages: list[dict[str, object]]) -> None:
        content = messages[-1].get("content") if messages else None
        if not isinstance(content, list):
            return
        for block in content:
            if len(self.tool_results) >= 24:
                break
            if not isinstance(block, dict) or "toolResult" not in block:
                continue
            result = block["toolResult"]
            captured: dict[str, object] = {
                key: self._text(_INVALID) for key in ("content", "status", "toolUseId")
            }
            if isinstance(result, dict):
                captured["content"] = self._payload(result.get("content"))
                for key in ("status", "toolUseId"):
                    value = result.get(key)
                    captured[key] = (
                        self._text(value)
                        if type(value) is str and len(value) <= 64
                        else self._text(_INVALID)
                    )
            self.tool_results.append(captured)

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.provider_calls += 1
        try:
            self._observe_results(messages)
            self.leakage |= self._leaks(messages[-1] if messages else None, set())
        except (RecursionError, TypeError, ValueError):
            pass
        started = perf_counter()
        try:
            response = self.provider.converse(system_prompt, messages, tools)
        except BaseException:
            self.usage = None
            raise
        finally:
            self.elapsed_seconds += perf_counter() - started
        usage = read_usage(response)
        if usage is None:
            self.usage = None
        elif self.usage is not None:
            for key, value in usage.items():
                self.usage[key] += value
        try:
            self.leakage |= self._leaks(response, set())
        except (RecursionError, TypeError, ValueError):
            pass
        try:
            _, _, calls, _ = parse_provider_response(response, self._seen_ids)
            for call in calls[: 24 - len(self.calls)]:
                self.calls.append(
                    {
                        "tool": self._text(call.name),
                        "input": self._payload(call.tool_input, reject_reasoning=True),
                    }
                )
        except (RecursionError, TypeError, ValueError):
            self.invalid_responses += 1
        return response
