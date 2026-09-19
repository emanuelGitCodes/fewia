import { isNonemptyString, isRecord, isSafeInteger } from "./apiTypes";

export const NUTRITION_NOTICE =
  "Estimated nutrition from USDA FoodData Central for the selected recipe quantities. Pantry ingredients are included.";

export const NUTRITION_PORTION_NOTICE =
  "Portion estimates: one egg = 50 g, one corn tortilla = 24 g, one potato = 213 g. Actual sizes and preparation vary.";

const MACRO_KEYS = ["energy_kcal", "protein_mg", "carbohydrate_mg", "fat_mg"] as const;

export type MacroTotals = {
  energy_kcal: number;
  protein_mg: number;
  carbohydrate_mg: number;
  fat_mg: number;
};

export type MealNutrition = {
  recipe_id: string;
  servings: number;
  per_serving: MacroTotals;
  total: MacroTotals;
};

export type MealPlanNutrition = {
  notice: string;
  portion_notice: string;
  total: MacroTotals | null;
  meals: MealNutrition[];
};

function isMacroTotals(value: unknown): value is MacroTotals {
  return (
    isRecord(value) &&
    MACRO_KEYS.every((key) => isSafeInteger(value[key]) && value[key] >= 0)
  );
}

function isMealNutrition(value: unknown): value is MealNutrition {
  return (
    isRecord(value) &&
    isNonemptyString(value.recipe_id) &&
    isSafeInteger(value.servings) &&
    value.servings >= 1 &&
    value.servings <= 8 &&
    isMacroTotals(value.per_serving) &&
    isMacroTotals(value.total)
  );
}

export function isNutrition(value: unknown): value is MealPlanNutrition {
  if (
    !isRecord(value) ||
    value.notice !== NUTRITION_NOTICE ||
    value.portion_notice !== NUTRITION_PORTION_NOTICE ||
    !Array.isArray(value.meals) ||
    !value.meals.every(isMealNutrition)
  ) {
    return false;
  }
  if (value.total === null) {
    return value.meals.length === 0;
  }
  return isMacroTotals(value.total) && value.meals.length >= 1 && value.meals.length <= 3;
}
