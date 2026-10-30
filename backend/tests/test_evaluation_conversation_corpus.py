import json
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from app.agent import ingredient_tool
from app.agent.budget_tool import budget_tool_spec
from app.agent.catalog_tool import catalog_tool_spec
from app.agent.chat_dispatch import dispatch
from app.agent.chat_messages import ToolCall
from app.agent.ingredient_tool import ingredient_tool_spec
from app.agent.plan_tools import get_meal_tool_spec, get_plan_tool_spec
from app.agent.planning_tool import planner_tool_spec
from app.agent.price_tool import price_tool_spec
from app.agent.proposal_tool import PROPOSAL_TOOL, proposal_tool_spec
from app.agent.substitute_tool import substitute_tool_spec
from app.domain.catalog import CATALOG_VERSION
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


def test_tool_names_match_the_registered_specs() -> None:
    specs = [
        planner_tool_spec(),
        budget_tool_spec(),
        catalog_tool_spec(),
        get_plan_tool_spec(),
        get_meal_tool_spec(),
        substitute_tool_spec(),
        price_tool_spec(),
        ingredient_tool_spec(),
        proposal_tool_spec(),
    ]
    names = {cast(Json, spec["toolSpec"])["name"] for spec in specs}
    assert names == TOOL_NAMES


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
        assert scenario.plan.plan_cap_cents == scenario.inputs.plan_cap_cents
