from collections.abc import Callable
from copy import deepcopy

import pytest

from app.evaluation_markdown_values import as_map, pick, require, slots, text


class MapSubclass(dict[str, object]):
    pass


class ListSubclass(list[object]):
    pass


class TextSubclass(str):
    pass


def assert_invalid(action: Callable[[], object]) -> None:
    with pytest.raises(ValueError) as caught:
        action()
    assert str(caught.value) == "Invalid evaluation report input"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_require_accepts_true_and_rejects_false() -> None:
    assert require(True) is None
    assert_invalid(lambda: require(False))


@pytest.mark.parametrize("value", [None, True, 1, "private", [], MapSubclass()])
def test_as_map_requires_exact_dictionary(value: object) -> None:
    assert_invalid(lambda: as_map(value))


@pytest.mark.parametrize("source", [{}, {"status": "scored"}])
def test_as_map_preserves_dictionary_identity(source: dict[str, object]) -> None:
    assert as_map(source) is source


def test_as_map_preserves_recovery_key_behavior() -> None:
    source = {1: "scored"}
    assert as_map(source) is source


@pytest.mark.parametrize("value", [None, True, 1, {}, [], TextSubclass("scored")])
def test_text_requires_exact_string(value: object) -> None:
    assert_invalid(lambda: text(value, "scored"))


@pytest.mark.parametrize("value", ["prefix-scored", "scored-suffix", "scored\n", ""])
def test_text_requires_full_regex_match(value: str) -> None:
    assert_invalid(lambda: text(value, "scored|failed"))


@pytest.mark.parametrize("value", ["scored", "failed"])
def test_text_returns_matching_string(value: str) -> None:
    assert text(value, "scored|failed") is value


def test_text_accepts_empty_string_when_pattern_matches() -> None:
    assert text("", "[a-z]*") == ""


@pytest.mark.parametrize("value", [None, True, 1, "private", {}, (), ListSubclass()])
def test_slots_requires_exact_list(value: object) -> None:
    assert_invalid(lambda: slots(value))


@pytest.mark.parametrize("bad_slot", [None, True, 1, "private", [], MapSubclass()])
def test_slots_rejects_bad_nested_types_without_mutation(bad_slot: object) -> None:
    source: list[object] = [{"status": "scored"}, bad_slot]
    before = deepcopy(source)
    assert_invalid(lambda: slots(source))
    assert source == before


@pytest.mark.parametrize("source", [[], [{}, {"status": "scored"}]])
def test_slots_copies_list_and_preserves_maps(source: list[dict[str, object]]) -> None:
    before = deepcopy(source)
    result = slots(source)
    assert result == source
    assert result is not source
    assert all(item is original for item, original in zip(result, source, strict=True))
    assert source == before


def test_pick_allowlists_present_fields_without_mutation() -> None:
    source: dict[str, object] = {
        "status": "scored",
        "observation": {"turns": [1]},
        "private": "excluded",
        "Status": "excluded",
    }
    before = deepcopy(source)
    result = pick(source, " status\tmissing\nobservation status ")
    assert result == {"status": "scored", "observation": {"turns": [1]}}
    assert result is not source
    assert result["observation"] is source["observation"]
    assert source == before


@pytest.mark.parametrize("fields", ["", " \t\n", "missing"])
def test_pick_accepts_empty_map_and_missing_fields(fields: str) -> None:
    assert pick({}, fields) == {}
    source: dict[str, object] = {"status": "scored"}
    assert pick(source, fields) == {}
    assert source == {"status": "scored"}


def test_invalid_input_suppresses_active_exception_context() -> None:
    try:
        raise RuntimeError("private input")
    except RuntimeError:
        assert_invalid(lambda: text("private input", "scored"))
