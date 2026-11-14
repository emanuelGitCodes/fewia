from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN
from app.agent.chat_loop import run_chat
from app.agent.provider import LLMProvider
from app.domain.budget import SpendingSnapshot, SpendingSource, calculate_budget
from app.domain.grocery import Diet, GroceryRequest
from app.domain.plan_proposal import (
    ApplyConstraints,
    ProposalDietaryConstraints,
    create_proposal,
)
from app.domain.plan_revision import PlanRevisionInput, PlanSnapshot
from app.plan_models import PlanRevision
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import save_job_plan_evidence
from app.services.job_delivery import JobContext, LeaseLost
from app.services.job_effects import apply_effect
from app.services.model_cost import ModelCostError
from app.services.plan_job import SpendingInput


class ChatHistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: StrictStr = Field(min_length=1, max_length=MAX_MESSAGE_LEN)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text is invalid")
        return value


class ChatJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["chat"] = "chat"
    message: StrictStr = Field(min_length=1, max_length=MAX_MESSAGE_LEN)
    monthly_limit_cents: StrictInt = Field(ge=0)
    spending: SpendingInput
    spending_source: SpendingSource
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)
    previous_request: dict[str, object] | None = None
    previous_ingredient_ids: list[StrictStr] | None = None
    previous_search: dict[str, object] | None = None
    previous_exhausted_search: dict[str, object] | None = None
    previous_what_if_recipe: StrictStr | None = None
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY)
    previous_job_id: UUID | None = Field(default=None)
    plan_revision_id: UUID | None = None
    plan_revision: PlanRevisionInput | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message is invalid")
        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _owned_context(
    factory: sessionmaker[Session], parsed: ChatJobInput, user_id: int
) -> PlanRevisionInput | None:
    from app.services.chat_history import load_previous_state

    with factory() as session:
        if parsed.previous_job_id is not None:
            state = load_previous_state(session, user_id, parsed.previous_job_id)
            history, request, ingredients = state.context
            parsed.history = [ChatHistoryTurn.model_validate(turn) for turn in history]
            parsed.previous_request = request
            parsed.previous_ingredient_ids = ingredients
            parsed.previous_search = state.search
            parsed.previous_exhausted_search = state.exhausted_search
            parsed.previous_what_if_recipe = state.what_if_recipe
        embedded = parsed.plan_revision
        revision_id = parsed.plan_revision_id
        if embedded is not None:
            if revision_id is not None and revision_id != embedded.id:
                raise ValueError("Chat plan context is unavailable.")
            revision_id = embedded.id
        if revision_id is None:
            return None
        stored = session.scalar(
            select(PlanRevision).where(
                PlanRevision.id == revision_id, PlanRevision.user_id == user_id
            )
        )
        if stored is None:
            raise ValueError("Chat plan context is unavailable.")
        snapshot = PlanSnapshot.model_validate(stored.snapshot)
        if embedded is not None and embedded.snapshot != snapshot:
            raise ValueError("Chat plan context is unavailable.")
        return PlanRevisionInput(id=stored.id, snapshot=snapshot)


def chat_job(
    payload: dict[str, object],
    context: JobContext,
    *,
    provider: LLMProvider,
    factory: sessionmaker[Session],
) -> dict[str, object]:
    context.heartbeat()
    parsed = ChatJobInput.model_validate(payload)
    plan = (
        _owned_context(factory, parsed, context.user_id)
        if parsed.previous_job_id is not None
        or parsed.plan_revision_id is not None
        or parsed.plan_revision is not None
        else None
    )
    previous = (
        None
        if parsed.previous_request is None
        else GroceryRequest.model_validate(parsed.previous_request)
    )
    clock = _utc_now()
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        SpendingSnapshot(
            parsed.spending.period,
            parsed.spending.posted_cents,
            parsed.spending.pending_cents,
            parsed.spending.refreshed_at,
        ),
        now=clock,
        plan_cap_cents=parsed.plan_cap_cents,
    )
    inputs = EvidenceInputs(
        monthly_limit_cents=parsed.monthly_limit_cents,
        spending=parsed.spending,
        spending_source=parsed.spending_source,
        calculated_at=clock,
        plan_cap_cents=parsed.plan_cap_cents,
    )
    history: list[dict[str, str]] = []
    for item in parsed.history:
        turn: dict[str, str] = {"role": str(item.role), "text": item.text}
        history.append(turn)

    evidence_ordinal = 0
    proposal_ordinal = 0

    def record_evidence(planning: dict[str, object]) -> str:
        nonlocal evidence_ordinal
        key = f"evidence:{evidence_ordinal}"
        evidence_ordinal += 1
        return save_job_plan_evidence(factory, context, key, planning, inputs)

    def propose(
        operations: list[dict[str, object]], dietary: ProposalDietaryConstraints
    ) -> str:
        nonlocal proposal_ordinal
        assert plan is not None
        diets: tuple[Diet, ...] = ("omnivore", "vegetarian", "vegan")
        prior_diet: Diet = "omnivore" if previous is None else previous.diet
        requested_diet: Diet = dietary.diet or "omnivore"
        diet = max((prior_diet, requested_diet), key=diets.index)
        prior_exclusions = [] if previous is None else previous.ingredient_exclusions
        constraints = ApplyConstraints(
            monthly_limit_cents=parsed.monthly_limit_cents,
            plan_cap_cents=parsed.plan_cap_cents,
            diet=diet,
            ingredient_exclusions=list(
                dict.fromkeys([*prior_exclusions, *dietary.ingredient_exclusions])
            ),
        )
        base_id = plan.id

        def write(session: Session) -> dict[str, object]:
            proposal_id = create_proposal(
                session, context.user_id, base_id, operations, constraints=constraints
            )
            return {"kind": "proposal", "id": str(proposal_id)}

        key = f"proposal:{proposal_ordinal}"
        proposal_ordinal += 1
        result = apply_effect(
            factory,
            context,
            key,
            {
                "plan": plan.model_dump(mode="json"),
                "operations": operations,
                "constraints": constraints.model_dump(mode="json"),
                "budget": {
                    "available_cents": budget.available_cents,
                    "pending_cents": budget.pending_cents,
                    "stale": budget.stale,
                    "warnings": list(budget.warnings),
                },
                "budget_inputs": inputs.model_dump(
                    mode="json", exclude={"calculated_at"}
                ),
            },
            write,
        )
        return str(result["id"])

    return run_chat(
        provider,
        parsed.message,
        budget,
        parsed.spending.period,
        heartbeat=context.heartbeat,
        user_id=context.user_id,
        spending_source=parsed.spending_source,
        previous_request=parsed.previous_request,
        previous_ingredient_ids=parsed.previous_ingredient_ids,
        previous_search=parsed.previous_search,
        previous_exhausted_search=parsed.previous_exhausted_search,
        previous_what_if_recipe=parsed.previous_what_if_recipe,
        history=history,
        record_evidence=record_evidence,
        plan_cap_cents=parsed.plan_cap_cents,
        plan_revision=plan,
        model_prose=False,
        sanitize_trace=True,
        provider_control_errors=(ModelCostError, LeaseLost),
        propose=None if plan is None else propose,
    )
