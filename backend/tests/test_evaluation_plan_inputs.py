from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_budget_inputs import CLOCK_ERROR
from app.evaluation_plan_inputs import MEALS_ERROR, fixture_plan
from app.services.grocery_planner import PlanningError

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
MEAL_IDS = ("M01", "M02", "M06")
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _meal_cases() -> dict[str, dict[str, object]]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    found: dict[str, dict[str, object]] = {}
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        case_id = row.get("id")
        if case_id in MEAL_IDS:
            found[str(case_id)] = row
    return found


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _inputs(case: dict[str, object]) -> dict[str, object]:
    return dict(_mapping(case["inputs"], "inputs"))


def _assert_static_clock_error(exc: BaseException, raw: str) -> None:
    assert isinstance(exc, TypeError)
    assert exc.args == (CLOCK_ERROR,)
    assert exc.__context__ is None
    assert exc.__cause__ is None
    assert raw not in str(exc)
    assert raw not in repr(exc)
    assert SECRET_MARKER not in str(exc)
    assert SECRET_MARKER not in repr(exc)


def test_m01_plan_matches_gold() -> None:
    result = fixture_plan(_inputs(_meal_cases()["M01"]))
    assert result.total_cents == 1703
    assert result.accepted is True
    assert len(result.lines) == 7
    assert result.notice == SAMPLE_ESTIMATE_NOTICE


def test_m02_shares_chicken_breast_before_packages() -> None:
    result = fixture_plan(_inputs(_meal_cases()["M02"]))
    chicken = next(
        line for line in result.lines if line.ingredient_id == "chicken_breast"
    )
    assert chicken.quantity == 200
    assert chicken.packages == 1


def test_m06_vegetarian_total_cents() -> None:
    result = fixture_plan(_inputs(_meal_cases()["M06"]))
    assert result.total_cents == 1853


def test_m06_vegan_raises_planning_error_for_eggs() -> None:
    payload = dict(_inputs(_meal_cases()["M06"]))
    payload["diet"] = "vegan"
    with pytest.raises(PlanningError) as diet_error:
        fixture_plan(payload)
    assert "eggs" in str(diet_error.value)


def test_empty_meals_raises_without_calling_planner() -> None:
    payload = dict(_inputs(_meal_cases()["M01"]))
    payload["meals"] = []
    with patch("app.evaluation_plan_inputs.plan_groceries") as planner:
        with pytest.raises(TypeError) as meals_error:
            fixture_plan(payload)
    assert type(meals_error.value) is TypeError
    assert meals_error.value.args == (MEALS_ERROR,)
    planner.assert_not_called()


def test_malformed_now_raises_static_clock_error() -> None:
    payload = dict(_inputs(_meal_cases()["M01"]))
    bad_now = f"{SECRET_MARKER}-not-a-clock"
    payload["now"] = bad_now
    with pytest.raises(TypeError) as now_error:
        fixture_plan(payload)
    _assert_static_clock_error(now_error.value, bad_now)


def test_missing_black_beans_price_is_incomplete() -> None:
    missing = replace(INGREDIENTS["black_beans"], price_cents=None)
    ingredients = {**INGREDIENTS, "black_beans": missing}
    result = fixture_plan(_inputs(_meal_cases()["M01"]), ingredients=ingredients)
    assert result.accepted is False
    assert result.total_cents is None
