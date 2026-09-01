"""The deterministic health context tool."""

from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyHealth
from app.tools.base import (
    ContextResponse,
    ToolWarning,
    build_evidence_id,
    missing_day_warnings,
    require_user,
    round_money,
    validate_range,
)

NULLABLE_COLUMNS = (
    "resting_heart_rate",
    "sleep_minutes",
    "intensity_minutes",
    "stress_score",
)


class HealthContext(ContextResponse):
    """Health values that the tool computes over the requested range."""

    average_steps: int
    total_steps: int
    average_sleep_minutes: float | None
    average_resting_heart_rate: float | None
    average_stress_score: float | None


def _mean(values: Sequence[Decimal | int]) -> float | None:
    """Return the rounded mean, or None when the range holds no value."""
    if not values:
        return None
    return round_money(sum(Decimal(v) for v in values) / Decimal(len(values)))


def _mean_steps(values: Sequence[int]) -> int:
    """Return the mean step count as a whole number, or 0 for an empty range."""
    if not values:
        return 0
    mean = Decimal(sum(values)) / Decimal(len(values))
    return int(mean.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _null_field_warnings(rows: Sequence[DailyHealth]) -> list[ToolWarning]:
    """Report the nullable columns that hold no value on one or more days."""
    affected = [
        name
        for name in NULLABLE_COLUMNS
        if any(getattr(row, name) is None for row in rows)
    ]
    if not affected:
        return []
    return [
        ToolWarning(
            code="null_fields",
            message="One or more days hold no value in a nullable column.",
            detail={"columns": ",".join(affected)},
        )
    ]


def get_health_context(
    session: Session, user_id: int, start_date: date, end_date: date
) -> HealthContext:
    """Read the daily health rows of one user and average them."""
    validate_range(start_date, end_date)
    require_user(session, user_id)
    statement = (
        select(DailyHealth)
        .where(
            DailyHealth.user_id == user_id,
            DailyHealth.observation_date >= start_date,
            DailyHealth.observation_date <= end_date,
        )
        .order_by(DailyHealth.observation_date)
    )
    rows = list(session.execute(statement).scalars().all())
    steps = [row.steps for row in rows]
    warnings = missing_day_warnings(len(rows), start_date, end_date)
    warnings.extend(_null_field_warnings(rows))
    return HealthContext(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        record_count=len(rows),
        source=",".join(sorted({row.source for row in rows})),
        evidence_id=build_evidence_id("health", user_id, start_date, end_date),
        warnings=warnings,
        average_steps=_mean_steps(steps),
        total_steps=sum(steps),
        average_sleep_minutes=_mean(
            [row.sleep_minutes for row in rows if row.sleep_minutes is not None]
        ),
        average_resting_heart_rate=_mean(
            [
                row.resting_heart_rate
                for row in rows
                if row.resting_heart_rate is not None
            ]
        ),
        average_stress_score=_mean(
            [row.stress_score for row in rows if row.stress_score is not None]
        ),
    )
