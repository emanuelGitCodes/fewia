"""HTTP routes for Kroger store lookup, customer sign-in, and the cart.

Store lookup and the cart preview store nothing. Sign-in stores only the
encrypted customer tokens; disconnect deletes them. The cart add sends the
posted items to Kroger once and keeps nothing.
"""

import re
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.demo import DEMO_USER_ID
from app.deps import (
    get_kroger_cipher,
    get_kroger_client,
    get_provider_settings,
    get_session,
)
from app.domain.plan_proposal import ProposalInvalid, load_base_snapshot
from app.kroger_cart import CartPreview, build_preview
from app.kroger_customer import (
    COOKIE_PATH,
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    customer_access_token,
    delete_tokens,
    is_connected,
    make_state,
    new_nonce,
    redact_access_log,
    state_matches,
    store_tokens,
)
from app.plan_models import PlanRevision
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import (
    CartItem,
    KrogerAuthRejected,
    KrogerCartUnknown,
    KrogerClient,
    KrogerStore,
    KrogerUnavailable,
)

router = APIRouter(prefix="/grocery/kroger", tags=["kroger"])
redact_access_log()
NOT_CONFIGURED_MESSAGE = "Kroger is not configured"
UNAVAILABLE_MESSAGE = "Kroger is unavailable"
INVALID_ZIP_MESSAGE = "zip_code MUST be exactly 5 digits"
NOT_CONNECTED_MESSAGE = "Kroger account is not connected"
CART_UNCONFIRMED_MESSAGE = "Kroger did not confirm the cart add"
REVISION_NOT_FOUND_MESSAGE = "The plan revision was not found."
REVISION_INVALID_MESSAGE = "The plan revision can no longer be used."
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


class ConnectionResponse(BaseModel):
    connected: bool


class CartPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_revision_id: UUID
    location_id: StrictStr = Field(pattern=r"^[0-9A-Za-z]{8}$")


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upc: StrictStr = Field(pattern=r"^[0-9]{8,14}$")
    quantity: StrictInt = Field(ge=1, le=10)


class CartAddBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CartLine] = Field(min_length=1, max_length=30)

    @field_validator("items")
    @classmethod
    def validate_unique_upcs(cls, value: list[CartLine]) -> list[CartLine]:
        if len({line.upc for line in value}) != len(value):
            raise ValueError("items must not repeat a upc")
        return value


Settings = Annotated[GroceryProviderSettings, Depends(get_provider_settings)]


def _host_key(netloc: str, scheme: str) -> tuple[str | None, int | None]:
    try:
        parts = urlsplit(f"//{netloc}")
        return parts.hostname, parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        return None, None


def _finish(settings: GroceryProviderSettings, outcome: str) -> RedirectResponse:
    response = RedirectResponse(f"{settings.kroger_return_url}?kroger={outcome}", 302)
    response.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/connect")
def connect_kroger(
    request: Request,
    settings: Settings,
    client: Annotated[KrogerClient | None, Depends(get_kroger_client)],
    cipher: Annotated[Fernet | None, Depends(get_kroger_cipher)],
) -> RedirectResponse:
    """Send the browser to Kroger sign-in with a single-use signed state."""
    if client is None or cipher is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MESSAGE)
    redirect = urlsplit(settings.kroger_redirect_uri)
    wanted = _host_key(redirect.netloc, redirect.scheme)
    if _host_key(request.headers.get("host", ""), request.url.scheme) != wanted:
        origin = f"{redirect.scheme}://{redirect.netloc}"
        return RedirectResponse(f"{origin}{COOKIE_PATH}/connect", 302)
    nonce = new_nonce()
    url: str | None = None
    try:
        url = client.authorize_url(
            settings.kroger_redirect_uri, make_state(cipher, nonce)
        )
    except ValueError:
        pass
    if url is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MESSAGE)
    response = RedirectResponse(url, 302)
    response.set_cookie(
        STATE_COOKIE,
        nonce,
        max_age=STATE_TTL_SECONDS,
        path=COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=redirect.scheme == "https",
    )
    return response


