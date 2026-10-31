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
    "chicken_pasta",
    "chicken_stir_fry",
    "chicken_curry",
    "chicken_vegetable_soup",
    "chicken_burrito_bowls",
    "chicken_potato_bake",
    "chicken_lentil_stew",
    "chicken_chickpea_skillet",
    "chicken_fried_rice",
    "chicken_tortilla_soup",
    "egg_fried_rice",
    "egg_tacos",
    "tomato_egg_pasta",
    "potato_hash_with_eggs",
    "chickpea_egg_scramble",
    "vegetable_egg_stir_fry",
    "egg_rice_bowls",
    "lentil_egg_skillet",
    "rice_and_beans",
    "lentil_pasta",
    "chickpea_tacos",
    "potato_curry",
    "tomato_rice",
    "garlic_tomato_pasta",
    "vegetable_soup",
    "lentil_tacos",
    "chickpea_pasta",
    "coconut_lentil_curry",
    "potato_tacos",
    "salsa_rice_bowls",
)
Diet = Literal["omnivore", "vegetarian", "vegan"]
SAMPLE_ESTIMATE_NOTICE = (
    "Estimated from the demo price catalog. Store prices, availability, "
    "taxes, delivery fees, and tips are not verified."
)


class MealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: StrictStr = Field(description="A supported catalog recipe ID.")
    servings: StrictInt = Field(
        ge=1, le=8, description="Servings for this meal, 1 to 8."
    )

    @field_validator("recipe_id")
    @classmethod
    def validate_recipe_id(cls, value: str) -> str:
        if value not in SUPPORTED_RECIPE_IDS:
            raise ValueError("recipe_id is not supported")
        return value


class GroceryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meals: list[MealRequest] = Field(
        min_length=1,
        max_length=3,
        description=("One to three supported catalog meals with servings from 1 to 8."),
    )
    budget_period: date = Field(
        description=(
            "First day of the budget month, YYYY-MM-DD, as the server reports it."
        )
    )
    plan_cap_cents: StrictInt | None = Field(
        default=None,
        ge=0,
        description=("Server plan cap in cents. Keep it or lower it. Never raise it."),
    )
    pantry_ingredients: list[StrictStr] = Field(
        default_factory=list,
        description=(
            "Catalog ingredient IDs the user already owns. They cost "
            "nothing in the plan."
        ),
    )
    ingredient_exclusions: list[StrictStr] = Field(
        default_factory=list,
        description=(
            "Catalog ingredient IDs the user excludes, or a restriction "
            "term exactly as the user wrote it."
        ),
    )
    diet: Diet = Field(
        default="omnivore",
        description="Diet the plan must satisfy: omnivore, vegetarian, or vegan.",
    )

    @field_validator("budget_period")
    @classmethod
    def validate_budget_period(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("budget_period must be the first day of its month")
        return value
