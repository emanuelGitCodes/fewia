from __future__ import annotations

from collections import UserDict
from copy import deepcopy
from typing import cast

import pytest

from app.evaluation_shapes import as_map, typed_equal, valid_public_result


class DictSubclass(dict[str, object]):
    pass


class ListSubclass(list[object]):
    pass


class StringSubclass(str):
    pass


def _result(
    status: str = "planned",
    *,
    accepted: object = True,
    total_cents: object = 1200,
    null_payloads: bool = False,
) -> dict[str, object]:
    return {
        "status": status,
        "answer": "Your plan is ready.",
        "request": None if null_payloads else {},
        "plan": None
        if null_payloads
        else {"accepted": accepted, "total_cents": total_cents},
        "budget": None if null_payloads else {},
    }


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        1,
        "map",
        [],
        (),
        UserDict({"key": 1}),
        DictSubclass({"key": 1}),
        {1: "value"},
        {True: "value"},
        {"key": 1, None: 2},
    ],
)
def test_as_map_rejects_other_shapes(value: object) -> None:
    assert as_map(value) == {}


def test_as_map_copies_only_the_outer_dictionary() -> None:
    nested: list[object] = [{"amount_cents": 42}]
    source: dict[str, object] = {"nested": nested, "enabled": True}
    result = as_map(source)
    assert result == source
    assert result is not source
    assert result["nested"] is nested
    result["enabled"] = False
    result["extra"] = 1
    assert source == {"nested": nested, "enabled": True}


def test_as_map_accepts_empty_maps_and_string_keys() -> None:
    source: dict[str, object] = {}
    assert as_map(source) == {}
    assert as_map(source) is not source
    key = StringSubclass("key")
    assert as_map({key: 1}) == {"key": 1}
    first = as_map(None)
    second = as_map(None)
    first["key"] = 1
    assert second == {}


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (None, None, True),
        (True, True, True),
        (True, 1, False),
        (0, False, False),
        (1, 1.0, False),
        ("1", 1, False),
        ("same", "same", True),
        ("same", "other", False),
        ({}, {}, True),
        ({"a": 1}, {"a": 1, "b": 2}, False),
        ({"a": 1}, {"b": 1}, False),
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
        ({True: "value"}, {1: "value"}, False),
        ({"a": [True]}, {"a": [1]}, False),
        ([{"a": [1, None]}], [{"a": [1, None]}], True),
        ([{"a": [1, None]}], [{"a": [1, False]}], False),
        ([], [], True),
        ([1], [1, 2], False),
        ([1, 2], [2, 1], False),
        ([1], (1,), False),
        (DictSubclass({"a": 1}), {"a": 1}, False),
        (ListSubclass([1]), [1], False),
        (StringSubclass("same"), "same", False),
        (DictSubclass({"a": True}), DictSubclass({"a": 1}), False),
        (ListSubclass([True]), ListSubclass([1]), False),
    ],
)
def test_typed_equal_is_strict_and_recursive(
    left: object, right: object, expected: bool
) -> None:
    assert typed_equal(left, right) is expected
    assert typed_equal(right, left) is expected


def test_typed_equal_preserves_inputs_and_aliases() -> None:
    shared: dict[str, object] = {"a": [1, True], "b": None}
    left: dict[str, object] = {"items": [shared, shared]}
    right: dict[str, object] = {
        "items": [{"b": None, "a": [1, True]}, {"a": [1, True], "b": None}]
    }
    left_before = deepcopy(left)
    right_before = deepcopy(right)
    assert typed_equal(left, right)
    assert typed_equal(left, left_before)
    assert typed_equal(right, right_before)
    items = cast(list[object], left["items"])
    assert items[0] is shared
    assert items[1] is shared
    assert not typed_equal(left, {"items": [shared]})
    assert typed_equal(left, left_before)


@pytest.mark.parametrize(
    ("status", "accepted", "total_cents", "null_payloads"),
    [
        ("planned", True, 1200, False),
        ("needs_revision", False, 1200, False),
        ("clarification", False, None, False),
        ("clarification", True, 1200, True),
        ("limit", True, 1200, True),
        ("incomplete", True, 1200, True),
    ],
)
def test_valid_public_result_accepts_coherent_statuses(
    status: str, accepted: object, total_cents: object, null_payloads: bool
) -> None:
    assert valid_public_result(
        _result(
            status,
            accepted=accepted,
            total_cents=total_cents,
            null_payloads=null_payloads,
        )
    )


