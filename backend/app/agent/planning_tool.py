import hashlib
import json
from calendar import monthrange
from dataclasses import asdict
from datetime import date
from typing import cast, get_args

from pydantic import ValidationError

from app.domain.budget import BudgetResult, SpendingSource
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest
from app.services.grocery_planner import (
    ExclusionConflict,
    PlanEstimate,
    PlanningError,
    plan_groceries,
)
from app.services.meal_nutrition import meal_nutrition
from app.tools.base import build_evidence_id

TOOL_NAME = "plan_groceries"


class PlanningToolError(ValueError):
    """A planning-tool failure with a static message and no raw input."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        detail: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.detail = {} if detail is None else detail


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


def _unsupported_recipe_only(exc: ValidationError) -> bool:
    errors = exc.errors()
    if not errors:
        return False
    for error in errors:
        loc = error["loc"]
        if not loc or loc[-1] != "recipe_id":
            return False
        value = error.get("input")
        if type(value) is not str or value in SUPPORTED_RECIPE_IDS:
            return False
    return True


def execute_plan(
    arguments: object,
    budget: BudgetResult,
    period: date,
    *,
    user_id: int = 1,
    spending_source: SpendingSource = "fixture",
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
    unsupported_recipe = False
    try:
        request = GroceryRequest.model_validate(arguments)
    except ValidationError as exc:
        request = None
        unsupported_recipe = _unsupported_recipe_only(exc)
    if request is None:
        if unsupported_recipe:
            raise PlanningToolError(
                "recipe is not supported",
                error_code="unsupported_recipe",
            )
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
    exclusion_detail: dict[str, str] | None = None
    try:
        plan = plan_groceries(request, planning_budget)
    except ExclusionConflict as exc:
        plan = None
        exclusion_detail = {
            "recipe_id": exc.recipe_id,
            "ingredient_id": exc.ingredient_id,
        }
    except PlanningError:
        plan = None
    if exclusion_detail is not None:
        raise PlanningToolError(
            "ingredient is excluded",
            error_code="exclusion_reject",
            detail=exclusion_detail,
        )
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
