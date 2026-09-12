"""Estimate meal macros from consumed recipe quantities."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import GroceryRequest
from app.domain.nutrition import NutritionFacts
from app.domain.nutrition_catalog import NUTRITION

NOTICE = (
    "Estimated nutrition from USDA FoodData Central for the selected "
    "recipe quantities. Pantry ingredients are included."
)
PORTION_NOTICE = (
    "Portion estimates: one egg = 50 g, one corn tortilla = 24 g, "
    "one potato = 213 g. Actual sizes and preparation vary."
)

# Demo edible-portion estimates. They are not measured user food weights.
GRAMS_PER_EACH: dict[str, int] = {
    "eggs": 50,
    "tortillas": 24,
    "potato": 213,
}


@dataclass(frozen=True, slots=True)
class MacroTotals:
    energy_kcal: int
    protein_mg: int
    carbohydrate_mg: int
    fat_mg: int


@dataclass(frozen=True, slots=True)
class MealNutrition:
    recipe_id: str
    servings: int
    per_serving: MacroTotals
    total: MacroTotals


@dataclass(frozen=True, slots=True)
class MealPlanNutrition:
    notice: str
    portion_notice: str
    total: MacroTotals | None
    meals: tuple[MealNutrition, ...]


def _unavailable() -> MealPlanNutrition:
    return MealPlanNutrition(NOTICE, PORTION_NOTICE, None, ())


def _macros(energy: int, protein: int, carb: int, fat: int) -> MacroTotals:
    return MacroTotals(
        (energy + 50) // 100,
        (protein + 50) // 100,
        (carb + 50) // 100,
        (fat + 50) // 100,
    )


def _grams(
    ingredient_id: str, quantity: int, grams_per_each: Mapping[str, int]
) -> int | None:
    ingredient = INGREDIENTS.get(ingredient_id)
    if ingredient is None or type(quantity) is not int or quantity <= 0:
        return None
    if ingredient.unit == "g":
        return quantity
    if ingredient.unit != "each":
        return None
    portion = grams_per_each.get(ingredient_id)
    if portion is None:
        return None
    if type(portion) is not int or portion <= 0:
        return None
    return quantity * portion


def meal_nutrition(
    request: GroceryRequest,
    *,
    facts: Mapping[str, NutritionFacts] = NUTRITION,
    grams_per_each: Mapping[str, int] = GRAMS_PER_EACH,
) -> MealPlanNutrition:
    meals: list[MealNutrition] = []
    plan_energy = plan_protein = plan_carb = plan_fat = 0
    for meal in request.meals:
        servings = meal.servings
        if type(servings) is not int or servings <= 0:
            return _unavailable()
        recipe = RECIPES.get(meal.recipe_id)
        if recipe is None:
            return _unavailable()
        energy = protein = carb = fat = 0
        for ingredient_id, quantity in recipe.ingredients:
            nutrition = facts.get(ingredient_id)
            grams = _grams(ingredient_id, quantity, grams_per_each)
            if nutrition is None or grams is None:
                return _unavailable()
            energy += nutrition.energy_kcal * grams
            protein += nutrition.protein_mg * grams
            carb += nutrition.carbohydrate_mg * grams
            fat += nutrition.fat_mg * grams
        meal_energy = energy * servings
        meal_protein = protein * servings
        meal_carb = carb * servings
        meal_fat = fat * servings
        meals.append(
            MealNutrition(
                meal.recipe_id,
                servings,
                _macros(energy, protein, carb, fat),
                _macros(meal_energy, meal_protein, meal_carb, meal_fat),
            )
        )
        plan_energy += meal_energy
        plan_protein += meal_protein
        plan_carb += meal_carb
        plan_fat += meal_fat
    return MealPlanNutrition(
        NOTICE,
        PORTION_NOTICE,
        _macros(plan_energy, plan_protein, plan_carb, plan_fat),
        tuple(meals),
    )
