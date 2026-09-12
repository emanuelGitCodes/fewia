"""Label USDA nutrition for plan lines. Values stay per 100 g."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.nutrition import USDA_NUTRITION_NOTICE, NutritionFacts
from app.domain.nutrition_catalog import NUTRITION, NUTRITION_BASIS_G
from app.services.grocery_planner import PlanEstimate


@dataclass(frozen=True, slots=True)
class PlanNutritionItem:
    ingredient_id: str
    fdc_id: int
    energy_kcal: int
    protein_mg: int
    fat_mg: int
    carbohydrate_mg: int
    sodium_mg: int


@dataclass(frozen=True, slots=True)
class PlanNutrition:
    notice: str
    basis_g: int
    items: tuple[PlanNutritionItem, ...] | None


def _item(ingredient_id: str, facts: NutritionFacts) -> PlanNutritionItem:
    return PlanNutritionItem(
        ingredient_id=ingredient_id,
        fdc_id=facts.fdc_id,
        energy_kcal=facts.energy_kcal,
        protein_mg=facts.protein_mg,
        fat_mg=facts.fat_mg,
        carbohydrate_mg=facts.carbohydrate_mg,
        sodium_mg=facts.sodium_mg,
    )


def nutrition_for_plan(
    plan: PlanEstimate,
    facts: Mapping[str, NutritionFacts] = NUTRITION,
) -> PlanNutrition:
    items: list[PlanNutritionItem] = []
    for line in plan.lines:
        nutrition = facts.get(line.ingredient_id)
        if nutrition is None:
            return PlanNutrition(USDA_NUTRITION_NOTICE, NUTRITION_BASIS_G, None)
        items.append(_item(line.ingredient_id, nutrition))
    return PlanNutrition(USDA_NUTRITION_NOTICE, NUTRITION_BASIS_G, tuple(items))
