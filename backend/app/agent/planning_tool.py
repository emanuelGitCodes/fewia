import hashlib
import json
from calendar import monthrange
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from typing import Literal, cast

from pydantic import ValidationError

from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest
from app.services.grocery_planner import (
    PlanEstimate,
    PlanningError,
    plan_groceries,
    safe_conflict,
)
from app.services.meal_nutrition import meal_nutrition
from app.services.supermarket_overlay import (
    IngredientCostEstimator,
    estimate_supermarket_cost,
)
from app.tools.base import build_evidence_id

TOOL_NAME = "plan_groceries"
_VALID_SOURCES: frozenset[str] = frozenset({"fixture", "plaid_sandbox"})


class PlanningToolError(ValueError):
    """A planning-tool failure with a static message and no raw input."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        ingredient_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.ingredient_id = ingredient_id


def tool_error_body(error: PlanningToolError) -> dict[str, object]:
    conflict = safe_conflict(
        getattr(error, "code", None),
        getattr(error, "ingredient_id", None),
    )
    if conflict is None:
        return {"error": "arguments are invalid"}
    body: dict[str, object] = {
        "error": conflict["error"],
        "ingredient_id": conflict["ingredient_id"],
    }
    return body


def _object_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("schema is invalid")
    return cast(dict[str, object], value)


def _apply_catalog_enums(schema: dict[str, object]) -> None:
    defs = _object_map(schema.get("$defs"))
    meal = _object_map(defs.get("MealRequest"))
    recipe = _object_map(_object_map(meal.get("properties")).get("recipe_id"))
    recipe["enum"] = list(SUPPORTED_RECIPE_IDS)
    properties = _object_map(schema.get("properties"))
    catalog_ids = list(INGREDIENTS)
    for field in ("pantry_ingredients", "ingredient_exclusions"):
        items = _object_map(_object_map(properties.get(field)).get("items"))
        items["enum"] = list(catalog_ids)


def planner_tool_spec() -> dict[str, object]:
    """Return the Bedrock toolSpec for plan_groceries."""
    schema = _object_map(deepcopy(GroceryRequest.model_json_schema()))
    _apply_catalog_enums(schema)
    return {
        "toolSpec": {
            "name": TOOL_NAME,
            "description": (
                "Plan supported meals against the server budget. "
                "The tool does not purchase items."
            ),
            "inputSchema": {
                "json": schema,
            },
        }
    }


def execute_plan(
    arguments: object,
    budget: BudgetResult,
    period: date,
    *,
    user_id: int = 1,
    spending_source: Literal["fixture", "plaid_sandbox"] = "fixture",
    supermarket_estimator: IngredientCostEstimator | None = None,
) -> dict[str, object]:
    """Return a deterministic grocery plan from validated tool arguments."""
    if type(user_id) is not int or user_id < 1:
        raise PlanningToolError("user_id is invalid")
    if spending_source not in _VALID_SOURCES:
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
    conflict: dict[str, str] | None = None
    try:
        plan = plan_groceries(request, planning_budget)
    except PlanningError as error:
        plan = None
        conflict = safe_conflict(
            getattr(error, "code", None),
            getattr(error, "ingredient_id", None),
        )
    if plan is None:
        if conflict is None:
            raise PlanningToolError("catalog constraint is invalid")
        raise PlanningToolError(
            "catalog constraint is invalid",
            code=conflict["error"],
            ingredient_id=conflict["ingredient_id"],
        )
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
