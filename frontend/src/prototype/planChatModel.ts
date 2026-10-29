import type { ChatBudget } from "../chatConversationModel";
import type { ChatJob } from "../chatTypes";
import { formatDollars } from "../money";
import type { PlanState } from "./planModel";
import { INGREDIENTS, RECIPES, isKnownRecipe } from "./prototypeData";

export const MAX_IDEAS = 3;

export type ChatIdea = { recipeId: string; servings: number };
export type ChatReply = { ideas: ChatIdea[]; answered: boolean };

export function retainChatReplies(
  current: ReadonlyMap<string, ChatReply>,
  assistantIds: string[],
  job: ChatJob | null,
  plannedIds: string[],
): ReadonlyMap<string, ChatReply> {
  const completed = job?.status === "succeeded" && job.result !== null ? job : null;
  const retained = new Set(assistantIds);
  if (completed !== null) {
    retained.add(completed.id);
  }
  const next = new Map([...current].filter(([id]) => retained.has(id)));
  if (completed !== null && completed.result !== null && !next.has(completed.id)) {
    next.set(completed.id, {
      ideas: ideasFromJob(completed, plannedIds),
      answered: completed.result.status !== "limit" && completed.result.status !== "incomplete",
    });
  }
  return next.size === current.size && [...next.keys()].every((id) => current.has(id))
    ? current
    : next;
}

function servingsText(servings: number): string {
  return `${String(servings)} ${servings === 1 ? "serving" : "servings"}`;
}

// Fallback when the plan cannot be saved as a revision: the client states the plan in the message text.
export function planChatPrefix(state: PlanState): string {
  const meals =
    state.meals.length === 0
      ? "no meals"
      : state.meals
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
