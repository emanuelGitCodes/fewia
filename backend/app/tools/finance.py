"""The deterministic financial context tool."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyFinance
from app.tools.base import (
    ContextResponse,
    build_evidence_id,
    missing_day_warnings,
    require_user,
    round_money,
    validate_range,
)


class FinancialContext(ContextResponse):
    """The financial totals and averages for one user and one date range."""

    total_spending: float
    average_daily_spending: float
    average_cash_flow: float
    category_totals: dict[str, float]


def _mean(total: Decimal, record_count: int) -> float:
    """Divide a money total by the record count, or report 0.0 for no rows."""
    if record_count == 0:
        return 0.0
    return round_money(total / Decimal(record_count))


def _category_totals(rows: Sequence[DailyFinance]) -> dict[str, float]:
    """Total each spending category over the rows."""
    zero = Decimal(0)
    return {
        "grocery": round_money(sum((row.grocery_spending for row in rows), zero)),
        "restaurant": round_money(sum((row.restaurant_spending for row in rows), zero)),
        "transportation": round_money(
            sum((row.transportation_spending for row in rows), zero)
        ),
        "fitness": round_money(sum((row.fitness_spending for row in rows), zero)),
        "discretionary": round_money(
            sum((row.discretionary_spending for row in rows), zero)
        ),
    }


def get_financial_context(
    session: Session, user_id: int, start_date: date, end_date: date
) -> FinancialContext:
    """Read the daily finance rows of one user and total them."""
    validate_range(start_date, end_date)
    require_user(session, user_id)
    rows: Sequence[DailyFinance] = (
        session.execute(
            select(DailyFinance)
            .where(DailyFinance.user_id == user_id)
            .where(DailyFinance.observation_date >= start_date)
            .where(DailyFinance.observation_date <= end_date)
            .order_by(DailyFinance.observation_date)
        )
        .scalars()
        .all()
    )
    record_count = len(rows)
    total_spending = sum((row.total_spending for row in rows), Decimal(0))
    total_cash_flow = sum((row.cash_flow for row in rows), Decimal(0))
    return FinancialContext(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        record_count=record_count,
        source=",".join(sorted({row.source for row in rows})),
        evidence_id=build_evidence_id("finance", user_id, start_date, end_date),
        warnings=missing_day_warnings(record_count, start_date, end_date),
        total_spending=round_money(total_spending),
        average_daily_spending=_mean(total_spending, record_count),
        average_cash_flow=_mean(total_cash_flow, record_count),
        category_totals=_category_totals(rows),
    )
