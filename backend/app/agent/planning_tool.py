import hashlib
import json
from calendar import monthrange
from dataclasses import asdict
from datetime import date
from typing import cast, get_args

from pydantic import ValidationError

from app.domain.budget import BudgetResult, SpendingSource
from app.domain.grocery import GroceryRequest
from app.services.grocery_planner import PlanEstimate, PlanningError, plan_groceries
from app.services.meal_nutrition import meal_nutrition
from app.services.supermarket_overlay import (
    IngredientCostEstimator,
    estimate_supermarket_cost,
)
from app.tools.base import build_evidence_id

TOOL_NAME = "plan_groceries"


class PlanningToolError(ValueError):
    """A planning-tool failure with a static message and no raw input."""


def planner_tool_spec() -> dict[str, object]:
    """Return the Bedrock toolSpec for plan_groceries."""
    return {
        "toolSpec": {
            "name": TOOL_NAME,
            "description": (
                "Plan supported meals against the server budget. "
                "The tool does not purchase items."
            ),
            "inputSchema": {
                "json": cast(dict[str, object], GroceryRequest.model_json_schema()),
            },
        }
    }


def execute_plan(
    arguments: object,
    budget: BudgetResult,
    period: date,
    *,
    user_id: int = 1,
    spending_source: SpendingSource = "fixture",
    supermarket_estimator: IngredientCostEstimator | None = None,
) -> dict[str, object]:
    """Return a deterministic grocery plan from validated tool arguments."""
    if type(user_id) is not int or user_id < 1:
        raise PlanningToolError("user_id is invalid")
    if spending_source not in get_args(SpendingSource):
        raise PlanningToolError("spending_source is invalid")
    if type(period) is not date or period.day != 1:
        raise PlanningToolError("period is invalid")
    if not isinstance(budget, BudgetResult):
        raise PlanningToolError("budget is invalid")
    if type(budget.available_cents) is not int or budget.available_cents < 0:
        raise PlanningToolError("budget is invalid")
    request: GroceryRequest | None
    try:
        request = GroceryRequest.model_validate(arguments)
    except ValidationError:
        request = None
    if request is None:
        raise PlanningToolError("arguments are invalid")
    if request.budget_period != period:
        raise PlanningToolError("budget_period does not match the server period")
    available_cents = budget.available_cents
    if request.plan_cap_cents is not None:
        available_cents = min(available_cents, request.plan_cap_cents)
    planning_budget = BudgetResult(
        available_cents,
        budget.pending_cents,
        budget.stale,
        budget.warnings,
    )
    plan: PlanEstimate | None
    try:
        plan = plan_groceries(request, planning_budget)
    except PlanningError:
        plan = None
    if plan is None:
        raise PlanningToolError("catalog constraint is invalid")
    request_payload: object = request.model_dump(mode="json")
    plan_payload: object = json.loads(json.dumps(asdict(plan), allow_nan=False))
    nutrition_payload: object = json.loads(
        json.dumps(asdict(meal_nutrition(request)), allow_nan=False)
    )
    budget_payload: dict[str, object] = {
        "available_cents": planning_budget.available_cents,
        "pending_cents": planning_budget.pending_cents,
        "stale": planning_budget.stale,
        "warnings": list(planning_budget.warnings),
    }
    result: dict[str, object] = {
        "request": request_payload,
        "plan": plan_payload,
        "budget": budget_payload,
        "meal_nutrition": nutrition_payload,
        "spending_source": spending_source,
        "evidence_id": _evidence_id(
            request_payload,
            budget_payload,
            plan_payload,
            nutrition_payload,
            spending_source,
            user_id,
            period,
        ),
    }
    if supermarket_estimator is not None:
        overlay = estimate_supermarket_cost(plan, supermarket_estimator)
        result["supermarket_estimate"] = {
            "total_cents": overlay.total_cents,
            "notice": overlay.notice,
        }
    return result


def _evidence_id(
    request_payload: object,
    budget_payload: object,
    plan_payload: object,
    nutrition_payload: object,
    source: str,
    user_id: int,
    period: date,
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "budget": budget_payload,
                "meal_nutrition": nutrition_payload,
                "plan": plan_payload,
                "request": request_payload,
                "source": source,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:24]
    last_day = monthrange(period.year, period.month)[1]
    return build_evidence_id(
        f"grocery-{digest}",
        user_id,
        period,
        date(period.year, period.month, last_day),
    )
