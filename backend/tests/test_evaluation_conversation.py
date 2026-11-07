import json
import re
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from app import evaluation_conversation as runner
from app import evaluation_model_turn as model_turn
from app.agent import chat_loop, grounding
from app.agent.catalog_tool import execute_catalog_search
from app.agent.chat_refusal import GUARDRAIL_DECLINE
from app.agent.provider import LLMProvider
from app.domain.plan_proposal import ProposalInvalid
from app.evaluate_conversation import GoldFollowingProvider, main
from app.evaluation_conversation import run_conversation_suite
from app.evaluation_conversation_corpus import (
    ConversationCorpus,
    Gold,
    Scenario,
    load_conversation_corpus,
)
from app.evaluation_conversation_score import (
    build_report,
    render_markdown,
    score_turn,
)
from app.evaluation_inputs import prepare_case
from app.evaluation_manifest import _hash, catalog_snapshot
from tests.test_search_recovery import terminal_search

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
    "provider_requests",
    "latency_ms",
    "apply_error",
    "purchase_signals",
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
        assert type(record["provider_requests"]) is int
        assert record["provider_requests"] == 2
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
        assert type(record["provider_requests"]) is int
        assert record["provider_requests"] == 1
        assert not any(cast(list[bool], record["facts_present"]))
        assert set(cast(dict[str, object], record["usage"]).values()) == {None}


def test_selection_normalizes_order_and_limits_runner_pairs(
    corpus: ConversationCorpus,
) -> None:
    raw = runner.ConversationSelection.model_validate(
        {
            "scenarios": [
                {"scenario_id": "C16", "repeats": [1]},
                {"scenario_id": "C11", "repeats": [1]},
                {"scenario_id": "C09", "repeats": [3, 2, 1]},
                {"scenario_id": "C08", "repeats": [3, 2, 1]},
                {"scenario_id": "C01", "repeats": [3, 2, 1]},
            ]
        }
    )
    selection = runner.normalize_selection(corpus, raw)
    normalized = [(item.scenario_id, item.repeats) for item in selection.scenarios]
    assert normalized == [
        ("C01", [1, 2, 3]),
        ("C08", [1, 2, 3]),
        ("C09", [1, 2, 3]),
        ("C11", [1]),
        ("C16", [1]),
    ]
    assert runner.logical_chat_turn_count(corpus, selection) == 22

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        return GoldFollowingProvider(scenario.turns[index - 1])

    records = list(
        run_conversation_suite(corpus, "p", provider_for, selection=selection)
    )
    assert len(records) == 22
    assert {(record["scenario_id"], record["repeat"]) for record in records} == {
        ("C01", 1),
        ("C01", 2),
        ("C01", 3),
        ("C08", 1),
        ("C08", 2),
        ("C08", 3),
        ("C09", 1),
        ("C09", 2),
        ("C09", 3),
        ("C11", 1),
        ("C16", 1),
    }
    assert all(type(record["provider_requests"]) is int for record in records)


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

    records = list(run_conversation_suite(_only(corpus, "C07"), "p", provider_for))
    assert _plan_ids(seen[(1, 2)][0]) == ["bean_tacos"]
    assert [r["apply_error"] for r in records] == [None, "missing"] * 3


