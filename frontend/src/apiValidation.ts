import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  SAMPLE_ESTIMATE_NOTICE,
  SHAPE_ERROR,
  SPOONACULAR_COST_NOTICE,
  isBool,
  isNonemptyString,
  isRecord,
  isSafeInteger,
  isSpendingSource,
  isStatus,
  isString,
  type CatalogItem,
  type GroceryBudget,
  type GroceryConfig,
  type GroceryJob,
  type GroceryJobAck,
  type GroceryJobResult,
  type GroceryPlan,
  type JobErrorDetail,
  type MacroTotals,
  type MealNutrition,
  type MealPlanNutrition,
  type PlanLine,
  type SupermarketEstimate,
  type SupermarketLine,
} from "./apiTypes";

function isTimezoneTimestamp(value: unknown): value is string {
  if (!isString(value)) {
    return false;
  }
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    return false;
  }
  return !Number.isNaN(Date.parse(value));
}

function isSignedCents(value: unknown): value is number {
  return isSafeInteger(value);
}
function isNonnegativeCents(value: unknown): value is number {
  return isSafeInteger(value) && value >= 0;
}
function isPositiveQuantity(value: unknown): value is number {
  return isSafeInteger(value) && value > 0;
}
function isStrings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}
function isItem(value: unknown): value is CatalogItem {
  return isRecord(value) && isNonemptyString(value.id) && isNonemptyString(value.name);
}
function isLine(value: unknown): value is PlanLine {
  if (!isRecord(value)) {
    return false;
  }
  const cost = value.cost_cents;
  if (cost !== null && !isNonnegativeCents(cost)) {
    return false;
  }
  return (
    isNonemptyString(value.ingredient_id) &&
    isNonemptyString(value.name) &&
    isNonemptyString(value.unit) &&
    isPositiveQuantity(value.quantity) &&
    isNonnegativeCents(value.packages) &&
    isBool(value.from_pantry)
  );
}

export function isPlan(value: unknown): value is GroceryPlan {
  if (!isRecord(value) || !Array.isArray(value.lines) || !value.lines.every(isLine)) {
    return false;
  }
  const total = value.total_cents;
  if (total !== null && !isNonnegativeCents(total)) {
    return false;
  }
  if (!isBool(value.accepted) || !isStrings(value.warnings)) {
    return false;
  }
  if (!isNonemptyString(value.catalog_version) || value.notice !== SAMPLE_ESTIMATE_NOTICE) {
    return false;
  }
  const incomplete = total === null || value.lines.some((line) => line.cost_cents === null);
  if (incomplete && value.accepted) {
    return false;
  }
  return true;
}

export function isBudget(value: unknown): value is GroceryBudget {
  return (
    isRecord(value) &&
    isNonnegativeCents(value.available_cents) &&
    isSignedCents(value.pending_cents) &&
    isBool(value.stale) &&
    isStrings(value.warnings)
  );
}

function copyMacros(value: unknown): MacroTotals | null {
  if (!isRecord(value)) {
    return null;
  }
  const energy = value.energy_kcal;
  const protein = value.protein_mg;
  const carb = value.carbohydrate_mg;
  const fat = value.fat_mg;
  if (
    !isNonnegativeCents(energy) ||
    !isNonnegativeCents(protein) ||
    !isNonnegativeCents(carb) ||
    !isNonnegativeCents(fat)
  ) {
    return null;
  }
  return {
    energy_kcal: energy,
    protein_mg: protein,
    carbohydrate_mg: carb,
    fat_mg: fat,
  };
}

function copyMealNutrition(value: unknown): MealNutrition | null {
  if (!isRecord(value) || !isNonemptyString(value.recipe_id)) {
    return null;
  }
  const servings = value.servings;
  const perServing = copyMacros(value.per_serving);
  const total = copyMacros(value.total);
  if (!isSafeInteger(servings) || servings < 1 || servings > 8 || perServing === null || total === null) {
    return null;
  }
  return { recipe_id: value.recipe_id, servings, per_serving: perServing, total };
}

function planNutrition(total: MacroTotals | null, meals: MealNutrition[]): MealPlanNutrition {
  return { notice: NUTRITION_NOTICE, portion_notice: NUTRITION_PORTION_NOTICE, total, meals };
}

