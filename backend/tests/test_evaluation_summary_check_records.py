from copy import deepcopy
from typing import cast

import pytest

from app.evaluation_summary_check_records import failure_record, validate_checks


class DictSubclass(dict[str, bool]):
    pass


class IntSubclass(int):
    pass


@pytest.mark.parametrize(
    "name",
    [
        "B04a.available_cents",
        "B04b.outcome",
        "B05b.stale",
        "M06a.accepted",
        "M06a.total_cents",
        "M06b.outcome",
        "budget",
        "servings",
        "guard",
        "P01.guard",
        "a",
        "a0_",
        "a" * 64,
        "Z99z." + "a" * 64,
    ],
)
def test_accepts_safe_check_names(name: str) -> None:
    assert validate_checks({name: True}) == {name: True}
    assert validate_checks({name: False}) == {name: False}
    assert failure_record("B04", 1, "fixture", [name])["checks"] == [name]


@pytest.mark.parametrize("value", [None, [], (), "guard", True, DictSubclass()])
def test_rejects_non_exact_dict_maps(value: object) -> None:
    with pytest.raises(ValueError, match="^invalid summary check record$"):
        validate_checks(value)


@pytest.mark.parametrize(
    "name",
    [
        None,
        1,
        False,
        b"guard",
        "",
        "Guard",
        "_guard",
        "1guard",
        "guard-name",
        "guard.name",
        " guard",
        "guard ",
        "guard\n",
        "guárd",
        "b04a.guard",
        "B4.guard",
        "B004.guard",
        "B04A.guard",
        "B04aa.guard",
        "B04a.Guard",
        "B04a.guard.extra",
        "B04a.",
        "a" * 65,
        "B04a." + "a" * 65,
        "B04." + "a" * 65,
    ],
)
def test_rejects_invalid_names_in_maps_and_failure_lists(name: object) -> None:
    with pytest.raises(ValueError, match="^invalid summary check record$"):
        validate_checks({name: True})
    with pytest.raises(ValueError, match="^invalid summary check record$"):
        failure_record("B04", 1, "fixture", cast(list[str], [name]))


@pytest.mark.parametrize("value", [0, 1, "true", "false", None, [], {}])
def test_rejects_non_boolean_check_values(value: object) -> None:
    with pytest.raises(ValueError, match="^invalid summary check record$"):
        validate_checks({"guard": value})


def test_empty_outputs_are_allowed_and_copied() -> None:
    checks: dict[str, bool] = {}
    names: list[str] = []
    result = validate_checks(checks)
    record = failure_record("A00", 1, "claims", names)
    assert result == {}
    assert result is not checks
    assert record == {
        "case_id": "A00",
        "repeat": 1,
        "assessment": "claims",
        "checks": [],
    }
    assert record["checks"] is not names


@pytest.mark.parametrize("scope", ["tools", "plan", "outcome", "claims", "fixture"])
def test_accepts_each_assessment_scope(scope: str) -> None:
    assert failure_record("Z99", 4, scope, ["guard"]) == {
        "case_id": "Z99",
        "repeat": 4,
        "assessment": scope,
        "checks": ["guard"],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_id", None),
        ("case_id", 101),
        ("case_id", ""),
        ("case_id", "b04"),
        ("case_id", "B4"),
        ("case_id", "B004"),
        ("case_id", "B04a"),
        ("case_id", "B04\n"),
        ("case_id", " B04"),
        ("repeat", True),
        ("repeat", False),
        ("repeat", 0),
        ("repeat", -1),
        ("repeat", 1.0),
        ("repeat", "1"),
        ("repeat", IntSubclass(1)),
        ("assessment", None),
        ("assessment", []),
        ("assessment", ""),
        ("assessment", "tool"),
        ("assessment", "Plan"),
        ("assessment", "fixture\n"),
        ("checks", None),
        ("checks", ("guard",)),
        ("checks", {"guard": False}),
        ("checks", "guard"),
        ("checks", ["guard", "guard"]),
        ("checks", ["B04a.outcome", "B04a.outcome"]),
    ],
)
def test_rejects_invalid_failure_fields(field: str, value: object) -> None:
    fields: dict[str, object] = {
        "case_id": "B04",
        "repeat": 1,
        "assessment": "fixture",
        "checks": ["guard"],
    }
    fields[field] = value
    before = deepcopy(fields)
    with pytest.raises(ValueError, match="^invalid summary check record$"):
        failure_record(
            cast(str, fields["case_id"]),
            cast(int, fields["repeat"]),
            cast(str, fields["assessment"]),
            cast(list[str], fields["checks"]),
        )
    assert fields == before


def test_valid_outputs_are_isolated_and_exclude_unrelated_payloads() -> None:
    source: dict[str, object] = {
        "case_id": "B04",
        "repeat": 2,
        "assessment": "fixture",
        "checks": ["guard", "B04a.available_cents"],
        "answer": "synthetic-secret-answer",
        "input": {"text": "synthetic-secret-input"},
        "report": {"text": "synthetic-secret-report"},
        "exception": "synthetic-secret-exception",
    }
    before = deepcopy(source)
    record = failure_record(
        cast(str, source["case_id"]),
        cast(int, source["repeat"]),
        cast(str, source["assessment"]),
        cast(list[str], source["checks"]),
    )
    assert record == {
        "case_id": "B04",
        "repeat": 2,
        "assessment": "fixture",
        "checks": ["guard", "B04a.available_cents"],
    }
    assert source == before
    cast(list[str], record["checks"]).append("budget")
    assert source == before
    checks = {"guard": False, "budget": True}
    result = validate_checks(checks)
    assert result == checks
    result["guard"] = True
    assert checks == {"guard": False, "budget": True}


def test_invalid_payloads_use_static_errors_and_preserve_inputs() -> None:
    checks: dict[str, object] = {
        "guard": True,
        "answer": "synthetic-secret-answer",
        "input": {"text": "synthetic-secret-input"},
        "report": {"text": "synthetic-secret-report"},
        "exception": "synthetic-secret-exception",
    }
    before = deepcopy(checks)
    with pytest.raises(ValueError) as map_error:
        validate_checks(checks)
    with pytest.raises(ValueError) as record_error:
        failure_record("B04", 1, "fixture", ["synthetic-secret-invalid-name"])
    assert str(map_error.value) == "invalid summary check record"
    assert str(record_error.value) == str(map_error.value)
    assert checks == before
