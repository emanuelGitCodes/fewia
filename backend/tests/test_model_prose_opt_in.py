import hashlib
import json
from collections.abc import Callable
from typing import Any, cast

import pytest

from app import evaluation_protocol as protocol
from app.agent import chat_loop
from app.agent.chat_answer import render_public_answer
from app.agent.chat_loop import run_chat
from app.agent.ingredient_tool import INGREDIENT_TOOL
from app.agent.planning_tool import execute_plan
from app.agent.price_tool import PRICE_TOOL, execute_price_lines
from app.agent.provider import LLMProvider
from app.agent.substitute_tool import SUBSTITUTE_TOOL
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_inputs import prepare_case
from app.evaluation_model_turn import observe_model_turn
from tests.test_chat_loop import (
    _LIMIT,
    _PROPOSED_ANSWER_START,
    _SWAP_ANSWER,
    _SWAP_ARGS,
    PERIOD,
    FakeLLM,
    Proposer,
    _discovery_block,
    _proposal_replies,
    _propose_run,
    _reply,
    _text_block,
    _tool_block,
    budget,
    plan_args,
)
from tests.test_evaluation_model_turn import case, tool
from tests.test_evaluation_protocol import _case

SENTINEL = "Zephyrword"
GROUNDED_MONEY = "Chickpeas bring the sample meal price to $17.03."
GROUNDED_PLAIN = "Chickpeas raise the energy to 384 kcal per serving."


def _swap(text: str, *, reasoning: object | None = None) -> list[Any]:
    return [
        _reply(
            [_tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)], "tool_use"
        ),
        _reply([_text_block(text, reasoning=reasoning)], "end_turn"),
    ]


def _run(
    replies: list[Any],
    *,
    model_prose: bool = True,
    history: list[dict[str, str]] | None = None,
) -> tuple[dict[str, object], FakeLLM]:
    provider = FakeLLM(replies)
    result = run_chat(
        provider,
        "swap chicken for chickpeas",
        budget(),
        PERIOD,
        history=history,
        model_prose=model_prose,
    )
    return result, provider


def _sha(text: object) -> str:
    return hashlib.sha256(cast(str, text).encode()).hexdigest()


def test_grounded_reply_with_money_becomes_the_answer_with_notice() -> None:
    result, provider = _run(_swap(GROUNDED_MONEY))
    assert len(provider.requests) == 2
    assert result["answer"] == f"{GROUNDED_MONEY} {SAMPLE_ESTIMATE_NOTICE}"
    assert result["reply_source"] == "model"
    assert result["reply_check"] == {
        "ok": True,
        "reasons": [],
        "unmatched": [],
        "gate": "clean",
    }
    assert result["status"] == "clarification"
    assert result["reply_sha256"] == _sha(result["answer"])


def test_grounded_reply_without_money_is_used_as_written() -> None:
    result, _ = _run(_swap(GROUNDED_PLAIN))
    assert result["answer"] == GROUNDED_PLAIN
    assert SAMPLE_ESTIMATE_NOTICE not in cast(str, result["answer"])
    assert result["reply_source"] == "model"
    assert result["reply_sha256"] == _sha(GROUNDED_PLAIN)


def test_needs_revision_keeps_the_template_status_plan_and_answer() -> None:
    args = plan_args(plan_cap_cents=100)
    replies: list[Any] = [
        _reply([_tool_block("p1", payload=args)], "tool_use"),
        _reply([_text_block(f"{SENTINEL} needs a revision.")], "end_turn"),
    ]
    result, _ = _run(replies)
    expected = execute_plan(args, budget(), PERIOD)
    assert result["status"] == "needs_revision"
    assert result["plan"] == expected["plan"]
    assert result["answer"] == render_public_answer(expected)
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "planner"}
    assert SENTINEL not in json.dumps(result)


def _planner_then_final(args: dict[str, object], text: str) -> list[Any]:
    return [
        _reply([_tool_block("p1", payload=args)], "tool_use"),
        _reply([_text_block(text)], "end_turn"),
    ]