def test_a_proposal_that_fails_to_apply_is_recorded_and_fails_the_turn(
    corpus: ConversationCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: Seen = {}
    operations = [{"op": "add", "recipe_id": "overnight_oats", "servings": 2}]

    def refuse(*args: object) -> object:
        raise ProposalInvalid("rejected")

    monkeypatch.setattr(runner, "apply_operations", refuse)

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        first = (
            _use("propose_plan_change", {"operations": operations})
            if turn == 1
            else _use("get_plan", {})
        )
        return Scripted([first, _text("Done.")], seen.setdefault((repeat, turn), []))

    sub = _only(corpus, "C07")
    records = list(run_conversation_suite(sub, "p", provider_for))
    assert [r["apply_error"] for r in records] == [None, "invalid"] * 3
    assert _plan_ids(seen[(1, 2)][0]) == ["bean_tacos"]
    scores = score_turn(sub.scenarios[0].turns[1], records[1])
    assert not scores["gold"]
    assert not scores["outcome"]


_REPLIES_BY_CODE = {
    "unsupported_character": "Snow ☃ today.",
    "empty": "",
    "too_long": "word " * 300,
    "store_price": "Kroger sells it.",
    "forbidden_claim": "This is medical advice.",
    "number_word": "It takes several meals.",
    "unmatched_number": "It adds 99999 kcal.",
    "medical_claim": "It may raise your blood sugar.",
}


def test_the_reason_allowlist_is_every_code_the_validator_can_emit() -> None:
    emitted: set[str] = set()
    for code, reply in _REPLIES_BY_CODE.items():
        reasons = grounding.validate(reply, grounding.FactSet()).reasons
        assert code in reasons
        emitted.update(reasons)
    assert emitted == set(grounding.REASON_CODES)
    assert runner.REASONS == grounding.REASON_CODES


def test_the_gate_allowlist_covers_every_reason_the_chat_loop_records() -> None:
    source = Path(chat_loop.__file__).read_text(encoding="utf-8")
    recorded = set(re.findall(r'(?:why\(|gate = |"gate": )"(\w+)"', source))
    assert recorded
    assert recorded <= runner.GATES
    assert {"refusal", "incomplete", "limit"} <= runner.GATES
    assert {"planned_terminal", "discovery_terminal", "guardrail"} <= runner.GATES


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


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "lower carb pasta"},
        {"query": "vegetarian pasta", "exclude": ["pasta"], "offset": 3},
    ],
)
def test_c18_rejects_searches_without_the_gluten_constraint(
    corpus: ConversationCorpus, arguments: dict[str, object]
) -> None:
    turn = corpus.scenarios[17].turns[0]
    payloads: list[tuple[object, object]] = [
        ("search_meals", execute_catalog_search(arguments))
    ]
    facts = [runner._present(item, payloads) for item in turn.expect.gold]
    assert not all(facts)
    record: dict[str, object] = {
        "tools": [{"name": "search_meals"}],
        "reply_source": "template",
        "status": "clarification",
        "gate": "discovery_terminal",
        "facts_present": facts,
        "apply_error": None,
    }
    assert not score_turn(turn, record)["gold"]


@pytest.mark.parametrize(
    ("scenario_id", "arguments"),
    [
        ("C16", {"query": "vegetarian", "limit": 3, "diet": "vegan"}),
        ("C18", {"query": "gluten-free pasta", "diet": "vegan"}),
    ],
)
def test_a_search_with_an_unrequested_diet_fails_the_total_matches_gold(
    corpus: ConversationCorpus, scenario_id: str, arguments: dict[str, object]
) -> None:
    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        if turn != 1:
            return Scripted([])
        return Scripted([_use("search_meals", arguments), _text("Done.")])

    sub = _only(corpus, scenario_id)
    records = run_conversation_suite(sub, "p", provider_for)
    first = [r for r in records if r["turn"] == 1]
    gold = sub.scenarios[0].turns[0].expect.gold
    index = next(i for i, item in enumerate(gold) if item.path == "total_matches")
    assert gold[index].value == 28
    for record in first:
        facts = cast(list[bool], record["facts_present"])
        assert facts[index] is False
        assert not score_turn(sub.scenarios[0].turns[0], record)["gold"]


def test_page_reference_rejects_repeated_or_skipped_pages(
    corpus: ConversationCorpus,
) -> None:
    page = corpus.scenarios[15].turns[1].expect.gold[0]
    for offset in (0, 2):
        payload = execute_catalog_search(
            {"query": "vegetarian", "limit": 1, "offset": offset}
        )
        assert not runner._present(page, [("search_meals", payload)])