export function copyMealPlanNutrition(value: unknown): MealPlanNutrition | null {
  if (
    !isRecord(value) ||
    value.notice !== NUTRITION_NOTICE ||
    value.portion_notice !== NUTRITION_PORTION_NOTICE ||
    !Array.isArray(value.meals)
  ) {
    return null;
  }
  const meals: MealNutrition[] = [];
  for (const item of value.meals) {
    const meal = copyMealNutrition(item);
    if (meal === null) {
      return null;
    }
    meals.push(meal);
  }
  if (value.total === null) {
    return meals.length === 0 ? planNutrition(null, []) : null;
  }
  const total = copyMacros(value.total);
  return total !== null && meals.length >= 1 && meals.length <= 3 ? planNutrition(total, meals) : null;
}

export function copySupermarketEstimate(value: unknown): SupermarketEstimate | null {
  if (!isRecord(value)) {
    return null;
  }
  const total = value.total_cents;
  if (total !== null && !isNonnegativeCents(total)) {
    return null;
  }
  if (value.notice !== SPOONACULAR_COST_NOTICE) {
    return null;
  }
  const totalCents = (total === null ? null : total) as number | null;
  if (!("lines" in value)) {
    return { total_cents: totalCents, notice: SPOONACULAR_COST_NOTICE, lines: [] };
  }
  if (!Array.isArray(value.lines)) {
    return null;
  }
  const lines: SupermarketLine[] = [];
  for (const item of value.lines) {
    if (!isRecord(item) || !isNonemptyString(item.ingredient_id)) {
      return null;
    }
    const cents = item.cents;
    if (cents !== null && !isNonnegativeCents(cents)) {
      return null;
    }
    lines.push({ ingredient_id: item.ingredient_id, cents: cents as number | null });
  }
  return { total_cents: totalCents, notice: SPOONACULAR_COST_NOTICE, lines };
}

function isResult(value: unknown): value is GroceryJobResult {
  if (
    !isRecord(value) ||
    !isPlan(value.plan) ||
    !isBudget(value.budget) ||
    !isNonemptyString(value.spending_source) ||
    (value.meal_nutrition !== undefined && copyMealPlanNutrition(value.meal_nutrition) === null)
  ) {
    return false;
  }
  if (!("supermarket_estimate" in value)) {
    return true;
  }
  return copySupermarketEstimate(value.supermarket_estimate) !== null;
}

export function parseConfig(value: unknown): GroceryConfig {
  if (
    !isRecord(value) ||
    !isSpendingSource(value.source) ||
    !isNonemptyString(value.budget_period) ||
    !isNonemptyString(value.catalog_version) ||
    !isSignedCents(value.posted_cents) ||
    !isSignedCents(value.pending_cents) ||
    value.notice !== SAMPLE_ESTIMATE_NOTICE ||
    !Array.isArray(value.recipes) ||
    !value.recipes.every(isItem) ||
    !Array.isArray(value.ingredients) ||
    !value.ingredients.every(isItem)
  ) {
    throw new Error(SHAPE_ERROR);
  }
  if (value.spending_refreshed_at !== null && !isTimezoneTimestamp(value.spending_refreshed_at)) {
    throw new Error(SHAPE_ERROR);
  }
  return value as GroceryConfig;
}

export function parseAck(value: unknown): GroceryJobAck {
  if (!isRecord(value) || !isNonemptyString(value.job_id) || !isStatus(value.status)) {
    throw new Error(SHAPE_ERROR);
  }
  return { job_id: value.job_id, status: value.status };
}

function copyErrorDetail(value: unknown): JobErrorDetail | null {
  if (!isRecord(value) || !isString(value.recipe_id) || !isString(value.ingredient_id)) {
    return null;
  }
  return { recipe_id: value.recipe_id, ingredient_id: value.ingredient_id };
}

export function parseJob(value: unknown): GroceryJob {
  if (!isRecord(value) || !isNonemptyString(value.id) || !isStatus(value.status)) {
    throw new Error(SHAPE_ERROR);
  }
  if (value.error_code !== null && !isString(value.error_code)) {
    throw new Error(SHAPE_ERROR);
  }
  if (value.status === "succeeded" && value.result == null) {
    throw new Error(SHAPE_ERROR);
  }
  if (value.result !== null && !isResult(value.result)) {
    throw new Error(SHAPE_ERROR);
  }
  const error_detail = copyErrorDetail(value.error_detail);
  if (isRecord(value.result) && "supermarket_estimate" in value.result) {
    const supermarket_estimate = copySupermarketEstimate(value.result.supermarket_estimate);
    if (supermarket_estimate === null) {
      throw new Error(SHAPE_ERROR);
    }
    return {
      ...value,
      error_detail,
      result: { ...value.result, supermarket_estimate },
    } as GroceryJob;
  }
  return { ...value, error_detail } as GroceryJob;
}
