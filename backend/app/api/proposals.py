"""HTTP routes that show, apply, or discard a plan proposal."""

from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.deps import get_current_user, get_provider_settings, get_session
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.domain.grocery import GroceryRequest, MealRequest
from app.domain.plan_proposal import (
    ApplyConstraints,
    ProposalInvalid,
    apply_operations,
    load_base_snapshot,
    parse_operations,
)
from app.domain.plan_revision import PlanSnapshot
from app.models import User
from app.plan_models import PlanProposal, PlanRevision
from app.services import security_admission
from app.services.grocery_planner import (
    DietConflict,
    ExclusionConflict,
    plan_groceries,
)

router = APIRouter(prefix="/grocery", tags=["grocery"])

PROPOSAL_NOT_FOUND_MESSAGE = "The plan proposal was not found."
PROPOSAL_DISCARDED_MESSAGE = "The plan proposal was discarded."
PROPOSAL_APPLIED_MESSAGE = "The plan proposal was already applied."
PROPOSAL_STALE_MESSAGE = "The plan proposal can no longer be applied."


class ApplyProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_cap_cents: Annotated[StrictInt, Field(ge=0)]


class DiscardProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Discard confirmation is required.")
        return value


class AppliedProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_revision_id: str
    snapshot: PlanSnapshot


class ProposalConstraintsError(HTTPException):
    """An Apply rejection with a fixed, structured detail."""


def _constraint_error(
    reason: Literal[
        "over_budget", "diet_conflict", "exclusion_conflict", "estimate_unavailable"
    ],
    *,
    total_cents: int | None = None,
    available_cents: int | None = None,
) -> ProposalConstraintsError:
    detail: dict[str, object] = {"code": "proposal_constraints", "reason": reason}
    if reason == "over_budget":
        detail.update(total_cents=total_cents, available_cents=available_cents)
    return ProposalConstraintsError(status_code=409, detail=detail)


def _validate_apply(
    session: Session,
    proposal: PlanProposal,
    preview: PlanSnapshot,
    browser_cap_cents: int,
) -> int:
    try:
        constraints = ApplyConstraints.model_validate(proposal.apply_constraints)
    except ValidationError:
        raise _constraint_error("estimate_unavailable") from None
    caps = [
        cap
        for cap in (
            browser_cap_cents,
            constraints.plan_cap_cents,
            preview.plan_cap_cents,
        )
        if cap is not None
    ]
    cap = min(caps)
    now = grocery_api._ny_now()
    settings = get_provider_settings()
    spending = grocery_api.require_spending(
        session, settings.spending_source, now, proposal.user_id
    )
    try:
        budget = calculate_budget(
            constraints.monthly_limit_cents,
            SpendingSnapshot(
                spending.period,
                spending.posted_cents,
                spending.pending_cents,
                spending.refreshed_at,
            ),
            now=now,
            plan_cap_cents=cap,
        )
        estimate = plan_groceries(
            GroceryRequest(
                meals=[
                    MealRequest(recipe_id=meal.recipe_id, servings=meal.servings)
                    for meal in preview.meals
                ],
                pantry_ingredients=preview.pantry_ingredient_ids,
                budget_period=spending.period,
                plan_cap_cents=cap,
                diet=constraints.diet,
                ingredient_exclusions=constraints.ingredient_exclusions,
            ),
            budget,
        )
    except DietConflict:
        raise _constraint_error("diet_conflict") from None
    except ExclusionConflict:
        raise _constraint_error("exclusion_conflict") from None
    except (ValueError, TypeError):
        raise _constraint_error("estimate_unavailable") from None
    if estimate.total_cents is None:
        raise _constraint_error("estimate_unavailable")
    if estimate.total_cents > budget.available_cents:
        raise _constraint_error(
            "over_budget",
            total_cents=estimate.total_cents,
            available_cents=budget.available_cents,
        )
    if not estimate.accepted:
        raise _constraint_error("estimate_unavailable")
    return cap


def _load(
    session: Session, proposal_id: UUID, user_id: int, *, lock: bool = False
) -> PlanProposal:
    statement = select(PlanProposal).where(
        PlanProposal.id == proposal_id, PlanProposal.user_id == user_id
    )
    if lock:
        statement = statement.with_for_update()
        statement = statement.execution_options(populate_existing=True)
    proposal = session.scalars(statement).one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail=PROPOSAL_NOT_FOUND_MESSAGE)
    return proposal


