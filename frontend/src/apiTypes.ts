export type Diet = "omnivore" | "vegetarian" | "vegan";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

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

export type GroceryJobResult = {
  plan: GroceryPlan;
  budget: GroceryBudget;
  spending_source: string;
};

export type GroceryConfig = {
  budget_period: string;
  source: "fixture";
  posted_cents: number;
  pending_cents: number;
  notice: string;
  recipes: CatalogItem[];
  ingredients: CatalogItem[];
};

export type GroceryJob = {
  id: string;
  status: JobStatus;
  result: GroceryJobResult | null;
  error_code: string | null;
};

export const SAMPLE_ESTIMATE_NOTICE =
  "Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";

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
