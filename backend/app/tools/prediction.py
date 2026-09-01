"""Activity prediction tool.

The tool returns a stub value. Phase 4 replaces the function body with a
trained model. The signature and the response model are locked.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyHealth
from app.tools.base import (
    ContextResponse,
    ToolWarning,
    build_evidence_id,
    missing_day_warnings,
    require_user,
    validate_range,
)

FeatureSet = Literal["finance", "environment", "combined"]

MODEL_VERSION = "stub-v0"


class ActivityPrediction(ContextResponse):
    """The predicted daily step average for one user and one range."""

    feature_set: FeatureSet
    predicted_average_steps: int
    model_version: str
    is_stub: bool


def _mean_steps(values: list[int]) -> int:
    """Return the mean of the step values, rounded to a whole number."""
    if not values:
        return 0
    mean = Decimal(sum(values)) / Decimal(len(values))
    return int(mean.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_activity_prediction(
    session: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    feature_set: FeatureSet = "combined",
) -> ActivityPrediction:
    """Predict the daily step average from the daily_health rows in the range.

    The stub reads the rows and returns their mean step count. It runs no
    model. The feature_set value changes no arithmetic here. The caller MUST
    read is_stub and model_version before it reports the value.
    """
    validate_range(start_date, end_date)
    require_user(session, user_id)
    rows = list(
        session.execute(
            select(DailyHealth.steps, DailyHealth.source)
            .where(DailyHealth.user_id == user_id)
            .where(DailyHealth.observation_date >= start_date)
            .where(DailyHealth.observation_date <= end_date)
        ).all()
    )
    warnings = missing_day_warnings(len(rows), start_date, end_date)
    warnings.append(
        ToolWarning(
            code="null_fields",
            message="The value comes from a stub. No trained model produced it.",
            detail={"model_version": MODEL_VERSION},
        )
    )
    return ActivityPrediction(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        record_count=len(rows),
        source=",".join(sorted({row.source for row in rows})),
        evidence_id=build_evidence_id("prediction", user_id, start_date, end_date),
        warnings=warnings,
        feature_set=feature_set,
        predicted_average_steps=_mean_steps([row.steps for row in rows]),
        model_version=MODEL_VERSION,
        is_stub=True,
    )