def _preview(
    session: Session, proposal: PlanProposal, *, discard_stale: bool = False
) -> PlanSnapshot:
    base = session.get(PlanRevision, proposal.base_plan_revision_id)
    if base is None or base.user_id != proposal.user_id:
        raise HTTPException(status_code=409, detail=PROPOSAL_STALE_MESSAGE)
    try:
        return apply_operations(
            load_base_snapshot(base), parse_operations(proposal.operations)
        )
    except ProposalInvalid:
        if discard_stale and proposal.status == "pending":
            proposal.status = "discarded"
            proposal.updated_at = datetime.now(UTC)
            session.commit()
        raise HTTPException(status_code=409, detail=PROPOSAL_STALE_MESSAGE) from None


def _committed(session: Session, proposal: PlanProposal) -> AppliedProposalResponse:
    revision = session.get(PlanRevision, proposal.applied_plan_revision_id)
    if revision is None or revision.user_id != proposal.user_id:
        raise HTTPException(status_code=409, detail=PROPOSAL_STALE_MESSAGE)
    try:
        snapshot = PlanSnapshot.model_validate(revision.snapshot)
    except ValidationError:
        raise HTTPException(status_code=409, detail=PROPOSAL_STALE_MESSAGE) from None
    return AppliedProposalResponse(plan_revision_id=str(revision.id), snapshot=snapshot)


@router.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    proposal = _load(session, proposal_id, user.id)
    was_discarded = proposal.status == "discarded"
    preview: dict[str, object] | None
    try:
        preview = (
            _committed(session, proposal).snapshot
            if proposal.applied_plan_revision_id is not None
            else _preview(session, proposal)
        ).model_dump(mode="json")
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


@router.post("/proposals/{proposal_id}/apply", response_model=AppliedProposalResponse)
def apply_proposal(
    proposal_id: UUID,
    request: ApplyProposalRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> AppliedProposalResponse | JSONResponse:
    proposal = _load(session, proposal_id, user.id)
    if proposal.status == "discarded":
        raise HTTPException(status_code=409, detail=PROPOSAL_DISCARDED_MESSAGE)
    if proposal.applied_plan_revision_id is not None:
        return _committed(session, proposal)
    security_admission.reserve_action(session, user.id, "mutation")
    proposal = _load(session, proposal_id, user.id, lock=True)
    if proposal.status == "discarded":
        raise HTTPException(status_code=409, detail=PROPOSAL_DISCARDED_MESSAGE)
    if proposal.applied_plan_revision_id is not None:
        return _committed(session, proposal)
    preview = _preview(session, proposal, discard_stale=True)
    try:
        cap = _validate_apply(
            session,
            proposal,
            preview,
            browser_cap_cents=request.plan_cap_cents,
        )
    except ProposalConstraintsError as exc:
        return JSONResponse(status_code=409, content={"detail": exc.detail})
    revision_id = uuid4()
    preview = preview.model_copy(update={"plan_cap_cents": cap})
    snapshot = cast(dict[str, object], preview.model_dump(mode="json"))
    session.add(PlanRevision(id=revision_id, user_id=user.id, snapshot=snapshot))
    session.flush()
    proposal.status = "applied"
    proposal.applied_plan_revision_id = revision_id
    proposal.updated_at = datetime.now(UTC)
    session.commit()
    return _committed(session, proposal)


@router.post("/proposals/{proposal_id}/discard")
def discard_proposal(
    proposal_id: UUID,
    request: DiscardProposalRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    proposal = _load(session, proposal_id, user.id)
    if proposal.status == "applied":
        raise HTTPException(status_code=409, detail=PROPOSAL_APPLIED_MESSAGE)
    if proposal.status == "discarded":
        return {"status": "discarded"}
    security_admission.reserve_action(session, user.id, "mutation")
    proposal = _load(session, proposal_id, user.id, lock=True)
    if proposal.status == "applied":
        raise HTTPException(status_code=409, detail=PROPOSAL_APPLIED_MESSAGE)
    if proposal.status == "pending":
        proposal.status = "discarded"
        proposal.updated_at = datetime.now(UTC)
        session.commit()
    return {"status": "discarded"}
