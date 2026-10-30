"""HTTP routes that show, apply, or discard a plan proposal."""

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.demo import DEMO_USER_ID
from app.deps import get_session
from app.domain.plan_proposal import (
    ProposalInvalid,
    apply_operations,
    load_base_snapshot,
    parse_operations,
)
from app.domain.plan_revision import PlanSnapshot
from app.models import User
from app.plan_models import PlanProposal, PlanRevision

router = APIRouter(prefix="/grocery", tags=["grocery"])

PROPOSAL_NOT_FOUND_MESSAGE = "The plan proposal was not found."
PROPOSAL_DISCARDED_MESSAGE = "The plan proposal was discarded."
PROPOSAL_APPLIED_MESSAGE = "The plan proposal was already applied."
PROPOSAL_STALE_MESSAGE = "The plan proposal can no longer be applied."


def _load(session: Session, proposal_id: UUID, *, lock: bool = False) -> PlanProposal:
    if session.get(User, DEMO_USER_ID) is None:
        raise HTTPException(status_code=503, detail=grocery_api.DEMO_NOT_READY_MESSAGE)
    statement = select(PlanProposal).where(
        PlanProposal.id == proposal_id, PlanProposal.user_id == DEMO_USER_ID
    )
    if lock:
        statement = statement.with_for_update()
    proposal = session.scalars(statement).one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND_MESSAGE)
    return proposal


def _preview(session: Session, proposal: PlanProposal) -> PlanSnapshot:
    base = session.get(PlanRevision, proposal.base_plan_revision_id)
    if base is None:
        raise HTTPException(status_code=409, detail=PROPOSAL_STALE_MESSAGE)
    try:
        return apply_operations(
            load_base_snapshot(base), parse_operations(proposal.operations)
        )
    except ProposalInvalid:
        session.refresh(proposal, with_for_update=True)
        if proposal.status == "pending":
            proposal.status = "discarded"
            proposal.updated_at = datetime.now(UTC)
            session.commit()
        raise HTTPException(status_code=409, detail=PROPOSAL_STALE_MESSAGE) from None


@router.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> dict[str, object]:
    proposal = _load(session, proposal_id)
    was_discarded = proposal.status == "discarded"
    preview: dict[str, object] | None
    try:
        preview = _preview(session, proposal).model_dump(mode="json")
    except HTTPException:
        if not was_discarded:
            raise
        preview = None
    applied_id = proposal.applied_plan_revision_id
    return {
        "id": str(proposal.id),
        "status": proposal.status,
        "base_plan_revision_id": str(proposal.base_plan_revision_id),
        "operations": proposal.operations,
        "preview": preview,
        "applied_plan_revision_id": None if applied_id is None else str(applied_id),
    }


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> dict[str, str]:
    proposal = _load(session, proposal_id, lock=True)
    if proposal.status == "discarded":
        raise HTTPException(status_code=409, detail=PROPOSAL_DISCARDED_MESSAGE)
    if proposal.applied_plan_revision_id is not None:
        return {"plan_revision_id": str(proposal.applied_plan_revision_id)}
    revision_id = uuid4()
    preview = _preview(session, proposal)
    snapshot = cast(dict[str, object], preview.model_dump(mode="json"))
    session.add(PlanRevision(id=revision_id, user_id=DEMO_USER_ID, snapshot=snapshot))
    session.flush()
    proposal.status = "applied"
    proposal.applied_plan_revision_id = revision_id
    proposal.updated_at = datetime.now(UTC)
    session.commit()
    return {"plan_revision_id": str(revision_id)}


@router.post("/proposals/{proposal_id}/discard")
def discard_proposal(
    proposal_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> dict[str, str]:
    proposal = _load(session, proposal_id, lock=True)
    if proposal.status == "applied":
        raise HTTPException(status_code=409, detail=PROPOSAL_APPLIED_MESSAGE)
    if proposal.status == "pending":
        proposal.status = "discarded"
        proposal.updated_at = datetime.now(UTC)
        session.commit()
    return {"status": "discarded"}
