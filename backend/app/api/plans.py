"""HTTP route that saves an immutable plan revision."""

from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.demo import DEMO_USER_ID
from app.deps import get_session
from app.domain.plan_revision import PlanSnapshot
from app.models import User
from app.plan_models import PlanRevision

router = APIRouter(prefix="/grocery", tags=["grocery"])


@router.post("/plans", status_code=201)
def create_plan_revision(
    body: PlanSnapshot,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    if session.get(User, DEMO_USER_ID) is None:
        raise HTTPException(status_code=503, detail=grocery_api.DEMO_NOT_READY_MESSAGE)
    revision_id = uuid4()
    snapshot = cast(dict[str, object], body.model_dump(mode="json"))
    session.add(PlanRevision(id=revision_id, user_id=DEMO_USER_ID, snapshot=snapshot))
    session.commit()
    return {"plan_revision_id": str(revision_id)}