@pytest.mark.parametrize("cursor_result", ["retained", "invalid", "missing"])
def test_search_cursor_reaches_model_context_on_each_turn(
    corpus: ConversationCorpus, monkeypatch: pytest.MonkeyPatch, cursor_result: str
) -> None:
    seen: dict[tuple[int, int], dict[str, object]] = {}
    real = chat_loop.run_chat

    def with_budget_result(*args: object, **kwargs: object) -> dict[str, object]:
        result = real(*args, **kwargs)  # type: ignore[arg-type]
        if args[1] == "What is my budget?":
            if cursor_result == "retained":
                result["next_search"] = kwargs.get("previous_search")
            elif cursor_result == "invalid":
                result["next_search"] = {"query": ""}
            else:
                result.pop("next_search", None)
        return result

    monkeypatch.setattr(chat_loop, "run_chat", with_budget_result)

    class ContextProvider:
        def __init__(self, repeat: int, turn: int) -> None:
            self.repeat = repeat
            self.turn = turn
            self.step = 0

        def converse(
            self,
            system_prompt: str,
            messages: list[dict[str, object]],
            tools: list[dict[str, object]],
        ) -> dict[str, object]:
            self.step += 1
            if self.step > 1:
                return _text("Done.")
            content = cast(list[dict[str, str]], messages[-1]["content"])
            context = cast(dict[str, object], json.loads(content[0]["text"]))
            seen[(self.repeat, self.turn)] = context
            if self.turn == 3:
                return _use("get_budget_summary", {})
            cursor = context.get("previous_search")
            arguments = (
                {"query": "vegetarian", "limit": 1}
                if self.turn == 1 or not isinstance(cursor, dict)
                else cursor
            )
            return _use("search_meals", arguments)

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        return ContextProvider(repeat, turn)

    sub = _only(corpus, "C16")
    records = list(run_conversation_suite(sub, "p", provider_for))
    assert len(records) == 12
    for repeat in (1, 2, 3):
        assert seen[(repeat, 1)]["previous_search"] is None
        cursor1 = cast(dict[str, object], seen[(repeat, 2)]["previous_search"])
        cursor2 = cast(dict[str, object], seen[(repeat, 3)]["previous_search"])
        assert cursor1["offset"] == 1
        assert cursor2["offset"] == 2
        expected = cursor2 if cursor_result == "retained" else None
        assert seen[(repeat, 4)]["previous_search"] == expected
        if cursor_result == "retained":
            own = [record for record in records if record["repeat"] == repeat]
            assert all(
                all(score_turn(turn, record).values())
                for turn, record in zip(sub.scenarios[0].turns, own, strict=True)
            )


def test_evaluation_keeps_exhaustion_and_drops_blocked_history(
    corpus: ConversationCorpus,
) -> None:
    original = corpus.scenarios[15]
    users = [
        "vegetarian meals",
        "What is my budget?",
        "more, but vegan",
        "more",
        "Start over",
        "more",
    ]
    scenario = original.model_copy(
        update={
            "turns": [
                original.turns[0].model_copy(
                    update={"user": user, "apply_proposal_before": False}
                )
                for user in users
            ],
        }
    )
    sub = corpus.model_copy(update={"scenarios": [scenario]})
    exhausted = terminal_search({"query": "vegetarian"})
    seen: Seen = {}

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        script = [_text("Done.")]
        if turn == 1:
            script = [_use("search_meals", exhausted)]
        elif turn == 2:
            script.insert(0, _use("get_budget_summary", {}))
        elif turn == 3:
            script = [
                _response("guardrail_intervened", [{"text": "blocked-eval-output"}])
            ]
        elif turn in (4, 6):
            script = [_use("search_meals", {"query": "chicken"})]
        return Scripted(script, seen.setdefault((repeat, turn), []))

    records = list(run_conversation_suite(sub, "p", provider_for))
    assert len(records) == len(users) * 3
    no_more_hash = sha256(b"There are no more matching meals.").hexdigest()
    for repeat in (1, 2, 3):
        own = [record for record in records if record["repeat"] == repeat]
        assert own[2]["gate"] == "guardrail"
        assert own[3]["reply_sha256"] == no_more_hash
        assert own[3]["tools"] == []
        for turn in (2, 3, 4, 5):
            messages = seen[(repeat, turn)][0]
            content = cast(list[dict[str, str]], messages[-1]["content"])
            context = json.loads(content[0]["text"])
            assert context["previous_search"] is None
            assert context["previous_exhausted_search"] == exhausted
        after = seen[(repeat, 4)][0]
        assert users[2] not in json.dumps(after)
        assert "blocked-eval-output" not in json.dumps(after)
        assert GUARDRAIL_DECLINE not in json.dumps(after)
        content = cast(list[dict[str, str]], seen[(repeat, 6)][0][-1]["content"])
        context = json.loads(content[0]["text"])
        assert context["previous_search"] == {**exhausted, "offset": 0}
        assert context["previous_exhausted_search"] is None
        assert own[5]["tools"]


