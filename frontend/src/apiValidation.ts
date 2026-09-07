import {
  SAMPLE_ESTIMATE_NOTICE,
  SHAPE_ERROR,
  isBool,
  isNonemptyString,
  isRecord,
  isSafeInteger,
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
} from "./apiTypes";

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

function isResult(value: unknown): value is GroceryJobResult {
  return (
    isRecord(value) &&
    isPlan(value.plan) &&
    isBudget(value.budget) &&
    isNonemptyString(value.spending_source)
  );
}

export function parseConfig(value: unknown): GroceryConfig {
  if (
    !isRecord(value) ||
    value.source !== "fixture" ||
    !isNonemptyString(value.budget_period) ||
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
