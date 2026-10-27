import type { ChatBudget } from "../chatConversationModel";
import type { ChatJob } from "../chatTypes";
import { formatDollars } from "../money";
import type { PlanState } from "./planModel";
import { INGREDIENTS, RECIPES, isKnownRecipe } from "./prototypeData";

export const MAX_IDEAS = 3;

export type ChatIdea = { recipeId: string; servings: number };

function servingsText(servings: number): string {
  return `${String(servings)} ${servings === 1 ? "serving" : "servings"}`;
}

// The chat request carries no plan, so the client states the plan in the message text.
export function planChatPrefix(state: PlanState): string {
  if (state.meals.length === 0) {
    return "My current plan: no meals.\n\n";
  }
  const meals = state.meals
    .map((meal) => `${RECIPES[meal.recipeId].name}, ${servingsText(meal.servings)}`)
    .join("; ");
  const pantry = state.pantry
    .filter((id) => Object.prototype.hasOwnProperty.call(INGREDIENTS, id))
    .map((id) => INGREDIENTS[id].name);
  const pantryText = pantry.length === 0 ? "none" : pantry.join(", ");
  return (
    `My current plan: ${meals}. Pantry: ${pantryText}. ` +
    `Plan cap: ${formatDollars(state.budgetCents)}.\n\n`
  );
}

// An invalid cap has no last valid value to send, so the chat stays blocked.
export function chatBudget(state: PlanState): ChatBudget | null {
  if (state.budgetError !== null) {
    return null;
  }
  return { monthly_limit_cents: state.budgetCents, plan_cap_cents: state.budgetCents };
}

export function ideasFromJob(job: ChatJob, plannedIds: string[]): ChatIdea[] {
  const result = job.result;
  if (result === null || (result.status !== "planned" && result.status !== "needs_revision")) {
    return [];
  }
  const ideas: ChatIdea[] = [];
  for (const meal of result.request?.meals ?? []) {
    if (ideas.length >= MAX_IDEAS) {
      break;
    }
    const id = meal.recipe_id;
    if (!isKnownRecipe(id) || plannedIds.includes(id) || ideas.some((idea) => idea.recipeId === id)) {
      continue;
    }
    ideas.push({ recipeId: id, servings: meal.servings });
  }
  return ideas;
}
