import json
from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import NoReturn, cast

import pytest

from app import evaluation_matrix
from app.evaluation_matrix import (
    MODEL_CASE_IDS,
    REFERENCE_CASE_IDS,
    EvaluationSlot,
    prepare_matrix,
)

_MODEL_IDS = frozenset(
    {"F01", "F02", "F04", "F05", "X02", "X03", "X04", "A01", "A02", "A03", "A04"}
)
_REFERENCE_IDS = frozenset({"F01", "F02", "F05", "X04", "A01"})
_ERROR = "corpus MUST match the finite JSON grocery-eval-v1 matrix contract"


@pytest.fixture
def corpus() -> dict[str, object]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    return cast(dict[str, object], json.loads(path.read_text()))


def _cases(corpus: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], corpus["scenarios"])


def _routing(slots: list[EvaluationSlot]) -> list[tuple[str, str, int, str]]:
    return [(slot.condition, slot.case_id, slot.repeat, slot.driver) for slot in slots]


def _reject(corpus: dict[str, object]) -> None:
    with pytest.raises(ValueError) as error:
        prepare_matrix(corpus)
    assert str(error.value) == _ERROR


def test_matrix_counts_repeats_and_unique_keys(corpus: dict[str, object]) -> None:
    slots = prepare_matrix(corpus)
    assert len(slots) == 138
    assert Counter(slot.condition for slot in slots) == {
        "tool_enabled": 33,
        "controlled_fixture": 15,
        "deterministic_fixture": 42,
        "no_tool": 33,
        "deterministic": 15,
    }
    keys = [(slot.condition, slot.case_id, slot.repeat) for slot in slots]
    assert len(set(keys)) == 138
    repeats = Counter((condition, case_id) for condition, case_id, _ in keys)
    assert set(repeats.values()) == {3}
    assert {slot.repeat for slot in slots} == {1, 2, 3}
    assert all(type(slot.repeat) is int for slot in slots)
    for condition, scope in (
        ("tool_enabled", _MODEL_IDS),
        ("no_tool", _MODEL_IDS),
        ("deterministic", _REFERENCE_IDS),
        ("controlled_fixture", frozenset({"P01", "P02", "P03", "P04", "P05"})),
    ):
        assert {slot.case_id for slot in slots if slot.condition == condition} == scope
    assert Counter(slot.driver for slot in slots) == {
        "model": 33,
        "refresh": 3,
        "handoff": 3,
        "protocol": 6,
        "duplicate": 3,
        "budget": 15,
        "meals": 21,
        "followup": 3,
        "missing": 3,
        "no_tool": 33,
        "reference": 15,
    }
    for slot in slots[:90]:
        if slot.driver in {"budget", "meals", "followup", "missing"}:
            assert slot.driver == slot.case["group"]


def test_exported_scopes_match_frozen_contract() -> None:
    assert type(MODEL_CASE_IDS) is frozenset
    assert type(REFERENCE_CASE_IDS) is frozenset
    assert MODEL_CASE_IDS == _MODEL_IDS
    assert REFERENCE_CASE_IDS == _REFERENCE_IDS


@pytest.mark.parametrize("reverse", [False, True])
def test_matrix_order_follows_corpus(corpus: dict[str, object], reverse: bool) -> None:
    if reverse:
        _cases(corpus).reverse()
    ids = [cast(str, case["id"]) for case in _cases(corpus)]
    slots = prepare_matrix(corpus)
    assert [(slot.case_id, slot.repeat) for slot in slots[:90]] == [
        (case_id, repeat) for case_id in ids for repeat in (1, 2, 3)
    ]
    assert [(slot.case_id, slot.repeat) for slot in slots[90:123]] == [
        (case_id, repeat)
        for case_id in ids
        if case_id in _MODEL_IDS
        for repeat in (1, 2, 3)
    ]
    assert [(slot.case_id, slot.repeat) for slot in slots[123:]] == [
        (case_id, repeat)
        for case_id in ids
        if case_id in _REFERENCE_IDS
        for repeat in (1, 2, 3)
    ]
    assert _routing(prepare_matrix(corpus)) == _routing(slots)


