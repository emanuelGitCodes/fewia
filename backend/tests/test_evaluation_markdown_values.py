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


class HostileKey:
    armed: bool = False

    def __hash__(self) -> int:
        if self.armed:
            raise RuntimeError("synthetic private marker")
        return hash("version")

    def __eq__(self, other: object) -> bool:
        if self.armed:
            raise RuntimeError("synthetic private marker")
        return self is other

    def __repr__(self) -> str:
        raise RuntimeError("synthetic private marker")

    def __str__(self) -> str:
        raise RuntimeError("synthetic private marker")


class HostileText(str):
    armed: bool = False

    def __hash__(self) -> int:
        if self.armed:
            raise RuntimeError("synthetic private marker")
        return hash("version")

    def __eq__(self, other: object) -> bool:
        if self.armed:
            raise RuntimeError("synthetic private marker")
        return self is other

    def __repr__(self) -> str:
        raise RuntimeError("synthetic private marker")

    def __str__(self) -> str:
        raise RuntimeError("synthetic private marker")


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
@pytest.mark.parametrize(
    "validate",
    [
        pytest.param(as_map, id="top_map"),
        pytest.param(lambda value: pick(value, "version"), id="direct_pick"),
    ],
)
def test_map_boundaries_require_exact_dictionary(
    value: object, validate: Callable[[object], object]
) -> None:
    assert_invalid(lambda: validate(value))


@pytest.mark.parametrize("source", [{}, {"status": "scored"}])
def test_as_map_preserves_dictionary_identity(source: dict[str, object]) -> None:
    assert as_map(source) is source


@pytest.mark.parametrize(
    "validate",
    [
        pytest.param(as_map, id="top_map"),
        pytest.param(lambda value: pick(value, "version"), id="direct_pick"),
        pytest.param(lambda value: pick(value, ""), id="empty_pick"),
        pytest.param(
            lambda value: slots([{"status": "scored"}, value]), id="nested_slot"
        ),
    ],
)
@pytest.mark.parametrize(
    "key",
    [None, True, 1, 1.5, b"version", ("version",), TextSubclass("version")],
    ids=["none", "bool", "int", "float", "bytes", "tuple", "str_subclass"],
)
def test_map_boundaries_reject_bad_keys_without_mutation(
    key: object, validate: Callable[[object], object]
) -> None:
    ignored = object()
    source = {key: ignored}
    assert_invalid(lambda: validate(source))
    assert len(source) == 1
    assert next(iter(source)) is key
    assert next(iter(source.values())) is ignored


@pytest.mark.parametrize(
    "validate",
    [
        pytest.param(as_map, id="top_map"),
        pytest.param(lambda value: pick(value, "version"), id="direct_pick"),
        pytest.param(lambda value: pick(value, ""), id="empty_pick"),
        pytest.param(
            lambda value: slots([{"status": "scored"}, value]), id="nested_slot"
        ),
    ],
)
@pytest.mark.parametrize("key_kind", ["object", "str_subclass"])
def test_map_boundaries_do_not_call_hostile_key_methods(
    key_kind: str, validate: Callable[[object], object]
) -> None:
    key = HostileKey() if key_kind == "object" else HostileText("version")
    source: dict[object, object] = {"version": "allowed", "unknown": object()}
    source[key] = object()
    keys = list(source)
    values = list(source.values())
    key.armed = True
    assert_invalid(lambda: validate(source))
    assert len(source) == len(keys)
    assert all(
        current is original for current, original in zip(source, keys, strict=True)
    )
    assert all(
        current is original
        for current, original in zip(source.values(), values, strict=True)
    )


def test_unknown_string_keys_preserve_ignored_values_without_inspection() -> None:
    ignored = HostileKey()
    ignored.armed = True
    source: dict[str, object] = {"version": "allowed", "unknown": ignored}
    assert as_map(source) is source
    assert pick(source, "version missing") == {"version": "allowed"}
    rows = slots([source])
    assert rows[0] is source
    assert source["unknown"] is ignored
    assert tuple(source) == ("version", "unknown")


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
