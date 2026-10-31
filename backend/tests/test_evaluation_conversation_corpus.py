import json
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from app.agent import ingredient_tool
from app.agent.chat_dispatch import dispatch
from app.agent.chat_loop import ChatUnavailable, run_chat
from app.agent.chat_messages import ToolCall
from app.agent.proposal_tool import PROPOSAL_TOOL
from app.domain.catalog import CATALOG_VERSION, RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS
from app.domain.plan_proposal import apply_operations, parse_operations
from app.domain.plan_revision import PlanRevisionInput, PlanSnapshot
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_conversation_corpus import (
    CORPUS_ERROR,
    SCENARIO_IDS,
    TOOL_NAMES,
    ConversationCorpus,
    load_conversation_corpus,
)

Json = dict[str, Any]
_PATH = Path(__file__).parent / "evaluation" / "conversation.json"
_REVISION_ID = UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture
def raw() -> Json:
    return cast(Json, json.loads(_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def corpus() -> ConversationCorpus:
    return load_conversation_corpus(_PATH)


def _reject(tmp_path: Path, data: Json) -> None:
    path = tmp_path / "conversation.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_conversation_corpus(path)
    assert str(error.value) == CORPUS_ERROR


def _turn(data: Json, scenario: int, turn: int = 0) -> Json:
    return cast(Json, data["scenarios"][scenario]["turns"][turn])


def test_real_corpus_loads(corpus: ConversationCorpus) -> None:
    assert corpus.version == "conversation-eval-v1"
    assert corpus.repeats == 3
    assert corpus.catalog_version == CATALOG_VERSION
    assert tuple(scenario.id for scenario in corpus.scenarios) == SCENARIO_IDS
    turns = {scenario.id: len(scenario.turns) for scenario in corpus.scenarios}
    assert turns["C04"] == 2
    assert turns["C07"] == 2
    assert turns["C11"] == 9
    outcomes = {
        outcome
        for scenario in corpus.scenarios
        for turn in scenario.turns
        for outcome in turn.expect.outcomes
    }
    assert outcomes == {"prose", "template", "clarification", "proposal"}


class _Recorder:
    def __init__(self) -> None:
        self.names: set[str] = set()

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.names = {cast(Json, spec["toolSpec"])["name"] for spec in tools}
        raise RuntimeError("recorded")


def _propose(operations: list[dict[str, object]]) -> str:
    return "proposal-fixture"


def _offered(corpus: ConversationCorpus, *, propose: bool) -> set[str]:
    scenario = corpus.scenarios[0]
    recorder = _Recorder()
    with pytest.raises(ChatUnavailable):
        run_chat(
            recorder,
            "What does my plan cost?",
            fixture_budget(scenario.inputs.model_dump()),
            date.fromisoformat(scenario.inputs.budget_period),
            plan_revision=PlanRevisionInput(id=_REVISION_ID, snapshot=scenario.plan),
            propose=_propose if propose else None,
        )
    assert recorder.names
    return recorder.names


def test_tool_names_are_what_run_chat_registers(corpus: ConversationCorpus) -> None:
    offered = _offered(corpus, propose=True)
    assert PROPOSAL_TOOL in offered
    assert offered == TOOL_NAMES
    assert _offered(corpus, propose=False) == TOOL_NAMES - {PROPOSAL_TOOL}


def test_every_corpus_tool_is_registered(corpus: ConversationCorpus) -> None:
    used = {
        name
        for scenario in corpus.scenarios
        for turn in scenario.turns
        for name in (
            *turn.expect.tools_any,
            *turn.expect.tools_forbidden,
            *(item.tool for item in turn.expect.gold),
        )
    }
    assert used <= _offered(corpus, propose=True)


def _set(path: list[Any], key: str, value: object) -> Callable[[Json], None]:
    def mutate(data: Json) -> None:
        target: Any = data
        for part in path:
            target = target[part]
        target[key] = value

    return mutate


def _delete(path: list[Any], key: str) -> Callable[[Json], None]:
    def mutate(data: Json) -> None:
        target: Any = data
        for part in path:
            target = target[part]
        del target[key]

    return mutate


def _drop_last_scenario(data: Json) -> None:
    data["scenarios"].pop()


def _swap_first_two(data: Json) -> None:
    first, second = data["scenarios"][:2]
    data["scenarios"][:2] = [second, first]


def _apply_twice_for_one_proposal(data: Json) -> None:
    turns = data["scenarios"][6]["turns"]
    turns.append(deepcopy(turns[1]))


_FOUR_MEALS = [
    {"recipe_id": recipe_id, "servings": 1}
    for recipe_id in (
        "bean_tacos",
        "chicken_and_rice_bowls",
        "lentil_soup",
        "vegetable_pasta",
    )
]
_TURN = ["scenarios", 0, "turns", 0]
_EXPECT = [*_TURN, "expect"]
_GOLD = [*_EXPECT, "gold", 0]
_RULES: dict[str, Callable[[Json], None]] = {
    "version": _set([], "version", "grocery-eval-v1"),
    "repeats": _set([], "repeats", 2),
    "catalog_version": _set([], "catalog_version", "sample-prices-v1"),
    "eleven_scenarios": _drop_last_scenario,
    "duplicate_id": _set(["scenarios", 1], "id", "C01"),
    "out_of_order": _swap_first_two,
    "unknown_recipe": _set(
        ["scenarios", 0, "plan", "meals", 0], "recipe_id", "unknown_meal"
    ),
    "servings_out_of_range": _set(["scenarios", 0, "plan", "meals", 0], "servings", 9),
    "unknown_pantry_id": _set(
        ["scenarios", 0, "plan"], "pantry_ingredient_ids", ["unobtainium"]
    ),
    "unknown_tool_any": _set(_EXPECT, "tools_any", ["decline"]),
    "unknown_tool_forbidden": _set(_EXPECT, "tools_forbidden", ["kroger_cart"]),
    "unknown_gold_tool": _set(_GOLD, "tool", "decline"),
    "forbidden_and_required": _set(_EXPECT, "tools_forbidden", ["what_if_substitute"]),
    "apply_before_any_proposal": _set(_TURN, "apply_proposal_before", True),
    "apply_after_non_proposal": _set(
        ["scenarios", 3, "turns", 1], "apply_proposal_before", True
    ),
    "apply_twice_for_one_proposal": _apply_twice_for_one_proposal,
    "no_meals": _set(["scenarios", 0, "plan"], "meals", []),
    "four_meals": _set(["scenarios", 0, "plan"], "meals", _FOUR_MEALS),
    "plan_cap_not_in_plan": _set(["scenarios", 5, "plan"], "plan_cap_cents", None),
    "plan_cap_not_in_inputs": _set(["scenarios", 5, "inputs"], "plan_cap_cents", None),
    "plan_cap_differs": _set(["scenarios", 5, "plan"], "plan_cap_cents", 4000),
    "empty_outcomes": _set(_EXPECT, "outcomes", []),
    "unknown_outcome": _set(_EXPECT, "outcomes", ["refusal"]),
    "repeated_outcome": _set(_EXPECT, "outcomes", ["prose", "prose"]),
    "empty_user": _set(_TURN, "user", ""),
    "long_user": _set(_TURN, "user", "x" * 501),
    "no_turns": _set(["scenarios", 0], "turns", []),
    "gold_float_value": _set(_GOLD, "value", 1.5),
    "gold_empty_path": _set(_GOLD, "path", ""),
    "missing_inputs_key": _delete(["scenarios", 0, "inputs"], "diet"),
    "inputs_wrong_type": _set(["scenarios", 0, "inputs"], "posted_cents", "0"),
    "inputs_has_meals": _set(["scenarios", 0, "inputs"], "meals", []),
    "unknown_corpus_key": _set([], "mode_note", "x"),
    "unknown_scenario_key": _set(["scenarios", 0], "group", "x"),
    "unknown_inputs_key": _set(["scenarios", 0, "inputs"], "extra", 1),
    "unknown_plan_key": _set(["scenarios", 0, "plan"], "extra", 1),
    "unknown_turn_key": _set(_TURN, "extra", 1),
    "unknown_expect_key": _set(_EXPECT, "extra", 1),
    "unknown_gold_key": _set(_GOLD, "extra", 1),
}


@pytest.mark.parametrize("rule", _RULES)
def test_each_rule_rejects_a_bad_copy(tmp_path: Path, raw: Json, rule: str) -> None:
    bad = deepcopy(raw)
    _RULES[rule](bad)
    _reject(tmp_path, bad)


def test_a_new_proposal_turn_allows_another_apply(tmp_path: Path, raw: Json) -> None:
    turns = raw["scenarios"][6]["turns"]
    turns.extend(deepcopy(turns))
    path = tmp_path / "conversation.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_conversation_corpus(path)
    flags = [turn.apply_proposal_before for turn in loaded.scenarios[6].turns]
    assert flags == [False, True, False, True]


def test_missing_and_malformed_files_use_the_fixed_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as missing:
        load_conversation_corpus(tmp_path / "absent.json")
    assert str(missing.value) == CORPUS_ERROR
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError) as malformed:
        load_conversation_corpus(broken)
    assert str(malformed.value) == CORPUS_ERROR


def _at(payload: object, path: str) -> object:
    for part in path.split("."):
        if isinstance(payload, list):
            payload = payload[int(part)]
        else:
            payload = cast(Json, payload)[part]
    return payload


def test_gold_regenerates_from_the_tools(
    corpus: ConversationCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingredient_tool, "_live_client", lambda: None)
    checked = 0
    for scenario in corpus.scenarios:
        inputs = scenario.inputs.model_dump()
        budget = fixture_budget(inputs)
        period = date.fromisoformat(scenario.inputs.budget_period)
        plan = PlanRevisionInput(id=_REVISION_ID, snapshot=scenario.plan)
        proposed: list[dict[str, object]] | None = None
        for number, turn in enumerate(scenario.turns, start=1):
            where = f"{scenario.id} turn {number}"
            if turn.apply_proposal_before:
                assert proposed is not None, where
                snapshot = apply_operations(plan.snapshot, parse_operations(proposed))
                plan = PlanRevisionInput(id=_REVISION_ID, snapshot=snapshot)
                proposed = None
            for gold in turn.expect.gold:
                call = ToolCall("gold", gold.tool, deepcopy(gold.input))
                trace: list[dict[str, object]] = []
                payload, _ = dispatch(
                    call,
                    budget,
                    period,
                    scenario.inputs.user_id,
                    "fixture",
                    trace,
                    plan=plan,
                    propose=lambda operations: "proposal-fixture",
                )
                assert payload is not None, f"{where}: {gold.tool} failed"
                got = _at(payload, gold.path)
                assert got == gold.value, f"{where}: {gold.tool} {gold.path}"
                assert type(got) is type(gold.value), f"{where}: {gold.path}"
                checked += 1
                if gold.tool == PROPOSAL_TOOL:
                    proposed = cast(list[dict[str, object]], gold.input["operations"])
    assert checked == sum(
        len(turn.expect.gold) for s in corpus.scenarios for turn in s.turns
    )


def test_plan_snapshots_validate(corpus: ConversationCorpus) -> None:
    for scenario in corpus.scenarios:
        PlanSnapshot.model_validate(scenario.plan.model_dump())


def test_c05_false_premise_holds(corpus: ConversationCorpus) -> None:
    scenario = corpus.scenarios[4]
    assert scenario.id == "C05"
    assert "chicken" in scenario.turns[0].user.lower()
    for meal in scenario.plan.meals:
        ids = [item for item, _ in RECIPES[meal.recipe_id].ingredients]
        names = [ALL_INGREDIENTS[item].name.lower() for item in ids]
        assert not any("chicken" in text for text in [*ids, *names])
