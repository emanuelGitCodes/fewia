import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.grocery import GroceryRequest


class PlanLine(BaseModel):
    model_config = ConfigDict(strict=True)

    ingredient_id: str
    name: str
    unit: str
    quantity: int = Field(gt=0)
    packages: int = Field(ge=0)
    cost_cents: int | None = Field(ge=0)
    from_pantry: bool


class ObservedPlan(BaseModel):
    model_config = ConfigDict(strict=True)

    lines: list[PlanLine]
    total_cents: int | None = Field(ge=0)
    accepted: bool
    catalog_version: str
    notice: str


class ObservedBudget(BaseModel):
    model_config = ConfigDict(strict=True)

    available_cents: int = Field(ge=0)
    pending_cents: int
    stale: bool


class PlanObservation(BaseModel):
    model_config = ConfigDict(strict=True)

    request: GroceryRequest
    plan: ObservedPlan
    budget: ObservedBudget


def parse_plan_observation(result: dict[str, object]) -> PlanObservation | None:
    raw_request = result.get("request")
    if type(raw_request) is not dict:
        return None
    if not GroceryRequest.model_fields.keys() <= raw_request.keys():
        return None
    period = raw_request.get("budget_period")
    if (
        type(period) is not str
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", period) is None
    ):
        return None
    try:
        request = GroceryRequest.model_validate(raw_request)
        if request.model_dump(mode="json")["budget_period"] != period:
            return None
        return PlanObservation.model_validate({**result, "request": request})
    except ValidationError:
        return None
