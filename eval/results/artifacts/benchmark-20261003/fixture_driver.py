import json
import sys
from copy import deepcopy
from app.evaluate import main

class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls.append(
            deepcopy({"system": system_prompt, "messages": messages, "tools": tools})
        )
        answer = "Which meals and servings would you like?"
        text = (
            answer
            if tools
            else json.dumps(
                {
                    "status": "clarification",
                    "answer": answer,
                    "request": None,
                    "plan": None,
                    "budget": None,
                }
            )
        )
        return {
            "stopReason": "end_turn",
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "usage": {"inputTokens": 5, "outputTokens": 7},
        }

raise SystemExit(main(sys.argv[1:], provider_factory=RecordingProvider))
