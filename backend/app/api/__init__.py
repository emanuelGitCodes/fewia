"""HTTP routes for the deterministic context tools."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_session
from app.tools.compare import PeriodComparison, compare_periods
from app.tools.environment import EnvironmentContext, get_environment_context
from app.tools.finance import FinancialContext, get_financial_context
from app.tools.health import HealthContext, get_health_context

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/health")
def read_health_context(
    user_id: int,
    start_date: date,
    end_date: date,
    session: Annotated[Session, Depends(get_session)],
) -> HealthContext:
    """Return the health context of one user over the requested range."""
    return get_health_context(session, user_id, start_date, end_date)


@router.get("/financial")
def read_financial_context(
    user_id: int,
    start_date: date,
    end_date: date,
    session: Annotated[Session, Depends(get_session)],
) -> FinancialContext:
    """Return the financial context for one user and one date range."""
    return get_financial_context(session, user_id, start_date, end_date)


@router.get("/environment")
def read_environment_context(
    user_id: int,
    start_date: date,
    end_date: date,
    session: Annotated[Session, Depends(get_session)],
) -> EnvironmentContext:
    """Return the environment context of one user for one date range."""
    return get_environment_context(session, user_id, start_date, end_date)


@router.get("/compare")
def read_period_comparison(
    user_id: int,
    period_a_start: date,
    period_a_end: date,
    period_b_start: date,
    period_b_end: date,
    session: Annotated[Session, Depends(get_session)],
) -> PeriodComparison:
    """Return the comparison of two date ranges for one user."""
    return compare_periods(
        session,
        user_id,
        (period_a_start, period_a_end),
        (period_b_start, period_b_end),
    )
