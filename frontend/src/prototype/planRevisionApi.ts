import { readJson } from "../api";
import type { PlanState } from "./planModel";
import { INGREDIENTS } from "./prototypeData";

export type PlanRevisionBody = {
  meals: { recipe_id: string; servings: number }[];
  pantry_ingredient_ids: string[];
  plan_cap_cents: number;
};

export const PLAN_REVISION_ERROR = "The plan revision response was not valid.";

export function planRevisionBody(state: PlanState): PlanRevisionBody {
  const pantry = state.pantry.filter((id) => Object.prototype.hasOwnProperty.call(INGREDIENTS, id));
  return {
    meals: state.meals.map((meal) => ({ recipe_id: meal.recipeId, servings: meal.servings })),
    pantry_ingredient_ids: [...new Set(pantry)],
    plan_cap_cents: state.budgetCents,
  };
}

export async function savePlanRevision(body: PlanRevisionBody, signal?: AbortSignal): Promise<string> {
  const data = await readJson("/api/grocery/plans", {
    method: "POST",
    signal,
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
  const id =
    typeof data === "object" && data !== null
      ? (data as { plan_revision_id?: unknown }).plan_revision_id
      : undefined;
  if (typeof id !== "string" || id.length === 0) {
    throw new Error(PLAN_REVISION_ERROR);
  }
  return id;
}