def test_evaluation_cannot_apply_a_proposal_from_a_blocked_turn(
    corpus: ConversationCorpus,
) -> None:
    seen: Seen = {}
    operations = [{"op": "add", "recipe_id": "overnight_oats", "servings": 2}]

    def provider_for(scenario: Scenario, repeat: int, turn: int) -> LLMProvider:
        script = [_use("get_plan", {}), _text("Done.")]
        if turn == 1:
            script = [
                _use("propose_plan_change", {"operations": operations}),
                _response(
                    "guardrail_intervened", [{"text": "blocked-proposal-output"}]
                ),
            ]
        return Scripted(script, seen.setdefault((repeat, turn), []))

    records = list(run_conversation_suite(_only(corpus, "C07"), "p", provider_for))
    assert len(records) == 6
    for repeat in (1, 2, 3):
        own = [record for record in records if record["repeat"] == repeat]
        assert own[0]["gate"] == "guardrail" and own[0]["proposal"] is False
        assert own[1]["apply_error"] == "missing"
        assert _plan_ids(seen[(repeat, 2)][0]) == ["bean_tacos"]
        assert len(seen[(repeat, 2)][0]) == 1
        assert "blocked-proposal-output" not in json.dumps(seen[(repeat, 2)])
        assert GUARDRAIL_DECLINE not in json.dumps(seen[(repeat, 2)])


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


def test_a_fixture_run_writes_manifest_identity_covered_by_the_hash(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    assert main(_argv(out)) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    manifest = report["manifest"]
    assert manifest["suite_version"] == "conversation-eval-v1.5"
    assert manifest["catalog_hash"] == _hash(catalog_snapshot())
    assert manifest["system_prompt_hash"] == _hash(chat_loop.SYSTEM_PROMPT)
    covered = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    assert report["manifest_hash"] == manifest["manifest_hash"] == _hash(covered)
    for key in ("suite_version", "catalog_hash", "system_prompt_hash"):
        changed = {**covered, key: "changed"}
        assert _hash(changed) != manifest["manifest_hash"]


def test_scenario_pass_counts_a_repeat_only_when_every_turn_has_every_gold_fact(
    corpus: ConversationCorpus,
) -> None:
    sub = _only(corpus, "C16")
    records: list[dict[str, object]] = []
    for repeat in (1, 2, 3):
        for number, turn in enumerate(sub.scenarios[0].turns, start=1):
            present = [True] * len(turn.expect.gold)
            if (repeat, number) == (2, 3):
                present[0] = False
            records.append(
                {
                    "scenario_id": "C16",
                    "repeat": repeat,
                    "turn": number,
                    "facts_present": present,
                    "apply_error": None,
                }
            )
    report = build_report(sub, records, {"manifest_hash": "x"})
    assert report["scenario_pass"] == {"passed": 2, "total": 3, "rate": 0.6667}
    gold = cast(dict[str, Any], report["checks"])["gold"]
    assert (gold["passed"], gold["total"]) == (11, 12)
    assert "- rate: 0.6667" in render_markdown(report)
    none = sub.model_copy(update={"scenarios": []})
    empty = build_report(none, [], {"manifest_hash": "x"})
    assert cast(dict[str, Any], empty["scenario_pass"])["rate"] is None


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
    assert all(type(record["provider_requests"]) is int for record in records)
    assert all(
        "reply_text" not in record and "unmatched" not in record for record in records
    )
