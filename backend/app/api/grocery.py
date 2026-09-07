"""HTTP routes for fixture grocery planning jobs."""

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.grocery_models import (
    CatalogRef,
    CreateGroceryJobBody,
    GroceryConfig,
    GroceryJobAccepted,
    GroceryJobView,
)
from app.deps import get_session
from app.domain.budget import NEW_YORK
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS
from app.job_models import Job
from app.models import User
from app.services.job_submission import IdempotencyConflict, create_job
from app.services.plan_job import PlanJobInput, SpendingInput

router = APIRouter(prefix="/grocery", tags=["grocery"])
DEMO_USER_ID = 1
FIXTURE_POSTED_CENTS = 18000
FIXTURE_PENDING_CENTS = 1200
PERIOD_MISMATCH_MESSAGE = "budget_period must match the current New York month"
DEMO_NOT_READY_MESSAGE = "Demo workspace is not ready."
CONFLICT_MESSAGE = "request_key already identifies different content"


def _ny_now() -> datetime:
    return datetime.now(UTC).astimezone(NEW_YORK)


def _existing_agent_job(session: Session, request_key: str) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.user_id == DEMO_USER_ID,
            Job.kind == "agent",
            Job.request_key == request_key,
        )
    )


@router.get("/config")
def read_grocery_config() -> GroceryConfig:
    return GroceryConfig(
        budget_period=_ny_now().date().replace(day=1),
        source="fixture",
        posted_cents=FIXTURE_POSTED_CENTS,
        pending_cents=FIXTURE_PENDING_CENTS,
        notice=SAMPLE_ESTIMATE_NOTICE,
        recipes=[
            CatalogRef(id=recipe_id, name=recipe_id.replace("_", " "))
            for recipe_id in SUPPORTED_RECIPE_IDS
        ],
        ingredients=[
            CatalogRef(id=item.id, name=item.name) for item in INGREDIENTS.values()
        ],
    )


@router.post("/jobs", status_code=202)
def create_grocery_job(
    body: CreateGroceryJobBody,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header()],
) -> GroceryJobAccepted:
    if session.get(User, DEMO_USER_ID) is None:
        raise HTTPException(status_code=503, detail=DEMO_NOT_READY_MESSAGE)
    existing = _existing_agent_job(session, idempotency_key)
    if existing is not None:
        if not body.matches_stored_caller_fields(existing.payload):
            raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE)
        session.commit()
        return GroceryJobAccepted(job_id=existing.id, status=existing.status)
    ny = _ny_now()
    period = ny.date().replace(day=1)
    if body.request.budget_period != period:
        raise HTTPException(status_code=422, detail=PERIOD_MISMATCH_MESSAGE)
    payload = cast(
        dict[str, object],
        PlanJobInput(
            request=body.request,
            monthly_limit_cents=body.monthly_limit_cents,
            spending=SpendingInput(
                period=period,
                posted_cents=FIXTURE_POSTED_CENTS,
                pending_cents=FIXTURE_PENDING_CENTS,
                refreshed_at=ny.astimezone(UTC),
            ),
            spending_source="fixture",
        ).model_dump(mode="json"),
    )
    try:
        job, _created = create_job(
            session, DEMO_USER_ID, "agent", idempotency_key, payload
        )
    except (IdempotencyConflict, IntegrityError) as exc:
        winner = _existing_agent_job(session, idempotency_key)
        if winner is not None and body.matches_stored_caller_fields(winner.payload):
            job = winner
        elif isinstance(exc, IntegrityError) and winner is None:
            raise
        else:
            raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return GroceryJobAccepted(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}")
def read_grocery_job(
    job_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> GroceryJobView:
    job = session.get(Job, str(job_id))
    if job is None or job.user_id != DEMO_USER_ID or job.kind != "agent":
        raise HTTPException(status_code=404, detail="Job not found")
    return GroceryJobView(
        id=job.id,
        status=job.status,
        result=job.result,
        error_code=job.error_code,
    )
