import hashlib
import json
from typing import Any, cast

import pytest

from app import evaluation_protocol as protocol
from app.agent import chat_loop
from app.agent.chat_answer import render_public_answer
from app.agent.chat_loop import run_chat
from app.agent.planning_tool import execute_plan
from app.agent.provider import LLMProvider
from app.agent.substitute_tool import TOOL_NAME as SUBSTITUTE_TOOL
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_inputs import prepare_case
from app.evaluation_model_turn import observe_model_turn
from tests.test_chat_loop import (
    _LIMIT,
    _SWAP_ANSWER,
    _SWAP_ARGS,
    PERIOD,
    FakeLLM,
    _discovery_block,
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
    assert result["reply_check"] == {"ok": True, "reasons": [], "unmatched": []}
    assert result["status"] == "clarification"
    assert result["reply_sha256"] == _sha(result["answer"])


def test_grounded_reply_without_money_is_used_as_written() -> None:
    result, _ = _run(_swap(GROUNDED_PLAIN))
    assert result["answer"] == GROUNDED_PLAIN
    assert SAMPLE_ESTIMATE_NOTICE not in cast(str, result["answer"])
    assert result["reply_source"] == "model"
    assert result["reply_sha256"] == _sha(GROUNDED_PLAIN)


def test_model_reply_keeps_the_status_and_plan_of_the_template_path() -> None:
    args = plan_args(plan_cap_cents=100)
    replies: list[Any] = [
        _reply([_tool_block("p1", payload=args)], "tool_use"),
        _reply([_text_block(f"{SENTINEL} needs a revision.")], "end_turn"),
    ]
    result, _ = _run(replies)
    expected = execute_plan(args, budget(), PERIOD)
    assert result["status"] == "needs_revision"
    assert result["plan"] == expected["plan"]
    assert result["answer"] == f"{SENTINEL} needs a revision."
    assert result["reply_source"] == "model"


def test_ungrounded_reply_falls_back_to_the_template_and_is_never_stored() -> None:
    result, _ = _run(_swap(f"{SENTINEL} adds 999 kcal."))
    assert result["answer"] == _SWAP_ANSWER
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {
        "ok": False,
        "reasons": ["unmatched_number"],
        "unmatched": ["999"],
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
    assert on["reply_check"] is None


def test_failed_tool_means_no_check() -> None:
    bad = {**_SWAP_ARGS, "recipe_id": "no_such_meal"}
    replies: list[Any] = [
        _reply([_tool_block("w1", name=SUBSTITUTE_TOOL, payload=bad)], "tool_use"),
        _reply([_text_block(f"{SENTINEL} ok.")], "end_turn"),
    ]
    on, _ = _run(replies)
    assert on["reply_source"] == "template"
    assert on["reply_check"] is None
    assert SENTINEL not in json.dumps(on)


def test_facts_come_from_every_tool_and_turn() -> None:
    replies: list[Any] = [
        _reply(
            [_tool_block("w1", name=SUBSTITUTE_TOOL, payload=_SWAP_ARGS)], "tool_use"
        ),
        _reply([_tool_block("p1", payload=plan_args(plan_cap_cents=100))], "tool_use"),
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
    assert on["reply_check"] is None


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
    assert result["reply_check"] is None


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
    assert on["reply_check"] is None


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
    assert result["reply_check"] is None


def test_reasoning_block_never_reaches_the_answer_or_next_request() -> None:
    hidden = {"text": "hidden-chain-of-thought"}
    result, provider = _run(_swap(GROUNDED_PLAIN, reasoning=hidden))
    assert result["answer"] == GROUNDED_PLAIN
    dumped = json.dumps(result)
    assert "hidden-chain-of-thought" not in dumped
    assert "reasoningContent" not in dumped
    assert "hidden-chain-of-thought" not in json.dumps(provider.requests)


def test_rejected_text_is_absent_from_the_next_turn_history() -> None:
    first, _ = _run(_swap(f"{SENTINEL} adds 999 kcal."))
    history = [
        {"role": "user", "text": "swap chicken for chickpeas"},
        {"role": "assistant", "text": cast(str, first["answer"])},
    ]
    _, second = _run(_swap(GROUNDED_PLAIN), history=history)
    assert SENTINEL not in json.dumps(second.requests)
    assert _SWAP_ANSWER in json.dumps(second.requests[0]["messages"])


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

    def spy(*args: Any, **kwargs: Any) -> dict[str, object]:
        seen.append(dict(kwargs))
        return real(*args, **kwargs)

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

    def spy(*args: Any, **kwargs: Any) -> dict[str, object]:
        seen.append(dict(kwargs))
        return real(*args, **kwargs)

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
