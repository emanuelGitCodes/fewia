from datetime import date
from hashlib import sha256
from typing import Any

import pytest

from app.agent import chat_loop
from app.agent.saved_plan_route import saved_plan_read
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.plan_revision import PlanRevisionInput

PERIOD = date(2026, 7, 1)


class _NoModel:
    def __init__(self) -> None:
        self.calls = 0

    def converse(self, *args: Any, **kwargs: Any) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("no model call expected")


def _plan(meals: list[dict[str, Any]] | None = None) -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "snapshot": {
                "meals": (
                    [{"recipe_id": "chicken_tacos", "servings": 2}]
                    if meals is None
                    else meals
                ),
                "pantry_ingredient_ids": [],
            },
        }
    )


def _run(
    message: str,
    *,
    plan: PlanRevisionInput | None = None,
    stale: bool = False,
    provider: _NoModel | None = None,
    **extra: Any,
) -> dict[str, Any]:
    held = BudgetResult(10_000, 250, stale, (STALE_SPENDING_WARNING,) if stale else ())
    result = chat_loop.run_chat(
        provider or _NoModel(),  # type: ignore[arg-type]
        message,
        held,
        PERIOD,
        plan_revision=_plan() if plan is None else plan,
        model_prose=True,
        **extra,
    )
    return dict(result)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Does my saved plan fit my budget?", "fit"),
        ("What does my plan cost right now?", "cost"),
        ("Remind me what the whole plan costs.", "cost"),
        ("Is the plan within my monthly budget?", "fit"),
        ("What is the total of this plan?", "cost"),
        ("What would the bowls cost with half the rice?", None),
        ("Add this plan to my Kroger cart and check out with the card on file.", None),
        ("Is this plan safe for my type 2 diabetes?", None),
        ("Plan 2 servings of bean tacos.", None),
        ("What does a plan cost?", None),
        ("What do my plan meals cost?", None),
        ("Would my plan fit my budget?", None),
        ("Hello", None),
    ],
)
def test_saved_plan_read(message: str, expected: str | None) -> None:
    assert saved_plan_read(message) == expected


def test_cost_runs_get_plan_without_model() -> None:
    provider = _NoModel()
    result = _run("What does my plan cost right now?", provider=provider)
    assert provider.calls == 0
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "saved_plan_read"}
    assert [entry["tool"] for entry in result["tool_trace"]] == ["get_plan"]
    assert result["plan"] is None
    assert result["proposal_id"] is None
    assert "Sample total for" in result["answer"]
    assert SAMPLE_ESTIMATE_NOTICE in result["answer"]


def test_fit_runs_plan_and_budget_tools() -> None:
    result = _run("Does my saved plan fit my budget?")
    assert [entry["tool"] for entry in result["tool_trace"]] == [
        "get_plan",
        "get_budget_summary",
    ]
    assert "fits the available USD $100.00" in result["answer"]
    assert "Pending: USD $2.50." in result["answer"]


def test_fit_reports_exceeding_a_low_cap() -> None:
    plan = PlanRevisionInput.model_validate(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "snapshot": {
                "meals": [{"recipe_id": "chicken_tacos", "servings": 8}],
                "pantry_ingredient_ids": [],
                "plan_cap_cents": 1,
            },
        }
    )
    result = _run("Is the plan within my monthly budget?", plan=plan)
    assert "exceeds the available" in result["answer"]


def test_stale_spending_warning_is_carried() -> None:
    result = _run("What does my plan cost right now?", stale=True)
    assert result["answer"].count(STALE_SPENDING_WARNING) == 1


def test_tool_results_reach_the_observer() -> None:
    seen: list[list[dict[str, object]]] = []
    _run("Does my saved plan fit my budget?", observe_terminal_tool_results=seen.append)
    assert len(seen) == 1
    assert len(seen[0]) == 2


def test_empty_plan_falls_through_without_trace() -> None:
    provider = _NoModel()
    with pytest.raises(chat_loop.ChatUnavailable):
        _run("What does my plan cost right now?", plan=_plan([]), provider=provider)
    assert provider.calls == 1


def test_no_plan_revision_keeps_model_path() -> None:
    provider = _NoModel()
    with pytest.raises(chat_loop.ChatUnavailable):
        chat_loop.run_chat(
            provider,  # type: ignore[arg-type]
            "What does my plan cost right now?",
            BudgetResult(10_000, 250, False, ()),
            PERIOD,
        )
    assert provider.calls == 1


def test_unrouted_message_calls_the_model() -> None:
    provider = _NoModel()
    with pytest.raises(chat_loop.ChatUnavailable):
        _run("What would the bowls cost with half the rice?", provider=provider)
    assert provider.calls == 1


def test_system_prompt_is_unchanged() -> None:
    digest = sha256(chat_loop.SYSTEM_PROMPT.encode()).hexdigest()
    assert len(digest) == 64
    assert "plan_groceries" in chat_loop.SYSTEM_PROMPT
