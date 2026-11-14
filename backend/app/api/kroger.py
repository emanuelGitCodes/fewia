"""Bind Kroger operations to the authenticated owner and one-use intents."""

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.deps import (
    get_current_user,
    get_kroger_cipher,
    get_kroger_client,
    get_kroger_pairing_cipher,
    get_provider_settings,
    get_session,
)
from app.domain.plan_proposal import ProposalInvalid, load_base_snapshot
from app.kroger_cart import CartPreview, build_preview
from app.kroger_customer import (
    KrogerConnectionChanged,
    customer_access_token,
    delete_rejected_access_token,
    delete_tokens,
    is_connected,
    redact_access_log,
    store_tokens,
)
from app.models import User
from app.plan_models import PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import (
    AUTHORIZE_PATH,
    CartItem,
    KrogerAuthRejected,
    KrogerCartUnknown,
    KrogerClient,
    KrogerUnavailable,
    Source,
)
from app.providers.kroger_fixture import FIXTURE_CODE
from app.security_models import KrogerOwner, SecurityIntent
from app.services import kroger_security as security
from app.services import security_admission as admission

router = APIRouter(prefix="/grocery/kroger", tags=["kroger"])
redact_access_log()
NOT_CONFIGURED_MESSAGE = "Kroger is not configured"
UNAVAILABLE_MESSAGE = "Kroger is unavailable"
INVALID_ZIP_MESSAGE = "zip_code MUST be exactly 5 digits"
NOT_CONNECTED_MESSAGE = "Kroger account is not connected"
CART_UNCONFIRMED_MESSAGE = "Kroger did not confirm the cart add"
REVISION_NOT_FOUND_MESSAGE = "The plan revision was not found."
REVISION_INVALID_MESSAGE = "The plan revision can no longer be used."
INVALID_ACTION_MESSAGE = "Kroger action is invalid or expired."
PROOF_REQUIRED_MESSAGE = "Kroger owner proof is required."
MAX_STATE_LENGTH = 512
_ZIP_CODE = re.compile(r"[0-9]{5}")


class StoreSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zip_code: StrictStr


class StoreView(BaseModel):
    location_id: str
    name: str
    address_line: str
    city: str
    state: str


class StoreSearchResponse(BaseModel):
    stores: list[StoreView]
    source: Source


class ConnectionResponse(BaseModel):
    connected: bool


class PairingBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    ticket: StrictStr = Field(min_length=43, max_length=43)


class PairingResponse(BaseModel):
    proof: str
    expires_in_seconds: Literal[28800] = 28800


class ConnectResponse(BaseModel):
    authorization_url: str


class CartPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    plan_revision_id: UUID
    location_id: StrictStr = Field(pattern=r"^[0-9A-Za-z]{8}$")


class ConfirmedCartPreview(CartPreview):
    confirmation_token: str | None
    expires_in_seconds: Literal[300] = 300


class CartAddBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    confirmation_token: StrictStr = Field(
        min_length=1, max_length=security.MAX_CART_TOKEN_LENGTH
    )


Settings = Annotated[GroceryProviderSettings, Depends(get_provider_settings)]
Database = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Client = Annotated[KrogerClient | None, Depends(get_kroger_client)]
TokenCipher = Annotated[Fernet | None, Depends(get_kroger_cipher)]
PairingCipher = Annotated[Fernet | None, Depends(get_kroger_pairing_cipher)]


@contextmanager
def _transaction(session: Session) -> Iterator[None]:
    try:
        yield
    except security.CartOutcomeUnknown:
        session.rollback()
        raise HTTPException(504, CART_UNCONFIRMED_MESSAGE) from None
    except security.SecurityIntentError:
        session.rollback()
        raise HTTPException(422, INVALID_ACTION_MESSAGE) from None
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(503, UNAVAILABLE_MESSAGE) from None
    except (
        HTTPException,
        admission.AdmissionLimitError,
        admission.OwnerUnavailableError,
    ):
        session.rollback()
        raise


def _configured(
    settings: GroceryProviderSettings,
    client: KrogerClient | None,
    cipher: Fernet | None,
    pairing_cipher: Fernet | None,
) -> tuple[KrogerClient, Fernet, Fernet]:
    confirmation = cipher if settings.kroger_mode == "fixture" else pairing_cipher
    if client is None or cipher is None or confirmation is None:
        raise HTTPException(503, NOT_CONFIGURED_MESSAGE)
    return client, cipher, confirmation


