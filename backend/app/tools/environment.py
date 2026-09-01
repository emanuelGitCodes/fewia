"""The deterministic environment context tool."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyEnvironment
from app.tools.base import (
    ContextResponse,
    build_evidence_id,
    missing_day_warnings,
    require_user,
    round_money,
    validate_range,
)


class EnvironmentContext(ContextResponse):
    """Average nearby place counts and location types for one date range."""

    average_park_count: float
    average_gym_count: float
    average_grocery_store_count: float
    average_restaurant_count: float
    location_types: list[str]


def _average(values: list[int]) -> float:
    """Average the values, or return 0.0 for an empty list."""
    if not values:
        return 0.0
    return round_money(sum(values) / len(values))


def get_environment_context(
    session: Session, user_id: int, start_date: date, end_date: date
) -> EnvironmentContext:
    """Read the environment rows of one user and average their place counts."""
    validate_range(start_date, end_date)
    require_user(session, user_id)
    rows = list(
        session.execute(
            select(DailyEnvironment)
            .where(DailyEnvironment.user_id == user_id)
            .where(DailyEnvironment.observation_date >= start_date)
            .where(DailyEnvironment.observation_date <= end_date)
            .order_by(DailyEnvironment.observation_date)
        )
        .scalars()
        .all()
    )
    return EnvironmentContext(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        record_count=len(rows),
        source=",".join(sorted({row.source for row in rows})),
        evidence_id=build_evidence_id("environment", user_id, start_date, end_date),
        warnings=missing_day_warnings(len(rows), start_date, end_date),
        average_park_count=_average([row.park_count for row in rows]),
        average_gym_count=_average([row.gym_count for row in rows]),
        average_grocery_store_count=_average([row.grocery_store_count for row in rows]),
        average_restaurant_count=_average([row.restaurant_count for row in rows]),
        location_types=sorted({row.location_type for row in rows}),
    )
