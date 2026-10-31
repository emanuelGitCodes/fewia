import { initialPlanState, planLines, withPlanBudgetInput, type PlanState } from "./planModel";
import { INGREDIENTS, isKnownRecipe, MAX_MEALS, MAX_SERVINGS, MIN_SERVINGS } from "./prototypeData";

export const PLAN_CHECKPOINT_KEY = "fewia.plan-checkpoint.v1";
export const PLAN_CHECKPOINT_TTL_MS = 30 * 60 * 1000;
export const MAX_CHECKPOINT_LENGTH = 16_384;
export const MAX_BUDGET_DRAFT_LENGTH = 256;
export const PLAN_RESTORE_ERROR = "Your saved plan could not be restored. Please check your plan.";
export const PLAN_SAVE_ERROR = "Could not save your plan for sign-in. Try Connect Kroger again.";

type ReturnPlan = { state: PlanState; returning: boolean; error: string | null };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function keys(value: Record<string, unknown>, expected: string[]): boolean {
  return (
    Object.keys(value).length === expected.length &&
    expected.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

function ingredientIds(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.length <= Object.keys(INGREDIENTS).length &&
    value.every((id: unknown) =>
      typeof id === "string" && Object.prototype.hasOwnProperty.call(INGREDIENTS, id),
    ) &&
    new Set(value).size === value.length
  );
}

function decode(serialized: string, now: number): PlanState | null {
  if (serialized.length > MAX_CHECKPOINT_LENGTH) {
    return null;
  }
  const value: unknown = JSON.parse(serialized);
  if (
    !record(value) || !keys(value, ["version", "savedAt", "plan"]) || value.version !== 1 ||
    typeof value.savedAt !== "number" || !Number.isSafeInteger(value.savedAt) ||
    value.savedAt < 0 || value.savedAt > now || now - value.savedAt > PLAN_CHECKPOINT_TTL_MS
  ) {
    return null;
  }
  const plan = value.plan;
  if (
    !record(plan) || !keys(plan, ["meals", "pantry", "checked", "view", "budgetInput", "budgetCents"]) ||
    !Array.isArray(plan.meals) || plan.meals.length > MAX_MEALS ||
    !ingredientIds(plan.pantry) || !ingredientIds(plan.checked) ||
    (plan.view !== "plan" && plan.view !== "pantry") ||
    typeof plan.budgetInput !== "string" || plan.budgetInput.length > MAX_BUDGET_DRAFT_LENGTH ||
    typeof plan.budgetCents !== "number" || !Number.isSafeInteger(plan.budgetCents) || plan.budgetCents < 0
  ) {
    return null;
  }
  const meals: PlanState["meals"] = [];
  for (const meal of plan.meals) {
    if (
      !record(meal) || !keys(meal, ["recipeId", "servings"]) ||
      typeof meal.recipeId !== "string" || !isKnownRecipe(meal.recipeId) ||
      typeof meal.servings !== "number" || !Number.isInteger(meal.servings) ||
      meal.servings < MIN_SERVINGS || meal.servings > MAX_SERVINGS ||
      meals.some((current) => current.recipeId === meal.recipeId)
    ) {
      return null;
    }
    meals.push({ recipeId: meal.recipeId, servings: meal.servings });
  }
  const state = withPlanBudgetInput(
    {
      meals,
      pantry: plan.pantry,
      checked: plan.checked,
      view: plan.view,
      budgetInput: plan.budgetInput,
      budgetCents: plan.budgetCents,
      budgetError: null,
      servingsError: null,
    },
    plan.budgetInput,
  );
  if (state.budgetCents !== plan.budgetCents) {
    return null;
  }
  const bought = new Set(
    planLines(state).filter((line) => !line.fromPantry).map((line) => line.ingredientId),
  );
  return state.checked.every((id) => bought.has(id)) ? state : null;
}

export function savePlanCheckpoint(state: PlanState): boolean {
  try {
    const { meals, pantry, checked, view, budgetInput, budgetCents } = state;
    const now = Date.now();
    const serialized = JSON.stringify({
      version: 1,
      savedAt: now,
      plan: {
        meals: meals.map(({ recipeId, servings }) => ({ recipeId, servings })),
        pantry, checked, view, budgetInput, budgetCents,
      },
    });
    if (decode(serialized, now) === null) {
      return false;
    }
    const storage = window.sessionStorage;
    storage.setItem(PLAN_CHECKPOINT_KEY, serialized);
    return storage.getItem(PLAN_CHECKPOINT_KEY) === serialized;
  } catch {
    return false;
  }
}

// Reading leaves the checkpoint intact for React StrictMode initialization.
export function readReturnPlan(): ReturnPlan {
  const marker = new URLSearchParams(window.location.search).get("kroger");
  const returning = marker === "connected" || marker === "error";
  if (!returning) {
    return { state: initialPlanState(), returning, error: null };
  }
  try {
    const serialized = window.sessionStorage.getItem(PLAN_CHECKPOINT_KEY);
    const state = serialized === null ? null : decode(serialized, Date.now());
    if (state !== null) {
      return { state, returning, error: null };
    }
  } catch {
    // Storage and parse failures use the same bounded message.
  }
  return { state: initialPlanState(), returning, error: PLAN_RESTORE_ERROR };
}

export function consumePlanCheckpoint(): boolean {
  try {
    window.sessionStorage.removeItem(PLAN_CHECKPOINT_KEY);
    return true;
  } catch {
    return false;
  }
}
