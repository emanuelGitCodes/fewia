export type Diet = "omnivore" | "vegetarian" | "vegan";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type SpendingSource = "manual" | "fixture" | "plaid_sandbox";

export type CatalogItem = {
  id: string;
  name: string;
};

export type MealRequest = {
  recipe_id: string;
  servings: number;
};

export type GroceryRequest = {
  meals: MealRequest[];
  budget_period: string;
  plan_cap_cents: number | null;
  pantry_ingredients: string[];
  ingredient_exclusions: string[];
  diet: Diet;
};

export type GroceryJobCreate = {
  request: GroceryRequest;
  monthly_limit_cents: number;
};

export type GroceryJobAck = {
  job_id: string;
  status: JobStatus;
};

export type PlanLine = {
  ingredient_id: string;
  name: string;
  unit: string;
  quantity: number;
  packages: number;
  cost_cents: number | null;
  from_pantry: boolean;
};

export type GroceryPlan = {
  lines: PlanLine[];
  total_cents: number | null;
  accepted: boolean;
  warnings: string[];
  catalog_version: string;
  notice: string;
};

export type GroceryBudget = {
  available_cents: number;
  pending_cents: number;
  stale: boolean;
  warnings: string[];
};

export type SupermarketEstimate = {
  total_cents: number | null;
  notice: string;
};

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

export type GroceryJobResult = {
  plan: GroceryPlan;
  budget: GroceryBudget;
  spending_source: string;
  meal_nutrition?: MealPlanNutrition;
  supermarket_estimate?: SupermarketEstimate;
};

export type GroceryConfig = {
  budget_period: string;
  source: SpendingSource;
  catalog_version: string;
  posted_cents: number;
  pending_cents: number;
  spending_refreshed_at: string | null;
  notice: string;
  recipes: CatalogItem[];
  ingredients: CatalogItem[];
};

export type ProviderCapabilities = {
  chat_configured: boolean;
  plaid_configured: boolean;
  instacart_configured: boolean;
  spending_source: SpendingSource;
};

export type GroceryJob = {
  id: string;
  status: JobStatus;
  result: GroceryJobResult | null;
  error_code: string | null;
};

export const SAMPLE_ESTIMATE_NOTICE =
  "Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";

export const NUTRITION_NOTICE =
  "Estimated nutrition from USDA FoodData Central for the selected recipe quantities. Pantry ingredients are included.";

export const NUTRITION_PORTION_NOTICE =
  "Portion estimates: one egg = 50 g, one corn tortilla = 24 g, one potato = 213 g. Actual sizes and preparation vary.";

export const SPOONACULAR_COST_NOTICE =
  "Average supermarket estimate from Spoonacular. Not a store price. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";

export const HTTP_ERROR =
  "The grocery request failed. Check meals, servings, and budget, then retry.";

export const SHAPE_ERROR =
  "The grocery service returned an unexpected response. Retry the request.";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isString(value: unknown): value is string {
  return typeof value === "string";
}

export function isNonemptyString(value: unknown): value is string {
  return isString(value) && value.length > 0;
}

export function isBool(value: unknown): value is boolean {
  return typeof value === "boolean";
}

export function isSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value);
}

export function isStatus(value: unknown): value is JobStatus {
  return (
    value === "queued" ||
    value === "running" ||
    value === "succeeded" ||
    value === "failed"
  );
}

export function isSpendingSource(value: unknown): value is SpendingSource {
  return value === "manual" || value === "fixture" || value === "plaid_sandbox";
}

export function sourceLabel(source: string): string {
  if (source === "manual") {
    return "Your entered budget";
  }
  if (source === "fixture") {
    return "Demo spending";
  }
  if (source === "plaid_sandbox") {
    return "Plaid Sandbox";
  }
  return "Unverified spending source";
}
