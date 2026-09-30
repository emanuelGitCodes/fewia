"""HTTP routes for grocery chat jobs and provider capabilities."""

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.api.chat_models import CreateChatJobBody
from app.api.grocery_models import GroceryJobAccepted, GroceryJobView
from app.demo import DEMO_USER_ID
from app.deps import get_provider_settings, get_session, get_supermarket_estimator
from app.domain.budget import NEW_YORK
from app.job_models import Job
from app.models import User
from app.provider_runtime import ProviderCapabilities, capabilities
from app.provider_settings import GroceryProviderSettings
from app.services.chat_history import ChatContextUnavailable, load_chat_context
from app.services.chat_job import ChatHistoryTurn, ChatJobInput
from app.services.job_submission import IdempotencyConflict, create_job
from app.services.supermarket_overlay import (
    IngredientCostEstimator,
    attach_supermarket_estimate,
)

router = APIRouter(prefix="/grocery", tags=["grocery"])
CHAT_KEY_PREFIX = "chat:"
CHAT_UNAVAILABLE_MESSAGE = "Chat is not configured."
CHAT_CONTEXT_MESSAGE = "Chat context is unavailable."
JOB_NOT_FOUND_MESSAGE = "Job not found"
IdempotencyKey = Annotated[str, Header(min_length=1, max_length=120)]


def _ny_now() -> datetime:
    return datetime.now(UTC).astimezone(NEW_YORK)


def _existing_chat_job(session: Session, request_key: str) -> Job | None:
    return grocery_api._existing_agent_job(session, request_key)


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
    existing = _existing_chat_job(session, request_key)
    if existing is not None:
        if not body.matches_stored_caller_fields(existing.payload):
            raise HTTPException(status_code=409, detail=grocery_api.CONFLICT_MESSAGE)
        session.commit()
        return GroceryJobAccepted(job_id=existing.id, status=existing.status)
    settings = get_provider_settings()
    if not capabilities(settings)["chat_configured"]:
        raise HTTPException(status_code=503, detail=CHAT_UNAVAILABLE_MESSAGE)
    if session.get(User, DEMO_USER_ID) is None:
        raise HTTPException(status_code=503, detail=grocery_api.DEMO_NOT_READY_MESSAGE)
    spending = grocery_api.require_spending(
        session, settings.spending_source, _ny_now()
    )
    loaded: tuple[list[dict[str, str]], dict[str, object] | None] | None = None
    try:
        loaded = load_chat_context(session, DEMO_USER_ID, body.previous_job_id)
    except ChatContextUnavailable:
        pass
    if loaded is None:
        raise HTTPException(status_code=409, detail=CHAT_CONTEXT_MESSAGE)
    history, previous_request = loaded
    turns = [ChatHistoryTurn.model_validate(item) for item in history]
    payload = cast(
        dict[str, object],
        ChatJobInput(
            operation="chat",
            message=body.message,
            monthly_limit_cents=body.monthly_limit_cents,
            plan_cap_cents=body.plan_cap_cents,
            previous_job_id=body.previous_job_id,
            history=turns,
            previous_request=previous_request,
            spending=spending,
            spending_source=settings.spending_source,
        ).model_dump(mode="json"),
    )
    job: Job | None = None
    error_status: int | None = None
    error_detail: str | None = None
    try:
        job, _created = create_job(session, DEMO_USER_ID, "agent", request_key, payload)
    except (IdempotencyConflict, IntegrityError) as exc:
        winner = _existing_chat_job(session, request_key)
        if winner is not None and body.matches_stored_caller_fields(winner.payload):
            job = winner
        elif isinstance(exc, IntegrityError) and winner is None:
            error_status = 503
            error_detail = grocery_api.JOB_UNAVAILABLE_MESSAGE
        else:
            error_status = 409
            error_detail = grocery_api.CONFLICT_MESSAGE
    except ValueError:
        error_status = 422
        error_detail = grocery_api.INPUT_INVALID_MESSAGE
    if error_status is not None:
        raise HTTPException(status_code=error_status, detail=error_detail)
    assert job is not None
    session.commit()
    return GroceryJobAccepted(job_id=job.id, status=job.status)


@router.get("/chat/jobs/{job_id}")
def read_chat_job(
    job_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    estimator: Annotated[
        IngredientCostEstimator | None, Depends(get_supermarket_estimator)
    ],
) -> GroceryJobView:
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
    if job.status == "succeeded" and isinstance(result, dict) and estimator is not None:
        result = attach_supermarket_estimate(result, estimator)
    return GroceryJobView(
        id=job.id,
        status=job.status,
        result=result,
        error_code=job.error_code,
    )
