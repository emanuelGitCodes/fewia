"""HTTP routes for the deterministic context tools."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_session
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