_CONFLICTS = {
    "diet": plan_args(
        meals=[{"recipe_id": "chicken_tacos", "servings": 2}], diet="vegan"
    ),
    "exclusion": plan_args(
        meals=[{"recipe_id": "vegetable_pasta", "servings": 2}],
        ingredient_exclusions=["onion"],
    ),
    "unknown_restriction": plan_args(
        meals=[{"recipe_id": "bean_tacos", "servings": 2}],
        ingredient_exclusions=["mystery spice"],
    ),
}


@pytest.mark.parametrize("name", list(_CONFLICTS))
def test_planner_conflict_or_clarification_uses_the_template(name: str) -> None:
    args = _CONFLICTS[name]
    template, _ = _run(_planner_then_final(args, "done"), model_prose=False)
    result, _ = _run(_planner_then_final(args, "Your plan is ready."))
    assert result["answer"] == template["answer"]
    assert "Your plan is ready." not in cast(str, result["answer"])
    assert result["status"] == template["status"]
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "tool_failed"}


def test_an_earlier_failed_tool_forces_the_template_even_after_a_good_one() -> None:
    bad = {**_SWAP_ARGS, "recipe_id": "no_such_meal"}
    replies: list[Any] = [
        _reply([_tool_block("w1", name=SUBSTITUTE_TOOL, payload=bad)], "tool_use"),
        _reply(
            [_tool_block("w2", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)], "tool_use"
        ),
        _reply([_text_block(GROUNDED_PLAIN)], "end_turn"),
    ]
    result, _ = _run(replies)
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "tool_failed"}


def test_a_failed_tool_beside_a_good_one_forces_the_template() -> None:
    bad = {**_SWAP_ARGS, "recipe_id": "no_such_meal"}
    replies: list[Any] = [
        _reply(
            [
                _tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS),
                _tool_block("w2", name=SUBSTITUTE_TOOL, payload=bad),
            ],
            "tool_use",
        ),
        _reply([_text_block(GROUNDED_PLAIN)], "end_turn"),
    ]
    result, _ = _run(replies)
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "tool_failed"}
    assert GROUNDED_PLAIN not in cast(str, result["answer"])


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        (SUBSTITUTE_TOOL, {"recipe_id": "bean_tacos", "with_food": "pork"}),
        (SUBSTITUTE_TOOL, {"recipe_id": "bean_tacos", "with_food": "zzqx"}),
        (INGREDIENT_TOOL, {"name": "pork"}),
        (INGREDIENT_TOOL, {"name": "zzqx"}),
    ],
)
def test_a_question_status_from_a_read_tool_uses_the_template(
    tool_name: str, args: dict[str, object]
) -> None:
    text = "I swapped in the beans for you."

    def replies() -> list[Any]:
        return [
            _reply([_tool_block("r1", name=tool_name, payload=args)], "tool_use"),
            _reply([_text_block(text)], "end_turn"),
        ]

    template, _ = _run(replies(), model_prose=False)
    result, _ = _run(replies())
    assert result["answer"] == template["answer"]
    assert text not in cast(str, result["answer"])
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "not_final"}


@pytest.mark.parametrize("text", ["Use Ⅲ eggs.", "10³ kcal", "①"])
def test_non_ascii_digits_reach_the_validator_unfolded(text: str) -> None:
    result, _ = _run(_swap(text))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {
        "ok": False,
        "reasons": ["unsupported_character"],
        "unmatched": [],
        "gate": "clean",
    }


def test_the_stored_reply_is_the_normalized_text_after_a_pass() -> None:
    result, _ = _run(_swap(f"  {GROUNDED_PLAIN}\n"))
    assert result["answer"] == GROUNDED_PLAIN
    assert result["reply_source"] == "model"


def test_a_reply_with_list_lines_is_stored_with_its_newlines() -> None:
    text = f"{GROUNDED_PLAIN}\n- Fits the plan.\n- Easy swap."
    result, _ = _run(_swap(text))
    assert result["answer"] == text
    assert result["reply_source"] == "model"
    assert result["reply_sha256"] == _sha(text)


def test_a_claim_split_across_lines_still_falls_back_to_the_template() -> None:
    result, _ = _run(_swap("These are gluten-\nfree."))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert cast(dict[str, object], result["reply_check"])["reasons"] == [
        "forbidden_claim"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "The tofu version also becomes vegan-friendly, while the original bean "
        "version is vegetarian.",
        "These are vegan.",
    ],
)
def test_a_diet_claim_falls_back_to_the_template(text: str) -> None:
    result, _ = _run(_swap(text))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert cast(dict[str, object], result["reply_check"])["reasons"] == [
        "forbidden_claim"
    ]