def test_valid_public_result_allows_extra_fields_without_mutation() -> None:
    result = _result()
    evidence: list[object] = [{"version": 1, "amount_cents": 1200}]
    result.update({"usage": {}, "evidence": evidence, "traces": []})
    before = deepcopy(result)
    assert valid_public_result(result)
    assert typed_equal(result, before)
    assert result["evidence"] is evidence


@pytest.mark.parametrize("answer", ["x", "x" * 4096])
def test_valid_public_result_accepts_answer_bounds(answer: str) -> None:
    result = _result()
    result["answer"] = answer
    assert valid_public_result(result)


@pytest.mark.parametrize("answer", ["", "x" * 4097, None, True, 1, [], {}])
def test_valid_public_result_rejects_invalid_answers(answer: object) -> None:
    result = _result()
    result["answer"] = answer
    assert not valid_public_result(result)


@pytest.mark.parametrize("field", ["status", "answer", "request", "plan", "budget"])
def test_valid_public_result_requires_each_field(field: str) -> None:
    result = _result()
    del result[field]
    assert not valid_public_result(result)


@pytest.mark.parametrize("status", ["unknown", "", None, True, 1, [], {}])
def test_valid_public_result_rejects_invalid_statuses(status: object) -> None:
    result = _result()
    result["status"] = status
    assert not valid_public_result(result)


@pytest.mark.parametrize(
    "value",
    [None, [], UserDict(_result()), DictSubclass(_result()), {"extra": "value"}],
)
def test_valid_public_result_rejects_other_shapes(value: object) -> None:
    assert not valid_public_result(value)


@pytest.mark.parametrize("field", ["request", "plan", "budget"])
@pytest.mark.parametrize(
    "payload", [None, [], "value", False, 0, UserDict(), DictSubclass()]
)
def test_valid_public_result_rejects_wrong_payload_types(
    field: str, payload: object
) -> None:
    result = _result()
    result[field] = payload
    assert not valid_public_result(result)


@pytest.mark.parametrize(
    "status", ["planned", "needs_revision", "clarification", "limit", "incomplete"]
)
@pytest.mark.parametrize("field", ["request", "plan", "budget"])
def test_valid_public_result_rejects_mixed_null_payloads(
    status: str, field: str
) -> None:
    result = _result(status, null_payloads=True)
    result[field] = {}
    assert not valid_public_result(result)
    result = _result(status, accepted=False, total_cents=None)
    result[field] = None
    assert not valid_public_result(result)


@pytest.mark.parametrize("status", ["planned", "needs_revision"])
def test_valid_public_result_rejects_null_plans(status: str) -> None:
    assert not valid_public_result(_result(status, null_payloads=True))


@pytest.mark.parametrize("status", ["limit", "incomplete"])
def test_valid_public_result_requires_null_payloads(status: str) -> None:
    assert not valid_public_result(_result(status))


@pytest.mark.parametrize(
    ("status", "accepted"),
    [
        ("planned", False),
        ("planned", 1),
        ("planned", "true"),
        ("planned", None),
        ("needs_revision", True),
        ("needs_revision", 0),
        ("needs_revision", "false"),
        ("needs_revision", None),
        ("clarification", True),
        ("clarification", 0),
        ("clarification", None),
    ],
)
def test_valid_public_result_requires_boolean_acceptance(
    status: str, accepted: object
) -> None:
    assert not valid_public_result(_result(status, accepted=accepted, total_cents=None))


@pytest.mark.parametrize("status", ["planned", "needs_revision", "clarification"])
def test_valid_public_result_requires_plan_acceptance(status: str) -> None:
    result = _result(status, total_cents=None)
    result["plan"] = {"total_cents": None}
    assert not valid_public_result(result)


@pytest.mark.parametrize("total_cents", [0, 1200, False, "unknown", [], {}])
def test_valid_public_result_requires_incomplete_clarification(
    total_cents: object,
) -> None:
    assert not valid_public_result(
        _result("clarification", accepted=False, total_cents=total_cents)
    )


def test_valid_public_result_requires_clarification_total_field() -> None:
    result = _result("clarification")
    result["plan"] = {"accepted": False}
    assert not valid_public_result(result)
