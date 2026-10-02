"""HTTP route for deterministic meal template suggestions."""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
)
from sqlalchemy.orm import Session

from app.api import grocery as grocery_api
from app.demo import DEMO_USER_ID
from app.deps import get_provider_settings, get_session
from app.domain.budget import (
    NEW_YORK,
    STALE_SPENDING_ERROR,
    BudgetResult,
    SpendingSnapshot,
    SpendingSource,
    StaleSpendingError,
    calculate_budget,
)
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, Diet
from app.models import User
from app.provider_settings import GroceryProviderSettings
from app.services.plan_templates import MealTemplateSuggestion, suggest_templates

router = APIRouter(prefix="/grocery", tags=["grocery"])
_CONTROL_LIMIT = 22


def _ny_now() -> datetime:
    return datetime.now(UTC).astimezone(NEW_YORK)


def _validate_control_ids(value: list[str], field_name: str) -> list[str]:
    for ingredient_id in value:
        if ingredient_id not in INGREDIENTS:
            raise ValueError(f"{field_name} contains an unknown ingredient id")
    return value


class SuggestTemplatesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_period: date
    monthly_limit_cents: StrictInt = Field(ge=0)
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)
    servings: StrictInt = Field(default=2, ge=1, le=8)
    diet: Diet = "omnivore"
    pantry_ingredients: list[StrictStr] = Field(
        default_factory=list, max_length=_CONTROL_LIMIT
    )
    ingredient_exclusions: list[StrictStr] = Field(
        default_factory=list, max_length=_CONTROL_LIMIT
    )

    @field_validator("budget_period")
    @classmethod
    def validate_budget_period(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("budget_period must be the first day of its month")
        return value

    @field_validator("pantry_ingredients", "ingredient_exclusions")
    @classmethod
    def validate_controls(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return _validate_control_ids(value, str(info.field_name))


class TemplateSuggestionsResponse(BaseModel):
    budget_period: date
    spending_source: SpendingSource
    budget: BudgetResult
    catalog_version: str
    notice: str
    suggestions: tuple[MealTemplateSuggestion, ...]


@router.post("/templates")
def suggest_plan_templates(
    body: SuggestTemplatesBody,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[GroceryProviderSettings, Depends(get_provider_settings)],
) -> TemplateSuggestionsResponse:
    if session.get(User, DEMO_USER_ID) is None:
        raise HTTPException(status_code=503, detail=grocery_api.DEMO_NOT_READY_MESSAGE)
    now = _ny_now()
    spending = grocery_api.require_spending(session, settings.spending_source, now)
    if body.budget_period != spending.period:
        raise HTTPException(status_code=422, detail=grocery_api.PERIOD_MISMATCH_MESSAGE)
    snapshot = SpendingSnapshot(
        spending.period,
        spending.posted_cents,
        spending.pending_cents,
        spending.refreshed_at,
    )
    budget: BudgetResult | None = None
    try:
        budget = calculate_budget(
            body.monthly_limit_cents,
            snapshot,
            now=now,
            plan_cap_cents=body.plan_cap_cents,
        )
    except StaleSpendingError:
        budget = None
    if budget is None:
        raise HTTPException(status_code=422, detail=STALE_SPENDING_ERROR)
    suggestions = suggest_templates(
        spending.period,
        budget,
        servings=body.servings,
        diet=body.diet,
        pantry_ingredients=tuple(body.pantry_ingredients),
        ingredient_exclusions=tuple(body.ingredient_exclusions),
    )
    return TemplateSuggestionsResponse(
        budget_period=spending.period,
        spending_source=settings.spending_source,
        budget=budget,
        catalog_version=CATALOG_VERSION,
        notice=SAMPLE_ESTIMATE_NOTICE,
        suggestions=suggestions,
    )
