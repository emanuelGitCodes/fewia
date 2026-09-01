"""HTTP routes for the prediction tool."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_session
from app.tools.prediction import (
    ActivityPrediction,
    FeatureSet,
    run_activity_prediction,
)

router = APIRouter(prefix="/predict", tags=["predict"])


@router.get("/activity")
def get_activity_prediction(
    user_id: Annotated[int, Query()],
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
    session: Annotated[Session, Depends(get_session)],
    feature_set: Annotated[FeatureSet, Query()] = "combined",
) -> ActivityPrediction:
    """Return the predicted daily step average for the user and the range."""
    return run_activity_prediction(session, user_id, start_date, end_date, feature_set)