@router.get("/callback")
def kroger_callback(
    request: Request,
    settings: Settings,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[KrogerClient | None, Depends(get_kroger_client)],
    cipher: Annotated[Fernet | None, Depends(get_kroger_cipher)],
) -> RedirectResponse:
    """Finish sign-in; never echo the code, the state, or Kroger's error."""
    params = request.query_params
    code = params.get("code")
    state = params.get("state")
    stored = False
    if (
        client is not None
        and cipher is not None
        and code
        and state
        and "error" not in params
        and state_matches(cipher, state, request.cookies.get(STATE_COOKIE))
    ):
        try:
            tokens = client.exchange_code(code, settings.kroger_redirect_uri)
            store_tokens(session, DEMO_USER_ID, cipher, tokens)
            stored = True
        except (KrogerUnavailable, SQLAlchemyError):
            pass
    return _finish(settings, "connected" if stored else "error")


@router.get("/connection", response_model=ConnectionResponse)
def kroger_connection(
    session: Annotated[Session, Depends(get_session)],
) -> ConnectionResponse:
    """Say whether the demo user has connected a Kroger account."""
    return ConnectionResponse(connected=is_connected(session, DEMO_USER_ID))


@router.delete("/connection", status_code=204)
def kroger_disconnect(session: Annotated[Session, Depends(get_session)]) -> Response:
    """Delete the stored Kroger tokens. Succeeds when there are none."""
    delete_tokens(session, DEMO_USER_ID)
    return Response(status_code=204)


@router.post("/cart/preview", response_model=CartPreview)
def preview_kroger_cart(
    body: CartPreviewBody,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[KrogerClient | None, Depends(get_kroger_client)],
) -> CartPreview:
    """Match the plan's grocery lines to Kroger products. Writes nothing."""
    if client is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MESSAGE)
    revision = session.get(PlanRevision, body.plan_revision_id)
    if revision is None or revision.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail=REVISION_NOT_FOUND_MESSAGE)
    try:
        snapshot = load_base_snapshot(revision)
        return build_preview(snapshot, client, body.location_id)
    except ProposalInvalid:
        raise HTTPException(409, REVISION_INVALID_MESSAGE) from None
    except KrogerUnavailable:
        raise HTTPException(503, UNAVAILABLE_MESSAGE) from None


@router.post("/cart/add", status_code=204)
def add_to_kroger_cart(
    body: CartAddBody,
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[KrogerClient | None, Depends(get_kroger_client)],
    cipher: Annotated[Fernet | None, Depends(get_kroger_cipher)],
) -> Response:
    """Send the posted items to the connected Kroger cart once."""
    if client is None or cipher is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MESSAGE)
    try:
        token = customer_access_token(session, DEMO_USER_ID, client, cipher)
        if token is None:
            raise HTTPException(409, NOT_CONNECTED_MESSAGE)
        lines = [CartItem(line.upc, line.quantity) for line in body.items]
        client.add_to_cart(token, lines)
    except KrogerAuthRejected:
        delete_tokens(session, DEMO_USER_ID)
        raise HTTPException(409, NOT_CONNECTED_MESSAGE) from None
    except KrogerUnavailable:
        raise HTTPException(503, UNAVAILABLE_MESSAGE) from None
    except KrogerCartUnknown:
        raise HTTPException(504, CART_UNCONFIRMED_MESSAGE) from None
    return Response(status_code=204)


@router.post("/stores", response_model=StoreSearchResponse)
def find_kroger_stores(
    body: StoreSearchBody,
    client: Annotated[KrogerClient | None, Depends(get_kroger_client)],
) -> StoreSearchResponse:
    """Return Kroger stores near a ZIP posted in the body."""
    if not _ZIP_CODE.fullmatch(body.zip_code):
        raise HTTPException(status_code=422, detail=INVALID_ZIP_MESSAGE)
    if client is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MESSAGE)
    failure: int | None = None
    stores: list[KrogerStore] = []
    try:
        stores = client.find_stores(body.zip_code, limit=5)
        if not stores:
            stores = client.find_stores(body.zip_code, limit=5, radius_miles=50)
    except ValueError:
        failure = 422
    except KrogerUnavailable:
        failure = 503
    if failure == 422:
        raise HTTPException(status_code=422, detail=INVALID_ZIP_MESSAGE)
    if failure == 503:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE)
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
        ]
    )