@pytest.mark.parametrize("final", ["Done.", "Your plan has been updated."])
def test_a_proposal_run_gets_the_template_whatever_the_model_says(final: str) -> None:
    result, _ = _propose_run(_proposal_replies(final), Proposer(), model_prose=True)
    assert result["reply_source"] == "template"
    assert result["proposal_id"] == "proposal-1"
    answer = cast(str, result["answer"])
    assert answer.startswith(_PROPOSED_ANSWER_START)
    assert "Apply it in the plan panel." in answer


def test_system_prompt_asks_for_whole_grams() -> None:
    assert (
        "Tool masses are in milligrams; in replies write grams rounded to the "
        "nearest whole gram (14484 mg is 14 g)."
    ) in chat_loop.SYSTEM_PROMPT


def _price_run(
    text: str, *, stale: bool
) -> tuple[dict[str, object], str, dict[str, Any]]:
    held = BudgetResult(10_000, 250, stale, (STALE_SPENDING_WARNING,) if stale else ())
    args: dict[str, object] = {"meals": [{**_SWAP_ARGS}]}
    estimate = cast(dict[str, Any], execute_price_lines(args, held, None)["estimate"])
    total = estimate["total_cents"]
    reply = text.format(total=f"${total // 100}.{total % 100:02d}")
    provider = FakeLLM(
        [
            _reply([_tool_block("l1", name=PRICE_TOOL, payload=args)], "tool_use"),
            _reply([_text_block(reply)], "end_turn"),
        ]
    )
    result = run_chat(provider, "price it", held, PERIOD, model_prose=True)
    return result, reply, estimate


def test_stale_budget_appends_the_server_warning_before_the_notice() -> None:
    result, reply, _ = _price_run("The sample total is {total}.", stale=True)
    assert result["reply_source"] == "model"
    assert result["answer"] == (
        f"{reply} {STALE_SPENDING_WARNING} {SAMPLE_ESTIMATE_NOTICE}"
    )
    assert result["reply_sha256"] == _sha(result["answer"])


def test_a_model_copy_of_the_stale_warning_is_a_forbidden_claim() -> None:
    text = "The sample total is {total}. " + STALE_SPENDING_WARNING
    for stale in (True, False):
        result, reply, _ = _price_run(text, stale=stale)
        check = cast(dict[str, object], result["reply_check"])
        assert check["reasons"] == ["forbidden_claim"]
        assert result["reply_source"] == "template"
        assert reply not in cast(str, result["answer"])
    fresh, _, _ = _price_run("The sample total is {total}.", stale=False)
    assert STALE_SPENDING_WARNING not in cast(str, fresh["answer"])


def test_a_stale_tool_payload_adds_the_warning_when_the_budget_is_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = cast(
        Callable[..., tuple[dict[str, object] | None, dict[str, object]]],
        chat_loop.dispatch,
    )

    def stale_dispatch(
        *args: object, **kwargs: object
    ) -> tuple[dict[str, object] | None, dict[str, object]]:
        payload, block = real(*args, **kwargs)
        assert payload is not None
        payload["stale"] = True
        return payload, block

    monkeypatch.setattr(chat_loop, "dispatch", stale_dispatch)
    result, _ = _run(_swap(GROUNDED_PLAIN))
    assert result["reply_source"] == "model"
    assert result["answer"] == f"{GROUNDED_PLAIN} {STALE_SPENDING_WARNING}"


def test_stale_warning_is_added_without_money_and_without_a_notice() -> None:
    held = BudgetResult(10_000, 250, True, (STALE_SPENDING_WARNING,))
    replies: list[Any] = [
        _reply(
            [_tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)], "tool_use"
        ),
        _reply([_text_block(GROUNDED_PLAIN)], "end_turn"),
    ]
    result = run_chat(FakeLLM(replies), "swap", held, PERIOD, model_prose=True)
    assert result["answer"] == f"{GROUNDED_PLAIN} {STALE_SPENDING_WARNING}"
    assert SAMPLE_ESTIMATE_NOTICE not in cast(str, result["answer"])


