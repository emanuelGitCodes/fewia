from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TypeGuard
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
STALE_SPENDING_ERROR = (
    "Spending snapshot is stale; refresh it or provide an explicit temporary cap."
)
STALE_SPENDING_WARNING = (
    "Spending snapshot is stale; available budget uses the explicit temporary cap."
)


@dataclass(frozen=True, slots=True)
class SpendingSnapshot:
    period: date
    posted_cents: int
    pending_cents: int
    refreshed_at: datetime


@dataclass(frozen=True, slots=True)
class BudgetResult:
    available_cents: int
    pending_cents: int
    stale: bool
    warnings: tuple[str, ...]


class StaleSpendingError(ValueError):
    pass


def _is_integer(value: object) -> TypeGuard[int]:
    return type(value) is int


def _validate_integer(value: object, name: str) -> None:
    if not _is_integer(value):
        raise TypeError(f"{name} must be an integer")


def _validate_nonnegative_integer(value: object, name: str) -> None:
    if not _is_integer(value):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _validate_aware_datetime(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


def _validate_snapshot(spending: SpendingSnapshot) -> None:
    if type(spending.period) is not date:
        raise TypeError("spending.period must be a date")
    if spending.period.day != 1:
        raise ValueError("spending.period must be the first day of its month")
    _validate_integer(spending.posted_cents, "spending.posted_cents")
    _validate_integer(spending.pending_cents, "spending.pending_cents")
    _validate_aware_datetime(spending.refreshed_at, "spending.refreshed_at")


def calculate_budget(
    monthly_limit_cents: int,
    spending: SpendingSnapshot,
    *,
    now: datetime,
    plan_cap_cents: int | None = None,
) -> BudgetResult:
    _validate_nonnegative_integer(monthly_limit_cents, "monthly_limit_cents")
    if not isinstance(spending, SpendingSnapshot):
        raise TypeError("spending must be a SpendingSnapshot")
    _validate_snapshot(spending)
    _validate_aware_datetime(now, "now")
    if plan_cap_cents is not None:
        _validate_nonnegative_integer(plan_cap_cents, "plan_cap_cents")

    current_period = now.astimezone(NEW_YORK).date().replace(day=1)
    if spending.period != current_period:
        raise ValueError("spending.period must match the current New York month")
    now_utc = now.astimezone(UTC)
    refreshed_at_utc = spending.refreshed_at.astimezone(UTC)
    if refreshed_at_utc > now_utc:
        raise ValueError("spending.refreshed_at must not be in the future")

    stale = now_utc - refreshed_at_utc > timedelta(hours=24)
    if stale:
        if plan_cap_cents is None:
            raise StaleSpendingError(STALE_SPENDING_ERROR)
        return BudgetResult(
            available_cents=plan_cap_cents,
            pending_cents=spending.pending_cents,
            stale=True,
            warnings=(STALE_SPENDING_WARNING,),
        )

    available_cents = max(0, monthly_limit_cents - spending.posted_cents)
    if plan_cap_cents is not None:
        available_cents = min(available_cents, plan_cap_cents)
    return BudgetResult(
        available_cents=available_cents,
        pending_cents=spending.pending_cents,
        stale=False,
        warnings=(),
    )
