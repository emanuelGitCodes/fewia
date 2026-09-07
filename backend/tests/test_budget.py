from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.budget import (
    STALE_SPENDING_ERROR,
    STALE_SPENDING_WARNING,
    BudgetResult,
    SpendingSnapshot,
    StaleSpendingError,
    calculate_budget,
)

NEW_YORK = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=NEW_YORK)


def snapshot(
    *,
    period: date = date(2026, 9, 1),
    posted_cents: int = 2500,
    pending_cents: int = 400,
    refreshed_at: datetime = NOW - timedelta(hours=1),
) -> SpendingSnapshot:
    return SpendingSnapshot(period, posted_cents, pending_cents, refreshed_at)


def test_dataclasses_are_immutable() -> None:
    spending = snapshot()
    result = BudgetResult(7500, 400, False, ())

    with pytest.raises(FrozenInstanceError):
        spending.posted_cents = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.available_cents = 1  # type: ignore[misc]


def test_fresh_budget_subtracts_posted_and_keeps_pending_separate() -> None:
    result = calculate_budget(10_000, snapshot(), now=NOW)

    assert result == BudgetResult(7500, 400, False, ())


def test_period_uses_new_york_month_not_utc_month() -> None:
    now = datetime(2026, 10, 1, 3, 30, tzinfo=UTC)
    refreshed_at = datetime(2026, 9, 30, 22, 30, tzinfo=NEW_YORK)

    result = calculate_budget(
        10_000,
        snapshot(refreshed_at=refreshed_at),
        now=now,
    )

    assert result.available_cents == 7500


def test_period_must_be_current_new_york_month_at_boundary() -> None:
    now = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="current New York month"):
        calculate_budget(10_000, snapshot(), now=now)


@pytest.mark.parametrize(
    ("posted_cents", "expected_available"),
    [(-250, 1250), (1500, 0)],
)
def test_refunds_can_increase_budget_and_overspending_clamps_to_zero(
    posted_cents: int, expected_available: int
) -> None:
    result = calculate_budget(
        1_000,
        snapshot(posted_cents=posted_cents, pending_cents=900),
        now=NOW,
    )

    assert result.available_cents == expected_available
    assert result.pending_cents == 900


def test_fresh_explicit_cap_is_applied_after_net_posted_spending() -> None:
    result = calculate_budget(10_000, snapshot(), now=NOW, plan_cap_cents=5_000)

    assert result.available_cents == 5_000
    assert result.pending_cents == 400


def test_zero_cap_returns_zero_for_fresh_spending() -> None:
    result = calculate_budget(10_000, snapshot(), now=NOW, plan_cap_cents=0)

    assert result.available_cents == 0
    assert result.stale is False


def test_exactly_24_hours_is_fresh() -> None:
    spending = snapshot(refreshed_at=NOW - timedelta(hours=24))

    result = calculate_budget(10_000, spending, now=NOW)

    assert result.stale is False


def test_fall_back_day_counts_25_elapsed_hours_as_stale() -> None:
    spending = snapshot(
        period=date(2026, 11, 1),
        refreshed_at=datetime(2026, 11, 1, 0, 0, tzinfo=NEW_YORK),
    )
    now = datetime(2026, 11, 2, 0, 0, tzinfo=NEW_YORK)

    with pytest.raises(StaleSpendingError):
        calculate_budget(10_000, spending, now=now)


def test_spring_forward_day_counts_23_elapsed_hours_as_fresh() -> None:
    spending = snapshot(
        period=date(2026, 3, 1),
        refreshed_at=datetime(2026, 3, 8, 0, 0, tzinfo=NEW_YORK),
    )
    now = datetime(2026, 3, 9, 0, 0, tzinfo=NEW_YORK)

    result = calculate_budget(10_000, spending, now=now)

    assert result == BudgetResult(7_500, 400, False, ())


def test_fold_future_refresh_is_rejected_by_utc_ordering() -> None:
    spending = snapshot(
        period=date(2026, 11, 1),
        refreshed_at=datetime(2026, 11, 1, 1, 15, tzinfo=NEW_YORK, fold=1),
    )
    now = datetime(2026, 11, 1, 1, 30, tzinfo=NEW_YORK, fold=0)

    with pytest.raises(ValueError, match="future"):
        calculate_budget(10_000, spending, now=now)


def test_stale_spending_requires_a_cap() -> None:
    spending = snapshot(refreshed_at=NOW - timedelta(hours=24, seconds=1))

    with pytest.raises(StaleSpendingError) as error:
        calculate_budget(10_000, spending, now=NOW)

    assert str(error.value) == STALE_SPENDING_ERROR


def test_stale_spending_uses_temporary_cap_without_subtraction() -> None:
    spending = snapshot(
        posted_cents=9_000,
        pending_cents=-300,
        refreshed_at=NOW - timedelta(days=2),
    )

    result = calculate_budget(10_000, spending, now=NOW, plan_cap_cents=2_000)

    assert result == BudgetResult(2_000, -300, True, (STALE_SPENDING_WARNING,))


@pytest.mark.parametrize(
    "monthly_limit_cents, plan_cap_cents",
    [
        (True, None),
        (10_000, True),
        (10_000, -1),
        (-1, None),
        (10_000, 1.5),
        (10_000, "100"),
    ],
)
def test_integer_controls_reject_booleans_and_negative_caps(
    monthly_limit_cents: object, plan_cap_cents: object
) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_budget(
            monthly_limit_cents,  # type: ignore[arg-type]
            snapshot(),
            now=NOW,
            plan_cap_cents=plan_cap_cents,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("posted_cents", True),
        ("pending_cents", False),
        ("posted_cents", 1.5),
        ("pending_cents", "100"),
    ],
)
def test_spending_cents_reject_non_integer_values(field: str, value: object) -> None:
    values: dict[str, object] = {field: value}
    spending = snapshot(**values)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        calculate_budget(10_000, spending, now=NOW)


@pytest.mark.parametrize(
    "spending, now",
    [
        (snapshot(refreshed_at=NOW + timedelta(seconds=1)), NOW),
        (snapshot(refreshed_at=datetime(2026, 9, 2, 11, 0)), NOW),
        (snapshot(), datetime(2026, 9, 2, 12, 0)),
    ],
)
def test_timestamps_reject_future_or_naive_values(
    spending: SpendingSnapshot, now: datetime
) -> None:
    with pytest.raises(ValueError, match="timezone-aware|future"):
        calculate_budget(10_000, spending, now=now)


@pytest.mark.parametrize(
    "period",
    [date(2026, 9, 2), date(2026, 8, 1), datetime(2026, 9, 1, 0, 0)],
)
def test_period_rejects_non_month_start_wrong_month_and_datetime(
    period: date,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_budget(10_000, snapshot(period=period), now=NOW)
