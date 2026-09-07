from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from app.domain.budget import StaleSpendingError
from app.evaluation_budget_inputs import CLOCK_ERROR, fixture_budget

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
BUDGET_IDS = ("B01", "B02", "B03", "B04", "B05")
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
PERIOD_ERROR = "spending.period must match the current New York month"
INPUT_KEYS = (
    "now",
    "budget_period",
    "spending_period",
    "monthly_limit_cents",
    "posted_cents",
    "pending_cents",
    "plan_cap_cents",
    "spending_refreshed_at",
)


def _budget_cases() -> dict[str, dict[str, object]]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    found: dict[str, dict[str, object]] = {}
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        case_id = row.get("id")
        if case_id in BUDGET_IDS:
            found[str(case_id)] = row
    return found


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _variants(case: dict[str, object]) -> list[dict[str, object]]:
    rows = case["variants"]
    assert isinstance(rows, list)
    return [_mapping(item, "variant") for item in rows]


def _inputs(
    case: dict[str, object], variant: dict[str, object] | None = None
) -> dict[str, object]:
    merged = dict(_mapping(case["inputs"], "inputs"))
    if variant is None:
        return merged
    for key in INPUT_KEYS:
        if key in variant:
            merged[key] = variant[key]
    return merged


def _assert_static_clock_error(exc: BaseException, raw: str) -> None:
    assert isinstance(exc, TypeError)
    assert exc.args == (CLOCK_ERROR,)
    assert exc.__context__ is None
    assert exc.__cause__ is None
    assert raw not in str(exc)
    assert raw not in repr(exc)
    assert SECRET_MARKER not in str(exc)
    assert SECRET_MARKER not in repr(exc)


@pytest.mark.parametrize(
    ("case_id", "available", "pending"),
    [("B01", 10000, 4000), ("B02", 1250, 0), ("B03", 0, 0)],
)
def test_fixture_budget_matches_gold_cents(
    case_id: str, available: int, pending: int
) -> None:
    result = fixture_budget(_inputs(_budget_cases()[case_id]))
    gold = _mapping(_budget_cases()[case_id]["expected"], "expected")
    assert result.available_cents == available
    assert result.available_cents == gold["available_cents"]
    assert result.pending_cents == pending
    assert result.stale is False


def test_invalid_date_text_raises_static_error() -> None:
    base = _inputs(_budget_cases()["B01"])
    bad_now = f"{SECRET_MARKER}-not-a-clock"
    payload = dict(base)
    payload["now"] = bad_now
    with pytest.raises(TypeError) as now_error:
        fixture_budget(payload)
    _assert_static_clock_error(now_error.value, bad_now)

    bad_period = f"{SECRET_MARKER}-bad-period"
    payload = dict(base)
    payload["budget_period"] = bad_period
    with pytest.raises(TypeError) as period_error:
        fixture_budget(payload)
    _assert_static_clock_error(period_error.value, bad_period)

    bad_refresh = f"{SECRET_MARKER}-not-a-stamp"
    payload = dict(base)
    payload["spending_refreshed_at"] = bad_refresh
    with pytest.raises(TypeError) as refresh_error:
        fixture_budget(payload)
    _assert_static_clock_error(refresh_error.value, bad_refresh)


def test_stale_and_period_mismatch_stay_distinct() -> None:
    cases = _budget_cases()
    mismatch = _inputs(cases["B04"], _variants(cases["B04"])[1])
    with pytest.raises(ValueError) as period_error:
        fixture_budget(mismatch)
    assert type(period_error.value) is ValueError
    assert str(period_error.value) == PERIOD_ERROR
    assert not isinstance(period_error.value, StaleSpendingError)

    stale = _inputs(cases["B05"], _variants(cases["B05"])[0])
    with pytest.raises(StaleSpendingError) as stale_error:
        fixture_budget(stale)
    assert isinstance(stale_error.value, StaleSpendingError)
    assert str(stale_error.value) != PERIOD_ERROR
    assert str(stale_error.value) != CLOCK_ERROR
