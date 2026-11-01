import json
from datetime import date

from app.agent.budget_tool import TOOL_NAME as BUDGET_TOOL_NAME
from app.agent.budget_tool import budget_summary_answer
from app.agent.chat_loop import run_chat
from app.domain.budget import BudgetResult


class FakeProvider:
    def __init__(self, replies: list[dict[str, object]]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.requests.append(
            {"system": system_prompt, "messages": messages, "tools": tools}
        )
        return self.replies.pop(0)


def _tool_reply() -> dict[str, object]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "budget-call",
                            "name": BUDGET_TOOL_NAME,
                            "input": {},
                        }
                    }
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


def _text_reply(text: str) -> dict[str, object]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            },
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


def test_budget_then_dairy_claim_returns_the_template_answer() -> None:
    period = date(2026, 9, 1)
    budget = BudgetResult(10_000, 250, False, ())
    for claim in (
        "This meal contains no dairy.",
        "This meal is milk-free.",
        "Chicken tacos don't contain dairy.",
        "Chicken tacos do not contain dairy.",
        "Chicken tacos are free from all dairy.",
        "This meal doesn't include any dairy.",
        "Chicken tacos do not include dairy.",
        "This meal does not have dairy.",
        "Chicken tacos don't have any dairy.",
        "This meal doesn't use dairy.",
        "Chicken tacos do not use any dairy.",
        "This meal hasn't got any dairy.",
        "Chicken tacos haven't got dairy.",
        "This meal has not got any dairy.",
        "Chicken tacos have not got any dairy.",
        "This meal is free of all dairy.",
        "Chicken tacos are without any dairy.",
        "Chicken tacos are without dairy.",
    ):
        provider = FakeProvider([_tool_reply(), _text_reply(claim)])

        result = run_chat(
            provider,
            "What is my remaining budget?",
            budget,
            period,
            model_prose=True,
        )

        assert len(provider.requests) == 2
        assert result["reply_source"] == "template"
        assert result["answer"] == budget_summary_answer(
            budget, period, spending_source="fixture"
        )
        assert result["reply_check"] == {
            "ok": False,
            "reasons": ["forbidden_claim"],
            "unmatched": [],
            "gate": "clean",
        }
        assert result["tool_trace"] == [
            {
                "tool": BUDGET_TOOL_NAME,
                "outcome": "success",
                "tool_use_id": "budget-call",
                "sequence": 1,
                "revision_index": None,
            }
        ]
        assert claim not in json.dumps(result)
