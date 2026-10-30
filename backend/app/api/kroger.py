"""HTTP routes for Kroger store lookup and customer sign-in.

Store lookup stores nothing. Sign-in stores only the encrypted customer tokens.
"""

import re
from typing import Annotated
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, StrictStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.demo import DEMO_USER_ID
from app.deps import (
    get_kroger_cipher,
    get_kroger_client,
    get_provider_settings,
    get_session,
)
from app.kroger_customer import (
    COOKIE_PATH,
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    is_connected,
    make_state,
    new_nonce,
    redact_access_log,
    state_matches,
    store_tokens,
)
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import KrogerClient, KrogerStore, KrogerUnavailable

router = APIRouter(prefix="/grocery/kroger", tags=["kroger"])
redact_access_log()
NOT_CONFIGURED_MESSAGE = "Kroger is not configured"
UNAVAILABLE_MESSAGE = "Kroger is unavailable"
INVALID_ZIP_MESSAGE = "zip_code MUST be exactly 5 digits"
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
