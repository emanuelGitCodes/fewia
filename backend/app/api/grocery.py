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
    PlanJobView,
)
from app.deps import get_provider_settings, get_session, get_supermarket_estimator
from app.domain.budget import NEW_YORK
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS
from app.job_models import Job
from app.models import User
from app.provider_settings import GroceryProviderSettings
from app.services.grocery_context import (
    FIXTURE_PENDING_CENTS as FIXTURE_PENDING_CENTS,
)
from app.services.grocery_context import (
    FIXTURE_POSTED_CENTS as FIXTURE_POSTED_CENTS,
)
from app.services.grocery_context import (
    SpendingSource,
    SpendingUnavailable,
    spending_input,
)
from app.services.job_submission import IdempotencyConflict, create_job
from app.services.plan_job import PlanJobInput, SpendingInput
from app.services.supermarket_overlay import (
    IngredientCostEstimator,
    attach_supermarket_estimate,
)

router = APIRouter(prefix="/grocery", tags=["grocery"])
DEMO_USER_ID = 1
PERIOD_MISMATCH_MESSAGE = "budget_period must match the current New York month"
DEMO_NOT_READY_MESSAGE = "Demo workspace is not ready."
CONFLICT_MESSAGE = "request_key already identifies different content"
SPENDING_UNAVAILABLE_MESSAGE = "Spending is unavailable"
INPUT_INVALID_MESSAGE = "The request has invalid parameters."
JOB_UNAVAILABLE_MESSAGE = "The job could not be stored."


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


def require_spending(
    session: Session, source: SpendingSource, now: datetime
) -> SpendingInput:
    loaded: SpendingInput | None = None
    try:
        loaded = spending_input(session, DEMO_USER_ID, source, now)
    except SpendingUnavailable:
        pass
    if loaded is None:
        raise HTTPException(status_code=503, detail=SPENDING_UNAVAILABLE_MESSAGE)
    return loaded


@router.get("/config")
def read_grocery_config(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[GroceryProviderSettings, Depends(get_provider_settings)],
) -> GroceryConfig:
    spending = require_spending(session, settings.spending_source, _ny_now())
    return GroceryConfig(
        budget_period=spending.period,
        source=settings.spending_source,
        posted_cents=spending.posted_cents,
        pending_cents=spending.pending_cents,
        notice=SAMPLE_ESTIMATE_NOTICE,
        recipes=[
            CatalogRef(id=recipe_id, name=recipe_id.replace("_", " "))
            for recipe_id in SUPPORTED_RECIPE_IDS
        ],
        ingredients=[
            CatalogRef(id=item.id, name=item.name) for item in INGREDIENTS.values()
        ],
        catalog_version=CATALOG_VERSION,
        spending_refreshed_at=spending.refreshed_at,
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
    settings = get_provider_settings()
    spending = require_spending(session, settings.spending_source, _ny_now())
    if body.request.budget_period != spending.period:
        raise HTTPException(status_code=422, detail=PERIOD_MISMATCH_MESSAGE)
    payload = cast(
        dict[str, object],
        PlanJobInput(
            request=body.request,
            monthly_limit_cents=body.monthly_limit_cents,
            spending=spending,
            spending_source=settings.spending_source,
        ).model_dump(mode="json"),
    )
    job: Job | None = None
    error_status: int | None = None
    error_detail: str | None = None
    try:
        job, _created = create_job(
            session, DEMO_USER_ID, "agent", idempotency_key, payload
        )
    except (IdempotencyConflict, IntegrityError) as exc:
        winner = _existing_agent_job(session, idempotency_key)
        if winner is not None and body.matches_stored_caller_fields(winner.payload):
            job = winner
        elif isinstance(exc, IntegrityError) and winner is None:
            error_status = 503
            error_detail = JOB_UNAVAILABLE_MESSAGE
        else:
            error_status = 409
            error_detail = CONFLICT_MESSAGE
    except ValueError:
        error_status = 422
        error_detail = INPUT_INVALID_MESSAGE
    if error_status is not None:
        raise HTTPException(status_code=error_status, detail=error_detail)
    assert job is not None
    session.commit()
    return GroceryJobAccepted(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}")
def read_grocery_job(
    job_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    estimator: Annotated[
        IngredientCostEstimator | None, Depends(get_supermarket_estimator)
    ],
) -> PlanJobView:
    job = session.get(Job, str(job_id))
    if job is None or job.user_id != DEMO_USER_ID or job.kind != "agent":
        raise HTTPException(status_code=404, detail="Job not found")
    result = job.result
    error_detail: dict[str, str] | None = None
    if job.status == "failed":
        detail = result.get("error_detail") if isinstance(result, dict) else None
        if isinstance(detail, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in detail.items()
        ):
            error_detail = cast(dict[str, str], detail)
        result = None
    if job.status == "succeeded" and isinstance(result, dict) and estimator is not None:
        result = attach_supermarket_estimate(result, estimator)
    return PlanJobView(
        id=job.id,
        status=job.status,
        result=result,
        error_code=job.error_code,
        error_detail=error_detail,
    )