def _generation(
    request: Request, session: Session, user_id: int, settings: GroceryProviderSettings
) -> UUID:
    if settings.kroger_mode != "fixture":
        values = request.headers.getlist("x-fewia-kroger-owner")
        if len(values) != 1 or len(values[0]) != 43:
            raise HTTPException(403, PROOF_REQUIRED_MESSAGE)
        try:
            return security.validate_tab_proof(session, user_id, values[0])
        except security.SecurityIntentError:
            raise HTTPException(403, PROOF_REQUIRED_MESSAGE) from None
    admission.lock_active_owner(session, user_id)
    owner = session.scalar(
        select(KrogerOwner)
        .where(KrogerOwner.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if owner is None:
        owner = KrogerOwner(user_id=user_id, pairing_generation=uuid4())
        session.add(owner)
        session.flush()
    return owner.pairing_generation


def _query(request: Request, name: str, maximum: int) -> str:
    values = request.query_params.getlist(name)
    if len(values) != 1 or not 1 <= len(values[0]) <= maximum:
        raise security.SecurityIntentError()
    return values[0]


def _finish(settings: GroceryProviderSettings, outcome: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.kroger_return_url}?kroger={outcome}", 302)


@router.post("/pairing/redeem", response_model=PairingResponse)
def redeem_pairing(
    body: PairingBody,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    pairing_cipher: PairingCipher,
) -> PairingResponse:
    with _transaction(session):
        if settings.kroger_mode != "live" or pairing_cipher is None:
            raise HTTPException(503, NOT_CONFIGURED_MESSAGE)
        admission.reserve_action(session, user.id, "mutation")
        proof = security.redeem_pairing_ticket(session, user.id, body.ticket)
        session.commit()
    return PairingResponse(proof=proof)


@router.post("/connect", response_model=ConnectResponse)
def connect_kroger(
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> ConnectResponse:
    with _transaction(session):
        _configured(settings, client, cipher, pairing_cipher)
        admission.reserve_action(session, user.id, "mutation")
        _generation(request, session, user.id, settings)
        ticket = security.issue_oauth_start_ticket(session, user.id)
        session.commit()
    return ConnectResponse(
        authorization_url="/api/grocery/kroger/connect/start?"
        + urlencode({"ticket": ticket})
    )


@router.get("/connect/start")
def start_kroger_connect(
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> RedirectResponse:
    with _transaction(session):
        client, _, _ = _configured(settings, client, cipher, pairing_cipher)
        ticket = _query(request, "ticket", 43)
        admission.reserve_action(session, user.id, "mutation")
        security.consume_oauth_start_ticket(session, user.id, ticket)
        state = security.issue_oauth_state(session, user.id)
        session.commit()
    try:
        target = client.authorize_url(settings.kroger_redirect_uri, state)
    except ValueError:
        raise HTTPException(503, NOT_CONFIGURED_MESSAGE) from None
    return RedirectResponse(target, 302)


@router.get(f"/fixture{AUTHORIZE_PATH}")
def kroger_fixture_authorize(
    request: Request, settings: Settings, user: CurrentUser
) -> RedirectResponse:
    if settings.kroger_mode != "fixture":
        raise HTTPException(404, "Not found")
    try:
        state = _query(request, "state", MAX_STATE_LENGTH)
    except security.SecurityIntentError:
        raise HTTPException(400, INVALID_ACTION_MESSAGE) from None
    target = urlsplit(settings.kroger_redirect_uri)
    query = urlencode({"code": FIXTURE_CODE, "state": state})
    joined = f"{target.query}&{query}" if target.query else query
    return RedirectResponse(urlunsplit(target._replace(query=joined)), 302)


@router.get("/callback")
def kroger_callback(
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> RedirectResponse:
    user_id = user.id
    try:
        client, cipher, _ = _configured(settings, client, cipher, pairing_cipher)
        code = _query(request, "code", 4096)
        state = _query(request, "state", 43)
        params = request.query_params
        if (
            "error" in params
            or any(len(params.getlist(key)) != 1 for key in params)
            or any(len(value) > 4096 for value in params.values())
        ):
            raise security.SecurityIntentError()
        admission.reserve_action(session, user_id, "retailer")
        generation = security.consume_oauth_state(session, user_id, state)
        identity = security.connection_identity(session, user_id)
        if identity.pairing_generation != generation:
            raise security.SecurityIntentError()
        session.commit()
    except (admission.AdmissionLimitError, admission.OwnerUnavailableError):
        session.rollback()
        raise
    except (HTTPException, security.SecurityIntentError, SQLAlchemyError):
        session.rollback()
        return _finish(settings, "error")
    try:
        tokens = client.exchange_code(code, settings.kroger_redirect_uri)
        security.advance_connection(session, user_id, identity)
        store_tokens(session, user_id, cipher, tokens)
        session.commit()
    except (
        KrogerUnavailable,
        KrogerAuthRejected,
        admission.OwnerUnavailableError,
        security.SecurityIntentError,
        SQLAlchemyError,
    ):
        session.rollback()
        return _finish(settings, "error")
    return _finish(settings, "connected")


@router.get("/connection", response_model=ConnectionResponse)
def kroger_connection(
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> ConnectionResponse:
    with _transaction(session):
        _configured(settings, client, cipher, pairing_cipher)
        _generation(request, session, user.id, settings)
        connected = is_connected(session, user.id)
        session.commit()
    return ConnectionResponse(connected=connected)


@router.delete("/connection", status_code=204)
def kroger_disconnect(
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> Response:
    with _transaction(session):
        _configured(settings, client, cipher, pairing_cipher)
        admission.reserve_action(session, user.id, "mutation")
        _generation(request, session, user.id, settings)
        admission.lock_active_owner(session, user.id)
        delete_tokens(session, user.id)
        security.revoke_pairing(session, user.id)
        session.commit()
    return Response(status_code=204)


@router.post("/cart/preview", response_model=ConfirmedCartPreview)
def preview_kroger_cart(
    body: CartPreviewBody,
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> ConfirmedCartPreview:
    user_id = user.id
    with _transaction(session):
        client, _, confirmation = _configured(settings, client, cipher, pairing_cipher)
        admission.reserve_action(session, user_id, "retailer")
        generation = _generation(request, session, user_id, settings)
        revision = session.get(PlanRevision, body.plan_revision_id)
        if revision is None or revision.user_id != user_id:
            raise HTTPException(404, REVISION_NOT_FOUND_MESSAGE)
        try:
            snapshot = load_base_snapshot(revision)
        except ProposalInvalid:
            raise HTTPException(409, REVISION_INVALID_MESSAGE) from None
        identity = security.connection_identity(session, user_id)
        if identity.connection_version is None:
            raise HTTPException(409, NOT_CONNECTED_MESSAGE)
        session.commit()
    try:
        preview = build_preview(snapshot, client, body.location_id)
    except KrogerUnavailable:
        raise HTTPException(503, UNAVAILABLE_MESSAGE) from None
    with _transaction(session):
        if _generation(request, session, user_id, settings) != generation:
            raise security.SecurityIntentError()
        if security.connection_identity(session, user_id) != identity:
            raise security.SecurityIntentError()
        token = None
        if preview.items:
            token = security.issue_cart_confirmation(
                session,
                user_id,
                confirmation,
                body.plan_revision_id,
                [
                    security.CartLine(upc=i.upc, quantity=i.quantity)
                    for i in preview.items
                ],
            )
        session.commit()
    return ConfirmedCartPreview(**preview.model_dump(), confirmation_token=token)


def _cart_response(code: object) -> Response:
    if code == "added":
        return Response(status_code=204)
    status, message = {
        "not_connected": (409, NOT_CONNECTED_MESSAGE),
        "rejected": (422, INVALID_ACTION_MESSAGE),
        "unavailable": (503, UNAVAILABLE_MESSAGE),
    }.get(str(code), (504, CART_UNCONFIRMED_MESSAGE))
    raise HTTPException(status, message)


def _cart_row(session: Session, user_id: int, token: str) -> SecurityIntent | None:
    if not token.isascii():
        raise security.SecurityIntentError()
    return session.scalar(
        select(SecurityIntent)
        .where(
            SecurityIntent.user_id == user_id,
            SecurityIntent.kind == "cart_confirmation",
            SecurityIntent.digest == hashlib.sha256(token.encode("ascii")).hexdigest(),
        )
        .execution_options(populate_existing=True)
    )


@router.post("/cart/add", status_code=204)
def add_to_kroger_cart(
    body: CartAddBody,
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> Response:
    user_id = user.id
    with _transaction(session):
        client, cipher, confirmation = _configured(
            settings, client, cipher, pairing_cipher
        )
        row = _cart_row(session, user_id, body.confirmation_token)
        if row is None:
            _generation(request, session, user_id, settings)
            raise security.SecurityIntentError()
        if row.state != "pending":
            _generation(request, session, user_id, settings)
            outcome = security.get_cart_outcome(
                session, user_id, body.confirmation_token
            )
            code = (
                row.details.get("outcome")
                if outcome.state != "uncertain"
                else "unknown"
            )
            session.commit()
            return _cart_response(code)
        admission.reserve_action(session, user_id, "retailer")
        _generation(request, session, user_id, settings)
        claim = security.claim_cart_confirmation(
            session, user_id, confirmation, body.confirmation_token
        )
        if isinstance(claim, security.CartOutcome):
            row = _cart_row(session, user_id, body.confirmation_token)
            code = row.details.get("outcome") if row is not None else "unknown"
            session.rollback()
            return _cart_response(code)
        session.commit()
    code = "unknown"
    access_token: str | None = None
    try:
        access_token = customer_access_token(
            session,
            user_id,
            client,
            cipher,
            expected_connection_version=claim.connection_version,
            expected_pairing_generation=claim.pairing_generation,
        )
        session.commit()
        if access_token is None:
            code = "not_connected"
        else:
            client.add_to_cart(
                access_token, [CartItem(i.upc, i.quantity) for i in claim.items]
            )
            code = "added"
    except KrogerConnectionChanged:
        session.rollback()
        code = "not_connected"
    except KrogerAuthRejected:
        if access_token is not None:
            with _transaction(session):
                delete_rejected_access_token(
                    session,
                    user_id,
                    cipher,
                    access_token,
                    expected_connection_version=claim.connection_version,
                )
                session.commit()
        code = "not_connected"
    except KrogerUnavailable:
        session.rollback()
        code = "unavailable"
    except ValueError:
        session.rollback()
        code = "rejected"
    except (KrogerCartUnknown, SQLAlchemyError):
        session.rollback()
        code = "unknown"
    try:
        state: security.TerminalState = (
            "succeeded"
            if code == "added"
            else "uncertain"
            if code == "unknown"
            else "failed"
        )
        outcome = security.record_cart_outcome(session, user_id, claim.intent_id, state)
        if outcome.state == "uncertain":
            code = "unknown"
        row = session.get(SecurityIntent, claim.intent_id)
        if row is not None:
            row.details = {**row.details, "outcome": code}
        session.commit()
    except (
        SQLAlchemyError,
        security.SecurityIntentError,
        admission.OwnerUnavailableError,
    ):
        session.rollback()
        raise HTTPException(504, CART_UNCONFIRMED_MESSAGE) from None
    return _cart_response(code)


@router.post("/stores", response_model=StoreSearchResponse)
def find_kroger_stores(
    body: StoreSearchBody,
    request: Request,
    settings: Settings,
    session: Database,
    user: CurrentUser,
    client: Client,
    cipher: TokenCipher,
    pairing_cipher: PairingCipher,
) -> StoreSearchResponse:
    with _transaction(session):
        if not _ZIP_CODE.fullmatch(body.zip_code):
            raise HTTPException(422, INVALID_ZIP_MESSAGE)
        client, _, _ = _configured(settings, client, cipher, pairing_cipher)
        admission.reserve_action(session, user.id, "retailer")
        _generation(request, session, user.id, settings)
        session.commit()
    try:
        stores = client.find_stores(body.zip_code, limit=5)
        if not stores:
            stores = client.find_stores(body.zip_code, limit=5, radius_miles=50)
    except ValueError:
        raise HTTPException(422, INVALID_ZIP_MESSAGE) from None
    except KrogerUnavailable:
        raise HTTPException(503, UNAVAILABLE_MESSAGE) from None
    return StoreSearchResponse(
        stores=[
            StoreView(
                location_id=s.location_id,
                name=s.name,
                address_line=s.address_line,
                city=s.city,
                state=s.state,
            )
            for s in stores
        ],
        source=client.source,
    )
