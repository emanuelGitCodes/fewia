"""HTTP request and plan snapshot types for Instacart list handoff."""

from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr


class CreateHandoffBody(BaseModel, extra="forbid"):
    job_id: UUID


class RetryHandoffBody(BaseModel, extra="forbid"):
    expected_attempt: StrictInt = Field(ge=1)


class PlanLine(BaseModel, extra="forbid"):
    ingredient_id: StrictStr
    name: StrictStr
    unit: StrictStr
    quantity: StrictInt
    packages: StrictInt
    cost_cents: StrictInt | None
    from_pantry: StrictBool


class SnapshotPlan(BaseModel, extra="forbid"):
    lines: list[PlanLine]
    total_cents: StrictInt | None
    accepted: StrictBool
    warnings: list[StrictStr]
    catalog_version: StrictStr
    notice: StrictStr
