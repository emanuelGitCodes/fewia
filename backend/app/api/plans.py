"""HTTP route that saves an immutable plan revision."""

from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_session
from app.domain.plan_revision import PlanSnapshot
from app.models import User
from app.plan_models import PlanRevision
from app.services import security_admission

router = APIRouter(prefix="/grocery", tags=["grocery"])


@router.post("/plans", status_code=201)
def create_plan_revision(
    body: PlanSnapshot,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    revision_id = uuid4()
    snapshot = cast(dict[str, object], body.model_dump(mode="json"))
    security_admission.reserve_action(session, user.id, "mutation")
    session.add(PlanRevision(id=revision_id, user_id=user.id, snapshot=snapshot))
    session.commit()
    return {"plan_revision_id": str(revision_id)}