def test_ungrounded_reply_falls_back_to_the_template_and_is_never_stored() -> None:
    result, _ = _run(_swap(f"{SENTINEL} adds 999 kcal."))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {
        "ok": False,
        "reasons": ["unmatched_number"],
        "unmatched": ["+999"],
        "gate": "clean",
    }
    assert result["reply_sha256"] == _sha(_SWAP_ANSWER)
    assert SENTINEL not in json.dumps(result)


def test_gluten_free_claim_falls_back_to_the_template() -> None:
    result, _ = _run(_swap(f"{SENTINEL} is gluten-free at 384 kcal."))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    check = cast(dict[str, object], result["reply_check"])
    assert check["ok"] is False
    assert "forbidden_claim" in cast(list[str], check["reasons"])
    assert SENTINEL not in json.dumps(result)


def test_number_word_falls_back_to_the_template() -> None:
    result, _ = _run(_swap(f"{SENTINEL} adds about half the energy."))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert SENTINEL not in json.dumps(result)


def test_opt_out_keeps_todays_answer_and_runs_no_check() -> None:
    result, _ = _run(_swap(GROUNDED_MONEY), model_prose=False)
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert result["reply_check"] is None
    assert result["reply_sha256"] == _sha(_SWAP_ANSWER)


def test_default_is_opt_out() -> None:
    provider = FakeLLM(_swap(GROUNDED_MONEY))
    result = run_chat(provider, "swap", budget(), PERIOD)
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"


def test_no_tool_means_no_check_and_todays_answer() -> None:
    text = "Which meal should I plan?"
    on, _ = _run([_reply([_text_block(text)], "end_turn")])
    off, _ = _run([_reply([_text_block(text)], "end_turn")], model_prose=False)
    assert on["answer"] == off["answer"]
    assert on["reply_source"] == "template"
    assert on["reply_check"] == {"gate": "no_tools"}


def test_failed_tool_means_no_check() -> None:
    bad = {**_SWAP_ARGS, "recipe_id": "no_such_meal"}
    replies: list[Any] = [
        _reply([_tool_block("w1", name=SUBSTITUTE_TOOL, payload=bad)], "tool_use"),
        _reply([_text_block(f"{SENTINEL} ok.")], "end_turn"),
    ]
    on, _ = _run(replies)
    assert on["reply_source"] == "template"
    assert on["reply_check"] == {"gate": "tool_failed"}
    assert SENTINEL not in json.dumps(on)


def test_facts_come_from_every_tool_and_turn() -> None:
    replies: list[Any] = [
        _reply(
            [_tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)], "tool_use"
        ),
        _reply([_tool_block("b1", name="get_budget_summary", payload={})], "tool_use"),
        _reply([_text_block(GROUNDED_MONEY)], "end_turn"),
    ]
    result, _ = _run(replies)
    assert result["reply_source"] == "model"
    assert result["model_turns"] == 3


def test_refusal_text_is_not_validated_as_prose() -> None:
    refusal = '{"refusal":"purchase"}'
    on, _ = _run(_swap(refusal))
    off, _ = _run(_swap(refusal), model_prose=False)
    assert on["answer"] == off["answer"]
    assert on["reply_source"] == "template"
    assert on["reply_check"] == {"gate": "refusal"}


def test_accepted_plan_keeps_the_template_without_a_final_call() -> None:
    replies: list[Any] = [
        _reply([_tool_block("p1", payload=plan_args())], "tool_use"),
    ]
    result, provider = _run(replies)
    expected = execute_plan(plan_args(), budget(), PERIOD)
    assert len(provider.requests) == 1
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "planned_terminal"}


def test_discovery_clarification_keeps_the_template() -> None:
    replies: list[Any] = [_reply([_discovery_block()], "tool_use")]
    on, provider = _run(replies)
    off, _ = _run(
        [_reply([_discovery_block()], "tool_use")],
        model_prose=False,
    )
    assert len(provider.requests) == 1
    assert on["answer"] == off["answer"]
    assert on["reply_source"] == "template"
    assert on["reply_check"] == {"gate": "discovery_terminal"}


