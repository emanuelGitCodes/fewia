from typing import Protocol


class LLMProvider(Protocol):
    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]: ...


class LLMUnavailable(Exception):
    pass
