from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN
from app.agent.chat_loop import run_chat
from app.agent.provider import LLMProvider
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import save_plan_evidence
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
    spending_source: Literal["fixture", "plaid_sandbox"]
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)
    previous_request: dict[str, object] | None = None
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY)
    previous_job_id: UUID | None = Field(default=None)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message is invalid")
        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def chat_job(
    payload: dict[str, object],
    heartbeat: Callable[[], None],
    *,
    provider: LLMProvider,
    factory: sessionmaker[Session],
) -> dict[str, object]:
    heartbeat()
    parsed = ChatJobInput.model_validate(payload)
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

    def record_evidence(planning: dict[str, object]) -> str:
        return save_plan_evidence(factory, 1, planning, inputs)

    return run_chat(
        provider,
        parsed.message,
        budget,
        parsed.spending.period,
        heartbeat=heartbeat,
        user_id=1,
        spending_source=parsed.spending_source,
        previous_request=parsed.previous_request,
        history=history,
        record_evidence=record_evidence,
        plan_cap_cents=parsed.plan_cap_cents,
    )
