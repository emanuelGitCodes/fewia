from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from app.agent.planning_tool import execute_plan
from app.domain.budget import SpendingSnapshot, calculate_budget
from app.domain.grocery import GroceryRequest


class SpendingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: date
    posted_cents: StrictInt
    pending_cents: StrictInt
    refreshed_at: AwareDatetime


class PlanJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: GroceryRequest
    monthly_limit_cents: StrictInt = Field(ge=0)
    spending: SpendingInput
    spending_source: Literal["fixture", "plaid_sandbox"]


PlanEvidenceRecorder = Callable[[dict[str, object], PlanJobInput, datetime], str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_revision_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all("0" <= char <= "9" or "a" <= char <= "f" for char in value)
    )


def plan_job(
    payload: dict[str, object],
    heartbeat: Callable[[], None],
    *,
    record_evidence: PlanEvidenceRecorder | None = None,
) -> dict[str, object]:
    heartbeat()
    parsed = PlanJobInput.model_validate(payload)
    if parsed.request.budget_period != parsed.spending.period:
        raise ValueError("request.budget_period must match spending.period")
    clock = _utc_now()
    spending = SpendingSnapshot(
        period=parsed.spending.period,
        posted_cents=parsed.spending.posted_cents,
        pending_cents=parsed.spending.pending_cents,
        refreshed_at=parsed.spending.refreshed_at,
    )
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        spending,
        now=clock,
        plan_cap_cents=parsed.request.plan_cap_cents,
    )
    result = execute_plan(
        parsed.request.model_dump(mode="json"),
        budget,
        parsed.spending.period,
        user_id=1,
        spending_source=parsed.spending_source,
    )
    if record_evidence is not None:
        revision = record_evidence(result, parsed, clock)
        if not _is_revision_id(revision):
            raise ValueError("evidence revision id is invalid")
        result["evidence_revision_id"] = revision
    heartbeat()
    return result
