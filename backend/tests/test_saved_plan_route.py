from datetime import date
from typing import Any, cast

import pytest

from app.agent import chat_loop
from app.agent import chat_messages as msgs
from app.agent.saved_plan_route import saved_plan_read, saved_plan_reply
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.plan_revision import PlanRevisionInput
from app.evaluation_manifest import _hash

PERIOD = date(2026, 7, 1)


class _NoModel:
    def __init__(self) -> None:
        self.calls = 0

    def converse(self, *args: object, **kwargs: object) -> dict[str, object]:
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
    provider: object | None = None,
    **extra: object,
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
        ("What does my plan cost after removing the oats?", None),
        ("Does this plan fit my gluten-free diet?", None),
        ("Hello", None),
    ],
)
def test_saved_plan_read(message: str, expected: str | None) -> None:
    assert saved_plan_read(message) == expected


def test_corpus_probe_message_does_not_route() -> None:
    assert saved_plan_read("What does a plan cost?") is None


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


def test_fit_with_incomplete_price_states_available_and_not_fit() -> None:
    plan = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
        "estimate": {"total_cents": None},
    }
    summary = {"money_display": {"available": "USD $100.00", "pending": "USD $2.50"}}
    reply = saved_plan_reply(plan, summary, stale=False)
    assert reply is not None
    assert "Available: USD $100.00." in reply
    assert "fits" not in reply
    assert "incomplete" in reply


class _ToolThenDone:
    """Model that reads the budget once, then ends its turn."""

    def __init__(self) -> None:
        self.calls = 0

    def converse(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            call = {"toolUseId": "m1", "name": "get_budget_summary", "input": {}}
            content: list[dict[str, object]] = [{"toolUse": call}]
            stop = "tool_use"
        else:
            content = [{"text": "Done."}]
            stop = "end_turn"
        return {
            "output": {"message": {"role": "assistant", "content": content}},
            "stopReason": stop,
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }


def _assert_model_only_trace(result: dict[str, Any], provider: _ToolThenDone) -> None:
    assert provider.calls == 2
    assert [entry["tool"] for entry in result["tool_trace"]] == ["get_budget_summary"]
    assert result["reply_check"] != {"gate": "saved_plan_read"}


def _fail_route_tool(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    real = chat_loop.dispatch

    def failing(
        call: msgs.ToolCall, *args: object, **kwargs: object
    ) -> tuple[dict[str, object] | None, dict[str, object]]:
        if call.name != name or not call.tool_use_id.startswith("saved-plan"):
            return real(call, *args, **kwargs)  # type: ignore[arg-type]
        trace = cast(list[dict[str, object]], args[4])
        trace.append({"tool": name, "outcome": "error", "sequence": len(trace) + 1})
        block = msgs.tool_result_block(call.tool_use_id, {"error": "x"}, success=False)
        return None, block

    monkeypatch.setattr(chat_loop, "dispatch", failing)


@pytest.mark.parametrize(
    ("message", "tool"),
    [
        ("What does my plan cost right now?", "get_plan"),
        ("Does my saved plan fit my budget?", "get_plan"),
        ("Does my saved plan fit my budget?", "get_budget_summary"),
    ],
)
def test_tool_failure_falls_through_to_the_model(
    monkeypatch: pytest.MonkeyPatch, message: str, tool: str
) -> None:
    _fail_route_tool(monkeypatch, tool)
    provider = _ToolThenDone()
    _assert_model_only_trace(_run(message, provider=provider), provider)


def test_search_continuation_does_not_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_loop, "is_search_continuation", lambda message: True)
    provider = _ToolThenDone()
    result = _run("What does my plan cost right now?", provider=provider)
    _assert_model_only_trace(result, provider)


def test_empty_plan_falls_through_without_a_route_trace() -> None:
    provider = _ToolThenDone()
    result = _run(
        "What does my plan cost right now?", plan=_plan([]), provider=provider
    )
    _assert_model_only_trace(result, provider)


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
    assert _hash(chat_loop.SYSTEM_PROMPT) == (
        "06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a"
    )
