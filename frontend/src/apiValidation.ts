import {
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
  type PlanLine,
  type SupermarketEstimate,
} from "./apiTypes";
import { isNutrition } from "./nutritionTypes";

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

function isSupermarketEstimate(value: unknown): value is SupermarketEstimate {
  if (!isRecord(value)) {
    return false;
  }
  const total = value.total_cents;
  if (total !== null && !isNonnegativeCents(total)) {
    return false;
  }
  return value.notice === SPOONACULAR_COST_NOTICE;
}

function isResult(value: unknown): value is GroceryJobResult {
  if (
    !isRecord(value) ||
    !isPlan(value.plan) ||
    !isBudget(value.budget) ||
    !isNonemptyString(value.spending_source)
  ) {
    return false;
  }
  if ("supermarket_estimate" in value && !isSupermarketEstimate(value.supermarket_estimate)) {
    return false;
  }
  if ("nutrition" in value && !isNutrition(value.nutrition)) {
    return false;
  }
  return true;
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
  return value as GroceryJob;
}
