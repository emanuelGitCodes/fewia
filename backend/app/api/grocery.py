"""HTTP routes for fixture grocery planning jobs."""

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.grocery_models import (
    CatalogRef,
    CreateGroceryJobBody,
    GroceryConfig,
    GroceryJobAccepted,
    PlanJobView,
)
from app.demo import DEMO_USER_ID
from app.deps import get_provider_settings, get_session
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
from app.services.job_submission import (
    JobConflict,
    JobInputInvalid,
    JobUnavailable,
    reuse_job,
    submit_job,
)
from app.services.plan_job import PlanJobInput, SpendingInput

router = APIRouter(prefix="/grocery", tags=["grocery"])
PERIOD_MISMATCH_MESSAGE = "budget_period must match the current New York month"
DEMO_NOT_READY_MESSAGE = "Demo workspace is not ready."
CONFLICT_MESSAGE = "request_key already identifies different content"
SPENDING_UNAVAILABLE_MESSAGE = "Spending is unavailable"
INPUT_INVALID_MESSAGE = "The request has invalid parameters."
JOB_UNAVAILABLE_MESSAGE = "The job could not be stored."


def _ny_now() -> datetime:
    return datetime.now(UTC).astimezone(NEW_YORK)


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
    matches = body.matches_stored_caller_fields
    existing: Job | None = None
    conflict = False
    try:
        existing = reuse_job(session, DEMO_USER_ID, "agent", idempotency_key, matches)
    except JobConflict:
        conflict = True
    if conflict:
        raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE)
    if existing is not None:
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
        job = submit_job(
            session, DEMO_USER_ID, "agent", idempotency_key, payload, matches
        )
    except JobConflict:
        error_status = 409
        error_detail = CONFLICT_MESSAGE
    except JobUnavailable:
        error_status = 503
        error_detail = JOB_UNAVAILABLE_MESSAGE
    except JobInputInvalid:
        error_status = 422
        error_detail = INPUT_INVALID_MESSAGE
    if error_status is not None:
        raise HTTPException(status_code=error_status, detail=error_detail)
    assert job is not None
    return GroceryJobAccepted(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}")
def read_grocery_job(
    job_id: UUID,
    session: Annotated[Session, Depends(get_session)],
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
    return PlanJobView(
        id=job.id,
        status=job.status,
        result=result,
        error_code=job.error_code,
        error_detail=error_detail,
    )
