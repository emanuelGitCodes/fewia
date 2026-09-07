"""HTTP routes for immutable grocery evidence snapshots."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.services.evidence_store import load_evidence

router = APIRouter(prefix="/grocery", tags=["grocery"])
DEMO_USER_ID = 1
NOT_FOUND_MESSAGE = "Evidence not found"


class GroceryEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    snapshot: dict[str, object]


def get_session_factory() -> sessionmaker[Session]:
    return SessionLocal


def _is_revision_id(value: str) -> bool:
    return len(value) == 64 and all(
        "0" <= char <= "9" or "a" <= char <= "f" for char in value
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=NOT_FOUND_MESSAGE)


@router.get("/evidence/{revision_id}")
def read_grocery_evidence(
    revision_id: str,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> GroceryEvidenceView:
    if not _is_revision_id(revision_id):
        raise _not_found()
    try:
        snapshot = load_evidence(factory, DEMO_USER_ID, revision_id)
    except (TypeError, ValueError):
        raise _not_found() from None
    if snapshot is None:
        raise _not_found()
    return GroceryEvidenceView(revision_id=revision_id, snapshot=snapshot)
