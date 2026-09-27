"""HTTP models for fixture grocery planning jobs."""

import json
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.domain.budget import SpendingSource
from app.domain.grocery import GroceryRequest


class CatalogRef(BaseModel):
    id: str
    name: str


class GroceryConfig(BaseModel):
    budget_period: date
    source: SpendingSource
    posted_cents: int
    pending_cents: int
    notice: str
    recipes: list[CatalogRef]
    ingredients: list[CatalogRef]
    catalog_version: str = ""
    spending_refreshed_at: datetime | None = None


class CreateGroceryJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: GroceryRequest
    monthly_limit_cents: StrictInt = Field(ge=0)

    def caller_fields(self) -> dict[str, object]:
        return {
            "monthly_limit_cents": self.monthly_limit_cents,
            "request": self.request.model_dump(mode="json"),
        }

    def matches_stored_caller_fields(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        if not isinstance(payload.get("request"), dict):
            return False
        stored: dict[str, object] = {
            "monthly_limit_cents": payload.get("monthly_limit_cents"),
            "request": payload["request"],
        }
        try:
            return json.dumps(stored, sort_keys=True, allow_nan=False) == json.dumps(
                self.caller_fields(), sort_keys=True, allow_nan=False
            )
        except (TypeError, ValueError):
            return False


class GroceryJobAccepted(BaseModel):
    job_id: str
    status: str


class GroceryJobView(BaseModel):
    id: str
    status: str
    result: dict[str, object] | None
    error_code: str | None