def test_p04_is_only_a_controlled_protocol_case(corpus: dict[str, object]) -> None:
    slots = [slot for slot in prepare_matrix(corpus) if slot.case_id == "P04"]
    assert len(slots) == 3
    assert {slot.condition for slot in slots} == {"controlled_fixture"}
    assert {slot.driver for slot in slots} == {"protocol"}
    assert all(slot.case["requires_model"] is True for slot in slots)
    provider_drivers = {
        "P01": "refresh",
        "P02": "handoff",
        "P03": "protocol",
        "P04": "protocol",
        "P05": "duplicate",
    }
    for slot in prepare_matrix(corpus):
        if slot.case_id in provider_drivers:
            assert slot.condition == "controlled_fixture"
            assert slot.driver == provider_drivers[slot.case_id]


def test_copies_are_isolated_from_caller_and_other_slots(
    corpus: dict[str, object],
) -> None:
    original = deepcopy(corpus)
    slots = prepare_matrix(corpus)
    assert corpus == original
    assert len({id(slot.case) for slot in slots}) == 138
    copies = [slot for slot in slots if slot.case_id == "F01"]
    assert len(copies) == 9
    frozen = deepcopy(copies[1].case)
    messages = cast(list[dict[str, object]], copies[0].case["messages"])
    messages[0]["content"] = "changed"
    cast(dict[str, object], copies[0].case["expected"])["accepted"] = "changed"
    assert all(slot.case == frozen for slot in copies[1:])
    assert corpus == original
    source = next(case for case in _cases(corpus) if case["id"] == "F01")
    cast(dict[str, object], source["inputs"])["diet"] = "changed"
    assert all(slot.case == frozen for slot in copies[1:])
    fresh = prepare_matrix(original)
    assert next(slot.case for slot in fresh if slot.case_id == "F01") == frozen
    with pytest.raises(FrozenInstanceError):
        copies[0].condition = "changed"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("version", "grocery-eval-v2"),
        ("version", None),
        ("catalog_version", "sample-prices-v1"),
        ("catalog_version", None),
        ("repeats", True),
        ("repeats", False),
        ("repeats", 3.0),
        ("repeats", "3"),
        ("repeats", 2),
        ("repeats", 4),
        ("scenarios", []),
        ("scenarios", {}),
        ("scenarios", None),
    ],
)
def test_invalid_corpus_headers(
    corpus: dict[str, object], key: str, value: object
) -> None:
    corpus[key] = value
    _reject(corpus)


@pytest.mark.parametrize("key", ["version", "catalog_version", "repeats", "scenarios"])
def test_missing_corpus_headers(corpus: dict[str, object], key: str) -> None:
    del corpus[key]
    _reject(corpus)


@pytest.mark.parametrize("change", ["duplicate", "missing", "unknown", "extra"])
def test_exact_current_case_ids(corpus: dict[str, object], change: str) -> None:
    cases = _cases(corpus)
    if change == "duplicate":
        cases[-1] = deepcopy(cases[0])
    elif change == "missing":
        cases.pop()
    elif change == "unknown":
        cases[-1]["id"] = "A05"
    else:
        cases.append(deepcopy(cases[0]))
    _reject(corpus)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", None),
        ("id", ""),
        ("id", []),
        ("group", "meals"),
        ("group", None),
        ("requires_model", True),
        ("requires_model", 0),
        ("requires_model", None),
        ("prompt", " "),
        ("messages", []),
        ("messages", {}),
        ("messages", [None]),
        ("messages", [{}]),
        ("messages", [{"role": "user", "content": ""}]),
        ("messages", [{"role": "tool", "content": "text"}]),
        ("messages", [{"role": "user", "content": 1}]),
        ("inputs", {}),
        ("inputs", []),
        ("expected", {}),
        ("expected", []),
        ("fixture_behavior", {}),
        ("fixture_behavior", []),
        ("fixture_behavior", {"kind": "fixture"}),
        ("fixture_behavior", {"kind": "", "provider": "fake"}),
    ],
)
def test_invalid_row_shapes(corpus: dict[str, object], key: str, value: object) -> None:
    _cases(corpus)[0][key] = value
    _reject(corpus)


