from __future__ import annotations

import pytest

from app.evaluation_score_values import (
    as_map,
    completed_results,
    has_value,
    id_lists_equal,
    lines_by_id,
    typed_equal,
)


def _turn(status: object, result: object) -> dict[str, object]:
    return {"status": status, "result": result}


def test_as_map_copies_string_keys_and_rejects_invalid_types() -> None:
    source = {"a": 1, "b": False}
    mapped = as_map(source)
    assert mapped == {"a": 1, "b": False}
    assert mapped is not source
    assert as_map([("a", 1)]) is None
    assert as_map(None) is None
    assert as_map({1: "a"}) is None
    assert as_map({"a": 1, 2: "b"}) is None


def test_as_map_does_not_mutate_source() -> None:
    source = {"a": 1}
    mapped = as_map(source)
    assert mapped is not None
    mapped["a"] = 9
    mapped["b"] = 2
    assert source == {"a": 1}


def test_typed_equal_rejects_bool_int_at_every_depth() -> None:
    assert typed_equal(True, True) is True
    assert typed_equal(1, 1) is True
    assert typed_equal(True, 1) is False
    assert typed_equal(False, 0) is False
    assert typed_equal([True], [1]) is False
    assert typed_equal({"k": True}, {"k": 1}) is False
    assert typed_equal({"k": [False]}, {"k": [0]}) is False
    assert typed_equal({"a": {"b": True}}, {"a": {"b": 1}}) is False


def test_typed_equal_compares_maps_and_lists_by_exact_type() -> None:
    assert typed_equal({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True
    assert typed_equal({"a": 1}, {"a": 1, "b": 2}) is False
    assert typed_equal([1, 2], [1, 2]) is True
    assert typed_equal([1, 2], [2, 1]) is False
    assert typed_equal({1: "a"}, {1: "a"}) is False
    assert typed_equal(1, 1.0) is False


def test_has_value_distinguishes_missing_from_none() -> None:
    body = {"notice": None, "total": 0}
    assert has_value(body, "notice", None) is True
    assert has_value(body, "total", 0) is True
    assert has_value(body, "missing", None) is False
    assert has_value(None, "notice", None) is False
    assert has_value({}, "notice", None) is False
    assert has_value(body, "total", False) is False


def test_id_lists_equal_is_order_insensitive_for_unique_strings() -> None:
    body = {"pantry_ingredients": ["rice", "beans"]}
    assert id_lists_equal(body, "pantry_ingredients", ["beans", "rice"]) is True
    assert id_lists_equal(body, "pantry_ingredients", ["rice", "beans"]) is True
    assert id_lists_equal({"pantry_ingredients": []}, "pantry_ingredients", []) is True


def test_id_lists_equal_rejects_duplicates_malformed_sets_and_missing() -> None:
    key = "ingredient_exclusions"
    assert id_lists_equal({"ingredient_exclusions": ["a", "a"]}, key, ["a"]) is False
    assert id_lists_equal({"ingredient_exclusions": ["a"]}, key, ["a", "a"]) is False
    assert id_lists_equal({"ingredient_exclusions": ["a", 1]}, key, ["a"]) is False
    assert id_lists_equal({"ingredient_exclusions": ["a"]}, key, ["a", None]) is False
    assert id_lists_equal({"ingredient_exclusions": None}, key, []) is False
    assert id_lists_equal({}, key, []) is False
    assert id_lists_equal(None, key, ["a"]) is False
    assert id_lists_equal({"ingredient_exclusions": "a"}, key, ["a"]) is False


def test_id_lists_equal_does_not_mutate_source() -> None:
    items = ["rice", "beans"]
    body = {"pantry_ingredients": items}
    expected = ["beans", "rice"]
    assert id_lists_equal(body, "pantry_ingredients", expected) is True
    assert items == ["rice", "beans"]
    assert expected == ["beans", "rice"]
    assert body["pantry_ingredients"] is items


def test_lines_by_id_indexes_unique_string_ingredient_ids() -> None:
    flour = {"ingredient_id": "flour", "quantity": 1}
    salt = {"ingredient_id": "salt", "quantity": 2}
    index = lines_by_id([flour, salt])
    assert index == {
        "flour": {"ingredient_id": "flour", "quantity": 1},
        "salt": {"ingredient_id": "salt", "quantity": 2},
    }
    assert index is not None
    assert index["flour"] is not flour
    assert lines_by_id([]) == {}


def test_lines_by_id_rejects_duplicate_and_malformed_lines() -> None:
    line = {"ingredient_id": "flour", "quantity": 1}
    assert lines_by_id([line, {"ingredient_id": "flour"}]) is None
    assert lines_by_id([{"quantity": 1}]) is None
    assert lines_by_id([{"ingredient_id": 1}]) is None
    assert lines_by_id([line, "flour"]) is None
    assert lines_by_id({"ingredient_id": "flour"}) is None
    assert lines_by_id([{1: "flour"}]) is None
    assert lines_by_id(None) is None


def test_lines_by_id_does_not_mutate_source() -> None:
    line = {"ingredient_id": "flour", "quantity": 1}
    raw = [line]
    index = lines_by_id(raw)
    assert index is not None
    index["flour"]["quantity"] = 9
    index["salt"] = {"ingredient_id": "salt"}
    raw.append({"ingredient_id": "oil"})
    assert line == {"ingredient_id": "flour", "quantity": 1}
    assert len(raw) == 2
    assert "salt" not in line
    assert "oil" not in index


def test_completed_results_returns_nonempty_completed_result_maps() -> None:
    turns = [
        _turn("completed", {"status": "planned", "ok": True}),
        _turn("completed", {"status": "planned"}),
    ]
    results = completed_results(turns, 2)
    assert results == [{"status": "planned", "ok": True}, {"status": "planned"}]
    assert results is not None
    assert results[0] is not turns[0]["result"]


@pytest.mark.parametrize(
    ("turns", "expected_count"),
    [
        (None, 1),
        ([], 1),
        ([], 0),
        ([_turn("completed", {"ok": True})], 2),
        (
            [_turn("completed", {"ok": True}), _turn("failed", {"ok": True})],
            2,
        ),
        ([_turn("completed", {"ok": True}), _turn("completed", {})], 2),
        ([_turn("completed", None)], 1),
        ([_turn("completed", {1: "x"})], 1),
        ([{"status": "completed"}], 1),
        ([{}], 1),
        ([_turn("completed", {"ok": True})], True),
        ([_turn("completed", {"ok": True})], False),
        ([_turn("completed", {"ok": True})], 0),
        ([_turn("completed", {"ok": True})], -1),
        ([_turn("completed", {"ok": True})], 1.0),
    ],
)
def test_completed_results_rejects_partial_missing_empty_and_bool_counts(
    turns: object, expected_count: object
) -> None:
    assert completed_results(turns, expected_count) is None


def test_completed_results_does_not_mutate_source() -> None:
    result = {"status": "planned"}
    turns = [_turn("completed", result)]
    results = completed_results(turns, 1)
    assert results is not None
    results[0]["status"] = "needs_revision"
    results.append({"status": "extra"})
    turns.append(_turn("completed", {"status": "other"}))
    assert result == {"status": "planned"}
    assert len(turns) == 2
    assert len(results) == 2
    assert results[0]["status"] == "needs_revision"
