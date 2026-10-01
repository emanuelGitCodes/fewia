"""HTTP routes for Plaid Item sync jobs."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.grocery_models import GroceryJobAccepted, GroceryJobView
from app.api.sync_models import CreateSyncJobBody
from app.demo import DEMO_USER_ID
from app.deps import get_session
from app.job_models import Job
from app.plaid_models import PlaidItem
from app.provider_runtime import capabilities
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    load_provider_settings,
)
from app.services.job_submission import (
    JobConflict,
    JobInputInvalid,
    JobUnavailable,
    reuse_job,
    submit_job,
)
from app.services.sync_job import SyncJobInput

router = APIRouter(prefix="/grocery/sync", tags=["grocery"])
REQUEST_KEY_PREFIX = "sync:"
CONFLICT_MESSAGE = "request_key already identifies different content"
ITEM_NOT_FOUND_MESSAGE = "Plaid Item is missing or not owned"
JOB_NOT_FOUND_MESSAGE = "Job not found"
CONFIG_UNAVAILABLE_MESSAGE = "Provider configuration is unavailable."
JOB_UNAVAILABLE_MESSAGE = "Job could not be created."
INVALID_JOB_MESSAGE = "Job request is invalid"


def get_provider_settings() -> GroceryProviderSettings:
    return load_provider_settings()


def _owned_item(session: Session, item_id: str) -> PlaidItem | None:
    return session.scalar(
        select(PlaidItem).where(
            PlaidItem.id == item_id,
            PlaidItem.user_id == DEMO_USER_ID,
        )
    )


def _is_plaid_sync_payload(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("operation") == "plaid_sync"


def _plaid_is_configured() -> bool:
    configured = False
    try:
        configured = capabilities(get_provider_settings())["plaid_configured"]
    except ProviderConfigurationError:
        pass
    return configured


@router.post("/jobs", status_code=202)
def create_sync_job(
    body: CreateSyncJobBody,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[
        str, Header(min_length=1, max_length=120, pattern=r"^\S+$")
    ],
) -> GroceryJobAccepted:
    request_key = f"{REQUEST_KEY_PREFIX}{idempotency_key}"
    matches = body.matches_stored_caller_fields
    existing: Job | None = None
    conflict = False
    try:
        existing = reuse_job(session, DEMO_USER_ID, "sync", request_key, matches)
    except JobConflict:
        conflict = True
    if conflict:
        raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE)
    if existing is not None:
        return GroceryJobAccepted(job_id=existing.id, status=existing.status)
    if _owned_item(session, body.item_id) is None:
        raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND_MESSAGE)
    if not _plaid_is_configured():
        raise HTTPException(status_code=503, detail=CONFIG_UNAVAILABLE_MESSAGE)
    payload = cast(
        dict[str, object],
        SyncJobInput(item_id=body.item_id).model_dump(mode="json"),
    )
    job: Job | None = None
    failure: tuple[int, str] | None = None
    try:
        job = submit_job(session, DEMO_USER_ID, "sync", request_key, payload, matches)
    except JobConflict:
        failure = (409, CONFLICT_MESSAGE)
    except JobUnavailable:
        failure = (503, JOB_UNAVAILABLE_MESSAGE)
    except JobInputInvalid:
        failure = (422, INVALID_JOB_MESSAGE)
    if failure is not None:
        raise HTTPException(status_code=failure[0], detail=failure[1])
    assert job is not None
    return GroceryJobAccepted(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}")
def read_sync_job(
    job_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> GroceryJobView:
    job = session.get(Job, str(job_id))
    if (
        job is None
        or job.user_id != DEMO_USER_ID
        or job.kind != "sync"
        or not _is_plaid_sync_payload(job.payload)
    ):
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND_MESSAGE)
    return GroceryJobView(
        id=job.id,
        status=job.status,
        result=job.result,
        error_code=job.error_code,
    )
