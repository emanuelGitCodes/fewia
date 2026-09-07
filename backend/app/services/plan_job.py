import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from app.domain.budget import BudgetResult, SpendingSnapshot, calculate_budget
from app.domain.grocery import GroceryRequest
from app.services.grocery_planner import PlanEstimate, plan_groceries


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


def _json_object(value: BudgetResult | PlanEstimate) -> dict[str, object]:
    return cast(
        dict[str, object], json.loads(json.dumps(asdict(value), allow_nan=False))
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def plan_job(
    payload: dict[str, object], heartbeat: Callable[[], None]
) -> dict[str, object]:
    heartbeat()
    parsed = PlanJobInput.model_validate(payload)
    if parsed.request.budget_period != parsed.spending.period:
        raise ValueError("request.budget_period must match spending.period")
    spending = SpendingSnapshot(
        period=parsed.spending.period,
        posted_cents=parsed.spending.posted_cents,
        pending_cents=parsed.spending.pending_cents,
        refreshed_at=parsed.spending.refreshed_at,
    )
    budget = calculate_budget(
        parsed.monthly_limit_cents,
        spending,
        now=_utc_now(),
        plan_cap_cents=parsed.request.plan_cap_cents,
    )
    plan = plan_groceries(parsed.request, budget)
    heartbeat()
    return {
        "plan": _json_object(plan),
        "budget": _json_object(budget),
        "spending_source": parsed.spending_source,
    }
