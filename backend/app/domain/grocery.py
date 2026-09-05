from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

SUPPORTED_RECIPE_IDS: tuple[str, ...] = (
    "chicken_tacos",
    "bean_tacos",
    "vegetable_pasta",
    "chicken_and_rice_bowls",
    "lentil_soup",
    "chickpea_curry",
    "vegetable_stir_fry",
    "baked_potatoes_with_beans",
    "breakfast_burritos",
    "overnight_oats",
)
Diet = Literal["omnivore", "vegetarian", "vegan"]
SAMPLE_ESTIMATE_NOTICE = (
    "Estimated from the demo price catalog. Instacart prices, availability, "
    "taxes, delivery fees, and tips are not verified."
)


class MealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: StrictStr
    servings: StrictInt = Field(ge=1, le=8)

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, value: str) -> str:
        if value not in SUPPORTED_RECIPE_IDS:
            raise ValueError("recipe_id is not supported")
        return value


class GroceryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meals: list[MealRequest] = Field(min_length=1, max_length=3)
    budget_period: date
    plan_cap_cents: StrictInt | None = Field(default=None, ge=0)
    pantry_ingredients: list[StrictStr] = Field(default_factory=list)
    ingredient_exclusions: list[StrictStr] = Field(default_factory=list)
    diet: Diet = "omnivore"

    @field_validator("budget_period")
    @classmethod
    def validate_budget_period(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("budget_period must be the first day of its month")
        return value
