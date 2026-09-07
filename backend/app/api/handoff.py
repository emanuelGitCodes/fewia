"""HTTP routes for Instacart development shopping-list handoff."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.api.handoff_models import (
    HandoffRouteError,
    job_shopping_payload,
    may_retry,
)
from app.api.handoff_types import CreateHandoffBody, RetryHandoffBody
from app.db import SessionLocal
from app.provider_runtime import build_instacart
from app.provider_settings import ProviderConfigurationError, load_provider_settings
from app.services.handoff_dispatch import dispatch_handoff
from app.services.handoff_intents import (
    HandoffNotFound,
    HandoffView,
    prepare_handoff,
    read_handoff,
)

router = APIRouter(prefix="/grocery", tags=["grocery"])
DEMO_USER_ID = 1
_HANDOFF_MISSING = "Handoff not found"
_REBUILD = "Plan requires a rebuild."
_UNAVAILABLE = "Instacart is unavailable."


def get_session_factory() -> sessionmaker[Session]:
    return SessionLocal


Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


def _fail(status: int, detail: str) -> NoReturn:
    raise HTTPException(status_code=status, detail=detail)


def _dispatch(
    factory: sessionmaker[Session],
    handoff_id: str,
    retry: bool = False,
    expected_attempt: int | None = None,
) -> HandoffView:
    provider = None
    config_failed = False
    missing = False
    view: HandoffView | None = None
    try:
        provider = build_instacart(load_provider_settings())
    except ProviderConfigurationError:
        config_failed = True
    if config_failed or provider is None:
        _fail(503, _UNAVAILABLE)
    client = provider
    try:
        view = dispatch_handoff(
            factory,
            client,
            DEMO_USER_ID,
            handoff_id,
            retry=retry,
            expected_attempt=expected_attempt,
        )
    except HandoffNotFound:
        missing = True
    finally:
        client.close()
    if missing or view is None:
        _fail(404, _HANDOFF_MISSING)
    return view


@router.post("/handoffs")
def create_handoff(body: CreateHandoffBody, factory: Factory) -> HandoffView:
    route_error: HandoffRouteError | None = None
    failed = False
    view: HandoffView | None = None
    try:
        payload = job_shopping_payload(factory, str(body.job_id))
        view = prepare_handoff(factory, DEMO_USER_ID, payload)
    except HandoffRouteError as exc:
        route_error = exc
    except ValueError:
        failed = True
    if route_error is not None:
        _fail(route_error.status, route_error.detail)
    if failed or view is None:
        _fail(409, _REBUILD)
    if view.state != "prepared":
        return view
    return _dispatch(factory, view.id)


@router.get("/handoffs/{handoff_id}")
def read_owned_handoff(handoff_id: UUID, factory: Factory) -> HandoffView:
    view = read_handoff(factory, DEMO_USER_ID, str(handoff_id))
    if view is None:
        _fail(404, _HANDOFF_MISSING)
    return view


@router.post("/handoffs/{handoff_id}/retry")
def retry_handoff(
    handoff_id: UUID, body: RetryHandoffBody, factory: Factory
) -> HandoffView:
    view = read_handoff(factory, DEMO_USER_ID, str(handoff_id))
    if view is None:
        _fail(404, _HANDOFF_MISSING)
    if not may_retry(view, body.expected_attempt):
        return view
    return _dispatch(factory, str(handoff_id), True, body.expected_attempt)
