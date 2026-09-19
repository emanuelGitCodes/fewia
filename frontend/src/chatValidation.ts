import {
  SHAPE_ERROR,
  isNonemptyString,
  isRecord,
  isSafeInteger,
  isStatus,
  isString,
  type GroceryRequest,
} from "./apiTypes";
import { isBudget, isPlan } from "./apiValidation";
import type { ChatJob, ChatResult, ChatToolTrace, ChatUsage } from "./chatTypes";
import { isNutrition, type MealPlanNutrition } from "./nutritionTypes";

const HEX64 = /^[0-9a-f]{64}$/;
const FIRST_DAY = /^(\d{4})-(\d{2})-01$/;
function isRequest(value: unknown): value is GroceryRequest {
  if (!isRecord(value) || !Array.isArray(value.meals) || !isString(value.budget_period)) {
    return false;
  }
  const month = Number(value.budget_period.slice(5, 7));
  const cap = value.plan_cap_cents;
  const diet = value.diet;
  const mealsOk = value.meals.every(
    (meal) =>
      isRecord(meal) &&
      isNonemptyString(meal.recipe_id) &&
      isSafeInteger(meal.servings) &&
      meal.servings >= 1 &&
      meal.servings <= 8,
  );
  return (
    FIRST_DAY.test(value.budget_period) && month >= 1 && month <= 12 &&
    value.meals.length >= 1 && value.meals.length <= 3 && mealsOk &&
    (cap === null || (isSafeInteger(cap) && cap >= 0)) &&
    Array.isArray(value.pantry_ingredients) && value.pantry_ingredients.every(isString) &&
    Array.isArray(value.ingredient_exclusions) && value.ingredient_exclusions.every(isString) &&
    (diet === "omnivore" || diet === "vegetarian" || diet === "vegan")
  );
}
function isUsage(value: unknown): value is ChatUsage {
  return (
    isRecord(value) && isSafeInteger(value.inputTokens) && value.inputTokens >= 0 &&
    isSafeInteger(value.outputTokens) && value.outputTokens >= 0
  );
}
function copyTrace(value: unknown): ChatToolTrace | null {
  if (
    !isRecord(value) || !isNonemptyString(value.tool) ||
    (value.outcome !== "success" && value.outcome !== "error") ||
    !isNonemptyString(value.tool_use_id) || value.tool_use_id.length > 64 ||
    !isSafeInteger(value.sequence) || value.sequence < 1
  ) {
    return null;
  }
  const revision = value.revision_index;
  const evidenceId = value.evidence_id;
  const revisionHex = value.evidence_revision_id;
  if (
    (revision !== null && (!isSafeInteger(revision) || revision < 1 || revision > 3)) ||
    (evidenceId !== undefined && !isNonemptyString(evidenceId)) ||
    (revisionHex !== undefined && !(isString(revisionHex) && HEX64.test(revisionHex)))
  ) {
    return null;
  }
  return {
    tool: value.tool, outcome: value.outcome, tool_use_id: value.tool_use_id,
    sequence: value.sequence, revision_index: revision,
    ...(evidenceId === undefined ? {} : { evidence_id: evidenceId }),
    ...(revisionHex === undefined ? {} : { evidence_revision_id: revisionHex }),
  };
}
function copyTraces(value: unknown): ChatToolTrace[] | null {
  if (!Array.isArray(value) || value.length > 24) {
    return null;
  }
  const traces: ChatToolTrace[] = [];
  for (const item of value) {
    const copied = copyTrace(item);
    if (copied === null) {
      return null;
    }
    traces.push(copied);
  }
  return traces;
}
export function parseChatResult(value: unknown): ChatResult {
  if (!isRecord(value)) {
    throw new Error(SHAPE_ERROR);
  }
  const traces = copyTraces(value.tool_trace);
  const status = value.status;
  const planned = status === "planned";
  const knownStatus =
    planned || status === "needs_revision" || status === "clarification" ||
    status === "limit" || status === "incomplete";
  if (
    traces === null || !knownStatus || !isNonemptyString(value.answer) ||
    (value.spending_source !== "fixture" && value.spending_source !== "plaid_sandbox") ||
    !isSafeInteger(value.model_turns) || value.model_turns < 0 || value.model_turns > 8 ||
    !isSafeInteger(value.planner_revisions) || value.planner_revisions < 0 ||
    value.planner_revisions > 3 || (value.usage !== null && !isUsage(value.usage))
  ) {
    throw new Error(SHAPE_ERROR);
  }
  const plan = value.plan;
  const planOk =
    isPlan(plan) && isBudget(value.budget) && isRequest(value.request) &&
    isString(value.evidence_revision_id) && HEX64.test(value.evidence_revision_id) &&
    (value.evidence_id === null || isNonemptyString(value.evidence_id)) &&
    plan.accepted === planned;
  const extrasNull =
    value.budget === null && value.request === null &&
    value.evidence_id === null && value.evidence_revision_id === null;
  const drop = status === "limit" || status === "incomplete";
  const need = planned || status === "needs_revision";
  if ((plan !== null && (drop || !planOk)) || (plan === null && (need || !extrasNull))) {
    throw new Error(SHAPE_ERROR);
  }
  const hasNutrition = "nutrition" in value;
  if (hasNutrition && (plan === null || !isNutrition(value.nutrition))) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    status: status as ChatResult["status"],
    answer: value.answer,
    plan: structuredClone(plan) as ChatResult["plan"],
    budget: structuredClone(value.budget) as ChatResult["budget"],
    request: structuredClone(value.request) as ChatResult["request"],
    evidence_id: value.evidence_id as string | null,
    evidence_revision_id: value.evidence_revision_id as string | null,
    spending_source: value.spending_source as ChatResult["spending_source"],
    tool_trace: traces,
    model_turns: value.model_turns,
    planner_revisions: value.planner_revisions,
    usage: value.usage === null ? null : {
      inputTokens: value.usage.inputTokens, outputTokens: value.usage.outputTokens,
    },
    ...(hasNutrition ? { nutrition: structuredClone(value.nutrition) as MealPlanNutrition } : {}),
  };
}
export function parseChatJob(value: unknown): ChatJob {
  if (
    !isRecord(value) || !isNonemptyString(value.id) || !isStatus(value.status) ||
    (value.error_code !== null && !isString(value.error_code)) ||
    (value.status === "succeeded" && value.result == null)
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    id: value.id,
    status: value.status,
    result: value.result === null ? null : parseChatResult(value.result),
    error_code: value.error_code as string | null,
  };
}
