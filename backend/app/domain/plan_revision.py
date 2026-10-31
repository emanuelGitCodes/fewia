"""Validated plan snapshot shared by the plan panel and chat jobs."""

from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)

from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SUPPORTED_RECIPE_IDS


class PlanMeal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: StrictStr
    servings: StrictInt = Field(ge=1, le=8)

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, value: str) -> str:
        if value not in SUPPORTED_RECIPE_IDS:
            raise ValueError("recipe_id is not supported")
        return value


class PlanSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meals: list[PlanMeal] = Field(max_length=3)
    pantry_ingredient_ids: list[StrictStr] = Field(max_length=len(INGREDIENTS))
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)

    @field_validator("meals")
    @classmethod
    def validate_meals(cls, value: list[PlanMeal]) -> list[PlanMeal]:
        ids = [meal.recipe_id for meal in value]
        if len(set(ids)) != len(ids):
            raise ValueError("meals must not repeat a recipe_id")
        return value

    @field_validator("pantry_ingredient_ids")
    @classmethod
    def validate_pantry(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("pantry_ingredient_ids must be unique")
        for ingredient_id in value:
            if ingredient_id not in INGREDIENTS:
                raise ValueError("pantry_ingredient_ids has an unknown id")
        return value


class PlanRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    snapshot: PlanSnapshot
