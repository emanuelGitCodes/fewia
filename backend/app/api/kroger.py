"""HTTP route for Kroger store lookup; nothing from Kroger is stored."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictStr

from app.deps import get_kroger_client
from app.providers.kroger import KrogerClient, KrogerStore, KrogerUnavailable

router = APIRouter(prefix="/grocery/kroger", tags=["kroger"])
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