def test_planner_limit_keeps_the_limit_answer() -> None:
    replies: list[Any] = [
        _reply(
            [_tool_block(f"p-{i}", payload=plan_args(plan_cap_cents=100))],
            "tool_use",
        )
        for i in range(chat_loop.MAX_PLANNER_REVISIONS + 1)
    ]
    result, _ = _run(replies)
    assert result["status"] == "limit"
    assert result["answer"] == _LIMIT
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "limit"}


def test_reasoning_block_never_reaches_the_answer_or_next_request() -> None:
    secret = "hidden-chain-of-thought"
    hidden = {"text": secret}
    swap = _tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS, reasoning=hidden)
    replies: list[Any] = [
        _reply([swap], "tool_use"),
        _reply([_text_block(GROUNDED_PLAIN, reasoning=hidden)], "end_turn"),
    ]
    # Control: the sentinel is in what the provider returned.
    assert secret in json.dumps(replies)
    result, provider = _run(replies)
    assert len(provider.requests) == 2
    assert result["answer"] == GROUNDED_PLAIN
    assert result["reply_source"] == "model"
    stored = json.dumps(result)
    assert secret not in stored
    assert "reasoningContent" not in stored
    assert secret not in json.dumps(provider.requests[1]["messages"])
    # The check can fail: a reply that quotes the sentinel is stored in the result.
    quoted, _ = _run(_swap(f"{secret} has 384 kcal.", reasoning=hidden))
    assert secret in json.dumps(quoted)


def test_accepted_model_text_is_what_the_next_turn_replays() -> None:
    first, _ = _run(_swap(GROUNDED_PLAIN))
    history = [
        {"role": "user", "text": "swap chicken for chickpeas"},
        {"role": "assistant", "text": cast(str, first["answer"])},
    ]
    _, second = _run(_swap(GROUNDED_PLAIN), history=history)
    assert GROUNDED_PLAIN in json.dumps(second.requests[0]["messages"])


def test_system_prompt_asks_for_digits_copied_from_tool_results() -> None:
    assert (
        "In your final reply, write every number as digits with its unit, "
        "copied exactly from a tool result; do not use number words or "
        "fractions." in chat_loop.SYSTEM_PROMPT
    )


def test_evaluation_protocol_never_opts_in(monkeypatch: pytest.MonkeyPatch) -> None:
    real = chat_loop.run_chat
    seen: list[dict[str, object]] = []

    def spy(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append(dict(kwargs))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(chat_loop, "run_chat", spy)
    for case_id in ("P03", "P04"):
        protocol.evaluate_protocol_case(_case(case_id))
    assert seen
    assert all(not call.get("model_prose") for call in seen)


def test_evaluation_model_turn_never_stores_model_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, object]] = []
    real = chat_loop.run_chat

    def spy(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append(dict(kwargs))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(chat_loop, "run_chat", spy)

    class Prose:
        def __init__(self) -> None:
            self.replies = [
                tool("get_budget_summary", {}),
                {
                    "stopReason": "end_turn",
                    "output": {
                        "message": {
                            "role": "assistant",
                            "content": [{"text": f"{SENTINEL} all good."}],
                        }
                    },
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                },
            ]

        def converse(
            self,
            system_prompt: str,
            messages: list[dict[str, object]],
            tools: list[dict[str, object]],
        ) -> dict[str, object]:
            return self.replies.pop(0)

    provider: LLMProvider = Prose()
    turn = observe_model_turn(
        prepare_case(case()),
        "How is my budget?",
        provider,
        markers=(),
        history=[],
        previous_request=None,
        record_evidence=lambda planning: "0123456789abcdef" * 4,
    )
    result = cast(dict[str, object], turn["result"])
    assert seen
    assert all(not call.get("model_prose") for call in seen)
    assert result["reply_source"] == "template"
    assert result["reply_check"] is None
    assert SENTINEL not in json.dumps(turn)


def test_positive_control_prose_would_show_if_the_flag_were_set() -> None:
    replies: list[Any] = [
        _reply([_tool_block("b1", name="get_budget_summary", payload={})], "tool_use"),
        _reply([_text_block(f"{SENTINEL} all good.")], "end_turn"),
    ]
    on, _ = _run(replies)
    assert on["answer"] == f"{SENTINEL} all good."
    assert on["reply_source"] == "model"
