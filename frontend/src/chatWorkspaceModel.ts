import type { GroceryConfig, GroceryJob } from "./apiTypes";
import type { FormState } from "./BudgetForm";
import type { ChatBudget } from "./chatConversationModel";
import type { ChatJob, ChatResult } from "./chatTypes";
import { parseDollars } from "./money";

function centsInput(cents: number): string {
  const dollars = Math.trunc(cents / 100);
  const fraction = cents % 100;
  return `${dollars}.${String(fraction).padStart(2, "0")}`;
}

export function chatBudgetFromForm(form: FormState): ChatBudget | null {
  try {
    const monthly = parseDollars(form.monthly);
    const cap = parseDollars(form.cap, true);
    if (monthly === null) {
      return null;
    }
    return { monthly_limit_cents: monthly, plan_cap_cents: cap };
  } catch {
    return null;
  }
}

export function chatEstimateJob(job: ChatJob | null): GroceryJob | null {
  if (job === null || job.status !== "succeeded") {
    return null;
  }
  const result = job.result;
  if (result === null || result.plan === null || result.budget === null) {
    return null;
  }
  return {
    id: job.id,
    status: job.status,
    error_code: job.error_code,
    result: {
      plan: structuredClone(result.plan),
      budget: structuredClone(result.budget),
      spending_source: result.spending_source,
    },
  };
}

export function formFromChat(form: FormState, result: ChatResult): FormState {
  const request = result.request;
  const budget = chatBudgetFromForm(form);
  if (request === null || budget === null) {
    return form;
  }
  const currentCap = budget.plan_cap_cents;
  const requestCap = request.plan_cap_cents;
  let cap = form.cap;
  if (requestCap !== null) {
    const chosen = currentCap === null ? requestCap : Math.min(currentCap, requestCap);
    if (chosen !== currentCap) {
      cap = centsInput(chosen);
    }
  }
  return {
    monthly: form.monthly,
    cap,
    meals: request.meals.map((meal) => ({
      recipe_id: meal.recipe_id,
      servings: meal.servings,
    })),
    diet: request.diet,
    pantry: [...request.pantry_ingredients],
    exclusions: [...request.ingredient_exclusions],
  };
}

export function configFingerprint(config: GroceryConfig | null): string {
  if (config === null) {
    return "";
  }
  return JSON.stringify([
    config.budget_period,
    config.source,
    config.posted_cents,
    config.pending_cents,
    config.catalog_version,
    config.spending_refreshed_at,
  ]);
}
