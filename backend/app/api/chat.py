"""HTTP routes for grocery chat jobs and provider capabilities."""

import re
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.api.chat_models import CreateChatJobBody
from app.api.grocery_models import GroceryJobAccepted, GroceryJobView
from app.demo import DEMO_USER_ID
from app.deps import (
    get_kroger_client,
    get_provider_settings,
    get_session,
    get_supermarket_estimator,
)
from app.domain.budget import NEW_YORK
from app.domain.plan_revision import PlanRevisionInput, PlanSnapshot
from app.job_models import Job
from app.models import User
from app.plan_models import PlanRevision
from app.provider_runtime import ProviderCapabilities, capabilities
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import KrogerClient
from app.services.chat_history import ChatContextUnavailable, load_chat_context
from app.services.chat_job import ChatHistoryTurn, ChatJobInput
from app.services.job_submission import (
    JobConflict,
    JobInputInvalid,
    JobUnavailable,
    reuse_job,
    submit_job,
)
from app.services.kroger_overlay import attach_kroger_quote
from app.services.supermarket_overlay import (
    IngredientCostEstimator,
    attach_supermarket_estimate,
)

router = APIRouter(prefix="/grocery", tags=["grocery"])
CHAT_KEY_PREFIX = "chat:"
CHAT_UNAVAILABLE_MESSAGE = "Chat is not configured."
CHAT_CONTEXT_MESSAGE = "Chat context is unavailable."
PLAN_REVISION_MESSAGE = "The plan is not available. Refresh the page and try again."
JOB_NOT_FOUND_MESSAGE = "Job not found"
LOCATION_ID_MESSAGE = "location_id MUST be 8 letters or digits"
_LOCATION_ID = re.compile(r"[0-9A-Za-z]{8}")
IdempotencyKey = Annotated[str, Header(min_length=1, max_length=120)]


def _ny_now() -> datetime:
    return datetime.now(UTC).astimezone(NEW_YORK)


@router.get("/providers")
def read_providers(
    settings: Annotated[GroceryProviderSettings, Depends(get_provider_settings)],
) -> ProviderCapabilities:
    return capabilities(settings)


@router.post("/chat/jobs", status_code=202)
def create_chat_job(
    body: CreateChatJobBody,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: IdempotencyKey,
) -> GroceryJobAccepted:
    request_key = f"{CHAT_KEY_PREFIX}{idempotency_key}"
    matches = body.matches_stored_caller_fields
    existing: Job | None = None
    conflict = False
    try:
        existing = reuse_job(session, DEMO_USER_ID, "agent", request_key, matches)
    except JobConflict:
        conflict = True
    if conflict:
        raise HTTPException(status_code=409, detail=grocery_api.CONFLICT_MESSAGE)
    if existing is not None:
        return GroceryJobAccepted(job_id=existing.id, status=existing.status)
    settings = get_provider_settings()
    if not capabilities(settings)["chat_configured"]:
        raise HTTPException(status_code=503, detail=CHAT_UNAVAILABLE_MESSAGE)
    if session.get(User, DEMO_USER_ID) is None:
        raise HTTPException(status_code=503, detail=grocery_api.DEMO_NOT_READY_MESSAGE)
    spending = grocery_api.require_spending(
        session, settings.spending_source, _ny_now()
    )
    loaded: (
        tuple[list[dict[str, str]], dict[str, object] | None, list[str] | None] | None
    ) = None
    try:
        loaded = load_chat_context(session, DEMO_USER_ID, body.previous_job_id)
    except ChatContextUnavailable:
        pass
    if loaded is None:
        raise HTTPException(status_code=409, detail=CHAT_CONTEXT_MESSAGE)
    history, previous_request, previous_ingredient_ids = loaded
    plan_revision: PlanRevisionInput | None = None
    if body.plan_revision_id is not None:
        row = session.get(PlanRevision, body.plan_revision_id)
        if row is not None and row.user_id == DEMO_USER_ID:
            try:
                plan_revision = PlanRevisionInput(
                    id=row.id, snapshot=PlanSnapshot.model_validate(row.snapshot)
                )
            except ValidationError:
                plan_revision = None
        if plan_revision is None:
            raise HTTPException(status_code=409, detail=PLAN_REVISION_MESSAGE)
    turns = [ChatHistoryTurn.model_validate(item) for item in history]
    payload = cast(
        dict[str, object],
        ChatJobInput(
            operation="chat",
            message=body.message,
            monthly_limit_cents=body.monthly_limit_cents,
            plan_cap_cents=body.plan_cap_cents,
            previous_job_id=body.previous_job_id,
            plan_revision_id=body.plan_revision_id,
            plan_revision=plan_revision,
            history=turns,
            previous_request=previous_request,
            previous_ingredient_ids=previous_ingredient_ids,
            spending=spending,
            spending_source=settings.spending_source,
        ).model_dump(mode="json"),
    )
    job: Job | None = None
    error_status: int | None = None
    error_detail: str | None = None
    try:
        job = submit_job(session, DEMO_USER_ID, "agent", request_key, payload, matches)
    except JobConflict:
        error_status = 409
        error_detail = grocery_api.CONFLICT_MESSAGE
    except JobUnavailable:
        error_status = 503
        error_detail = grocery_api.JOB_UNAVAILABLE_MESSAGE
    except JobInputInvalid:
        error_status = 422
        error_detail = grocery_api.INPUT_INVALID_MESSAGE
    if error_status is not None:
        raise HTTPException(status_code=error_status, detail=error_detail)
    assert job is not None
    return GroceryJobAccepted(job_id=job.id, status=job.status)


@router.get("/chat/jobs/{job_id}")
def read_chat_job(
    job_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    estimator: Annotated[
        IngredientCostEstimator | None, Depends(get_supermarket_estimator)
    ],
    kroger: Annotated[KrogerClient | None, Depends(get_kroger_client)],
    location_id: str | None = None,
) -> GroceryJobView:
    if location_id is not None and not _LOCATION_ID.fullmatch(location_id):
        raise HTTPException(status_code=422, detail=LOCATION_ID_MESSAGE)
    job = session.get(Job, str(job_id))
    payload = job.payload if job is not None else None
    if (
        job is None
        or job.user_id != DEMO_USER_ID
        or job.kind != "agent"
        or not isinstance(payload, dict)
        or payload.get("operation") != "chat"
    ):
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND_MESSAGE)
    result = job.result
    if job.status == "succeeded" and isinstance(result, dict):
        result = attach_supermarket_estimate(result, estimator)
        if location_id is not None and kroger is not None:
            result = attach_kroger_quote(
                result, kroger, location_id, lambda: datetime.now(UTC)
            )
    return GroceryJobView(
        id=job.id,
        status=job.status,
        result=result,
        error_code=job.error_code,
    )
