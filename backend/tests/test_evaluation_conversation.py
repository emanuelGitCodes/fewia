import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from app import evaluation_conversation as runner
from app import evaluation_model_turn as model_turn
from app.agent import chat_loop
from app.agent.provider import LLMProvider
from app.evaluate_conversation import GoldFollowingProvider, main
from app.evaluation_conversation import run_conversation_suite
from app.evaluation_conversation_corpus import (
    ConversationCorpus,
    Gold,
    Scenario,
    load_conversation_corpus,
)
from app.evaluation_inputs import prepare_case

_CORPUS = Path(__file__).parent / "evaluation" / "conversation.json"
_RECORD_KEYS = {
    "scenario_id",
    "repeat",
    "turn",
    "profile",
    "status",
    "reply_source",
    "reply_sha256",
    "gate",
    "verdict",
    "proposal",
    "tools",
    "facts_present",
    "usage",
    "latency_ms",
}
_USAGE = {"inputTokens": 10, "outputTokens": 3}
Seen = dict[tuple[int, int], list[list[dict[str, object]]]]


@pytest.fixture(scope="module")
def corpus() -> ConversationCorpus:
    return load_conversation_corpus(_CORPUS)


class Scripted:
    def __init__(
        self,
        responses: list[dict[str, object]],
        seen: list[list[dict[str, object]]] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.seen = seen if seen is not None else []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.seen.append(deepcopy(messages))
        return self.responses.pop(0)


def _response(stop: str, content: list[dict[str, object]]) -> dict[str, object]:
    message = {"role": "assistant", "content": content}
    return {"output": {"message": message}, "stopReason": stop, "usage": _USAGE}


def _use(name: str, tool_input: dict[str, object]) -> dict[str, object]:
    call = {"toolUseId": "t1", "name": name, "input": tool_input}
    return _response("tool_use", [{"toolUse": call}])


def _text(value: str) -> dict[str, object]:
    return _response("end_turn", [{"text": value}])


def _only(corpus: ConversationCorpus, scenario_id: str) -> ConversationCorpus:
    chosen = [s for s in corpus.scenarios if s.id == scenario_id]
    return corpus.model_copy(update={"scenarios": chosen})


def _plan_ids(messages: list[dict[str, object]]) -> list[str]:
    content = cast(list[dict[str, str]], messages[-1]["content"])
    meals = json.loads(content[0]["text"])["plan_meals"]
    return [meal["recipe_id"] for meal in meals]


def test_a_run_emits_one_hash_only_record_per_repeat(
    corpus: ConversationCorpus,
) -> None:
    gold = corpus.scenarios[0].turns[0].expect.gold

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        return Scripted([_use("what_if_substitute", gold[0].input), _text("Swap ok.")])

    sub = _only(corpus, "C01")
    records = list(run_conversation_suite(sub, "nova-2-lite", provider_for))
    assert [r["repeat"] for r in records] == [1, 2, 3]
    for record in records:
        assert set(record) == _RECORD_KEYS
        assert record["scenario_id"] == "C01"
        assert record["turn"] == 1
        assert record["profile"] == "nova-2-lite"
        assert record["gate"] == "clean"
        assert record["reply_source"] == "model"
        assert record["verdict"] == {"ok": True, "reasons": [], "unmatched_count": 0}
        assert record["proposal"] is False
        assert record["facts_present"] == [True] * len(gold)
        assert record["usage"] == {
            "input": 20,
            "output": 6,
            "cache_read": 0,
            "cache_write": 0,
        }
        tools = cast(list[dict[str, Any]], record["tools"])
        assert [t["name"] for t in tools] == ["what_if_substitute"]
        assert tools[0]["inputs"]["recipe_id"] == "bean_tacos"
        assert isinstance(record["latency_ms"], int)
        assert len(cast(str, record["reply_sha256"])) == 64
        assert "Swap ok." not in json.dumps(record)


def test_an_unmatched_number_keeps_only_its_count(corpus: ConversationCorpus) -> None:
    gold = corpus.scenarios[0].turns[0].expect.gold

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        text = _text("It adds 999 kcal.")
        return Scripted([_use("what_if_substitute", gold[0].input), text])

    records = list(run_conversation_suite(_only(corpus, "C01"), "p", provider_for))
    assert records[0]["verdict"] == {
        "ok": False,
        "reasons": ["unmatched_number"],
        "unmatched_count": 1,
    }
    assert records[0]["reply_source"] == "template"
    assert "999" not in json.dumps(records[0])


def test_a_provider_failure_records_a_failed_turn_and_stops(
    corpus: ConversationCorpus,
) -> None:
    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        return Scripted([])

    records = list(run_conversation_suite(_only(corpus, "C11"), "p", provider_for))
    assert [(r["repeat"], r["turn"]) for r in records] == [(1, 1), (2, 1), (3, 1)]
    for record in records:
        assert record["status"] == "failed"
        assert record["reply_source"] == "none"
        assert record["reply_sha256"] is None
        assert record["gate"] is None
        assert record["tools"] == []
        assert not any(cast(list[bool], record["facts_present"]))
        assert set(cast(dict[str, object], record["usage"]).values()) == {None}


def test_apply_proposal_before_changes_the_plan_in_memory_only(
    corpus: ConversationCorpus,
) -> None:
    seen: Seen = {}
    operations = [{"op": "add", "recipe_id": "overnight_oats", "servings": 2}]

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        first = (
            _use("propose_plan_change", {"operations": operations})
            if turn == 1
            else _use("get_plan", {})
        )
        return Scripted([first, _text("Done.")], seen.setdefault((repeat, turn), []))

    sub = _only(corpus, "C07")
    records = list(run_conversation_suite(sub, "p", provider_for))
    assert len(records) == 6
    for repeat in (1, 2, 3):
        assert _plan_ids(seen[(repeat, 1)][0]) == ["bean_tacos"]
        assert _plan_ids(seen[(repeat, 2)][0]) == ["bean_tacos", "overnight_oats"]
    assert (records[0]["proposal"], records[0]["gate"]) == (True, "proposal")
    assert records[0]["reply_source"] == "template"
    assert records[1]["facts_present"] == [True, True]
    # An applied proposal never edits the corpus plan.
    assert [m.recipe_id for m in sub.scenarios[0].plan.meals] == ["bean_tacos"]


def test_no_proposal_is_applied_when_none_was_recorded(
    corpus: ConversationCorpus,
) -> None:
    seen: Seen = {}

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        script = (
            [_text("Which meal?")]
            if turn == 1
            else [_use("get_plan", {}), _text("Done.")]
        )
        return Scripted(script, seen.setdefault((repeat, turn), []))

    list(run_conversation_suite(_only(corpus, "C07"), "p", provider_for))
    assert _plan_ids(seen[(1, 2)][0]) == ["bean_tacos"]


def test_fact_presence_needs_the_tool_path_and_exact_typed_value() -> None:
    payloads: list[tuple[object, object]] = [
        ("get_plan", {"a": {"b": [{"c": 5}]}, "flag": 1})
    ]

    def gold(tool: str, path: str, value: bool | int | str) -> Gold:
        return Gold(tool=tool, input={}, path=path, value=value)

    assert runner._present(gold("get_plan", "a.b.0.c", 5), payloads)
    assert not runner._present(gold("get_plan", "a.b.0.c", 6), payloads)
    assert not runner._present(gold("get_plan", "a.b.1.c", 5), payloads)
    assert not runner._present(gold("get_plan", "a.x", 5), payloads)
    assert not runner._present(gold("get_meal", "a.b.0.c", 5), payloads)
    assert not runner._present(gold("get_plan", "a.b.0.c", "5"), payloads)
    assert not runner._present(gold("get_plan", "flag", True), payloads)


def test_the_matrix_turn_passes_exactly_todays_run_chat_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[tuple[object, ...], dict[str, object]]] = []
    real = chat_loop.run_chat

    def spy(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append((args, kwargs))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(chat_loop, "run_chat", spy)
    case: dict[str, object] = {
        "id": "turn-case",
        "messages": [
            {"role": "user", "content": "Plan a catalog meal."},
            {"role": "user", "content": "FUTURE_MESSAGE"},
        ],
        "inputs": {
            "user_id": 23,
            "now": "2026-10-03T12:00:00+00:00",
            "budget_period": "2026-10-01",
            "spending_period": "2026-10-01",
            "monthly_limit_cents": 20000,
            "posted_cents": 5000,
            "pending_cents": 300,
            "plan_cap_cents": 10000,
            "spending_refreshed_at": "2026-10-03T12:00:00+00:00",
            "followup_diet": "FUTURE_DIET",
        },
        "expected": {"answer": "GOLD_ANSWER", "total_cents": -999},
    }
    model_turn.observe_model_turn(
        prepare_case(case),
        "Plan a catalog meal.",
        Scripted([_text("Done.")]),
        markers=(),
        history=[],
        previous_request=None,
        record_evidence=lambda planning: "0" * 64,
    )
    assert len(seen) == 1
    args, kwargs = seen[0]
    assert len(args) == 4
    assert set(kwargs) == {
        "user_id",
        "spending_source",
        "previous_request",
        "previous_ingredient_ids",
        "history",
        "record_evidence",
        "plan_cap_cents",
        "observe_terminal_tool_results",
    }
    assert kwargs["user_id"] == 23
    assert kwargs["spending_source"] == "fixture"
    assert kwargs["plan_cap_cents"] == 10000


class _Marked(GoldFollowingProvider):
    """Gold-following provider whose final reply carries unique marker text."""

    def __init__(self, scenario: Scenario, turn: int, reply: str) -> None:
        super().__init__(scenario.turns[turn - 1])
        self._reply = reply

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        response = super().converse(system_prompt, messages, tools)
        output = cast(dict[str, Any], response["output"])
        for block in output["message"]["content"]:
            if "text" in block:
                block["text"] = self._reply
        return response


def _argv(out: Path) -> list[str]:
    options = {
        "--corpus": str(_CORPUS),
        "--output-dir": str(out),
        "--profile": "nova-2-lite",
        "--region": "us-east-1",
        "--revision": "a" * 40,
    }
    return [part for pair in options.items() for part in pair] + ["--fixture"]


def test_no_output_file_holds_reply_text(tmp_path: Path) -> None:
    word, number = "ZEPHYRMARKERWORD", "9173525"
    replies = {1: f"{word} is tidy.", 2: f"{word} adds {number} kcal.", 3: word}

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        return _Marked(scenario, turn, replies[repeat])

    out = tmp_path / "out"
    assert main(_argv(out), fixture_provider_for=provider_for) == 0
    names = ["slots.jsonl", "report.json", "report.md", "completion.json"]
    for name in names:
        text = (out / name).read_text(encoding="utf-8")
        assert word not in text
        assert number not in text
    lines = (out / "slots.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    flagged = [r for r in records if r["verdict"]["unmatched_count"] > 0]
    assert flagged
    assert all("unmatched_number" in r["verdict"]["reasons"] for r in flagged)
    assert any(r["reply_source"] == "model" for r in records)
