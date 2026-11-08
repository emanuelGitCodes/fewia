"""HTTP routes that show, apply, or discard a plan proposal."""

from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.demo import DEMO_USER_ID
from app.deps import get_provider_settings, get_session
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
    browser_cap_cents: int | None = None,
) -> None:
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
    cap = min(caps) if caps else None
    now = grocery_api._ny_now()
    settings = get_provider_settings()
    spending = grocery_api.require_spending(session, settings.spending_source, now)
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


@router.post("/proposals/{proposal_id}/apply", response_model=dict[str, str])
def apply_proposal(
    proposal_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    request: ApplyProposalRequest | None = None,
) -> dict[str, str] | JSONResponse:
    proposal = _load(session, proposal_id, lock=True)
    if proposal.status == "discarded":
        raise HTTPException(status_code=409, detail=PROPOSAL_DISCARDED_MESSAGE)
    if proposal.applied_plan_revision_id is not None:
        return {"plan_revision_id": str(proposal.applied_plan_revision_id)}
    preview = _preview(session, proposal)
    try:
        _validate_apply(
            session,
            proposal,
            preview,
            browser_cap_cents=None if request is None else request.plan_cap_cents,
        )
    except ProposalConstraintsError as exc:
        return JSONResponse(status_code=409, content={"detail": exc.detail})
    revision_id = uuid4()
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