@pytest.mark.parametrize(
    "key",
    [
        "id",
        "group",
        "requires_model",
        "prompt",
        "messages",
        "inputs",
        "expected",
        "fixture_behavior",
    ],
)
def test_missing_row_fields(corpus: dict[str, object], key: str) -> None:
    del _cases(corpus)[0][key]
    _reject(corpus)


def test_requires_model_matches_every_frozen_case(corpus: dict[str, object]) -> None:
    for index, case in enumerate(_cases(corpus)):
        malformed = deepcopy(corpus)
        _cases(malformed)[index]["requires_model"] = not case["requires_model"]
        _reject(malformed)
    p04 = next(case for case in _cases(corpus) if case["id"] == "P04")
    p04["requires_model"] = 1
    _reject(corpus)


def test_groups_match_every_frozen_case(corpus: dict[str, object]) -> None:
    for index, case in enumerate(_cases(corpus)):
        malformed = deepcopy(corpus)
        wrong_group = "meals" if case["group"] == "budget" else "budget"
        _cases(malformed)[index]["group"] = wrong_group
        _reject(malformed)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("domain_calls", None),
        ("domain_calls", ["calculate_budget"]),
        ("domain_calls", [{"name": "calculate_budget", "expectation": []}]),
        ("model_tools", {}),
        ("model_tools", [{"name": "plan_groceries"}]),
        ("model_tools", [{"name": "", "arguments": {}}]),
        ("unnecessary_model_tools", [None]),
        ("allowed_outcomes", []),
        ("allowed_outcomes", "accept_budget"),
        ("allowed_outcomes", [1]),
    ],
)
def test_invalid_expected_shapes(
    corpus: dict[str, object], key: str, value: object
) -> None:
    cast(dict[str, object], _cases(corpus)[0]["expected"])[key] = value
    _reject(corpus)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        (1,),
        {1},
        b"data",
        object(),
        {1: "data"},
    ],
)
def test_nonfinite_and_non_json_data_anywhere(
    corpus: dict[str, object], value: object
) -> None:
    cast(dict[str, object], _cases(corpus)[-1]["expected"])["extra"] = value
    _reject(corpus)


@pytest.mark.parametrize("kind", ["dict", "list", "row"])
def test_cyclic_data_is_rejected(corpus: dict[str, object], kind: str) -> None:
    if kind == "dict":
        corpus["cycle"] = corpus
    elif kind == "list":
        cycle: list[object] = []
        cycle.append(cycle)
        corpus["cycle"] = cycle
    else:
        case = _cases(corpus)[-1]
        case["cycle"] = case
    _reject(corpus)


@pytest.mark.parametrize("value", [None, [], {}, "corpus", 1, True, (1,)])
def test_invalid_root_shape(value: object) -> None:
    _reject(cast(dict[str, object], value))


def test_invalid_last_case_constructs_no_partial_slots(
    corpus: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbid_construction(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Validation MUST precede slot construction")

    monkeypatch.setattr(evaluation_matrix, "EvaluationSlot", forbid_construction)
    _cases(corpus)[-1]["messages"] = []
    original = deepcopy(corpus)
    _reject(corpus)
    assert corpus == original


def test_changed_gold_and_fixture_text_cannot_change_routing(
    corpus: dict[str, object],
) -> None:
    original_routing = _routing(prepare_matrix(corpus))
    for case in _cases(corpus):
        case["expected"] = {
            "domain_calls": [],
            "model_tools": [],
            "unnecessary_model_tools": [],
            "allowed_outcomes": ["alternate_gold"],
            "evidence_class": "real_bedrock",
            "accepted": False,
            "total_cents": 9999,
        }
        cast(dict[str, object], case["fixture_behavior"])["kind"] = "alternate_fixture"
    slots = prepare_matrix(corpus)
    assert _routing(slots) == original_routing
    for slot in slots:
        expected = cast(dict[str, object], slot.case["expected"])
        assert expected["accepted"] is False
        assert expected["total_cents"] == 9999
        assert "evidence_class" not in vars(slot)
