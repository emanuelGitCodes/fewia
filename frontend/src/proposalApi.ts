import { HTTP_ERROR, SHAPE_ERROR, isAbortError } from "./api";
import { isRecord, isSafeInteger, isString } from "./apiTypes";
import { UUID } from "./chatValidation";
import { INGREDIENTS, isKnownRecipe } from "./prototype/prototypeData";

export type ProposalStatus = "pending" | "applied" | "discarded";
export type ProposalPreview = {
  meals: { recipe_id: string; servings: number }[];
  pantry_ingredient_ids: string[];
  plan_cap_cents: number | null;
};
export type Proposal = {
  id: string;
  status: ProposalStatus;
  base_plan_revision_id: string;
  preview: ProposalPreview;
  applied_plan_revision_id: string | null;
};

export const PROPOSAL_CONFLICT = "The proposal no longer fits the plan.";

// 409: the proposal is stale, discarded, or already applied.
export class ProposalConflict extends Error {
  constructor() {
    super(PROPOSAL_CONFLICT);
    this.name = "ProposalConflict";
  }
}

function isUuid(value: unknown): value is string {
  return isString(value) && UUID.test(value);
}

function parsePreview(value: unknown): ProposalPreview {
  if (!isRecord(value) || !Array.isArray(value.meals) || !Array.isArray(value.pantry_ingredient_ids)) {
    throw new Error(SHAPE_ERROR);
  }
  const cap = value.plan_cap_cents;
  const meals = value.meals.map((meal: unknown) => {
    if (
      !isRecord(meal) || !isString(meal.recipe_id) || !isKnownRecipe(meal.recipe_id) ||
      !isSafeInteger(meal.servings) || meal.servings < 1 || meal.servings > 8
    ) {
      throw new Error(SHAPE_ERROR);
    }
    return { recipe_id: meal.recipe_id, servings: meal.servings };
  });
  const pantry = value.pantry_ingredient_ids.map((id: unknown) => {
    if (!isString(id) || !Object.prototype.hasOwnProperty.call(INGREDIENTS, id)) {
      throw new Error(SHAPE_ERROR);
    }
    return id;
  });
  if (
    meals.length < 1 || meals.length > 3 ||
    new Set(meals.map((meal) => meal.recipe_id)).size !== meals.length ||
    new Set(pantry).size !== pantry.length
  ) {
    throw new Error(SHAPE_ERROR);
  }
  if (cap !== null && (!isSafeInteger(cap) || cap < 0)) {
    throw new Error(SHAPE_ERROR);
  }
  return { meals, pantry_ingredient_ids: pantry, plan_cap_cents: cap };
}

function parseProposal(value: unknown): Proposal {
  if (!isRecord(value)) {
    throw new Error(SHAPE_ERROR);
  }
  const { status, applied_plan_revision_id: applied } = value;
  if (
    !isUuid(value.id) || !isUuid(value.base_plan_revision_id) ||
    (status !== "pending" && status !== "applied" && status !== "discarded") ||
    (applied !== null && !isUuid(applied))
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    id: value.id,
    status,
    base_plan_revision_id: value.base_plan_revision_id,
    preview: parsePreview(value.preview),
    applied_plan_revision_id: applied,
  };
}

async function request(path: string, method: "GET" | "POST", signal: AbortSignal): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, { method, signal });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new Error(HTTP_ERROR, { cause: error });
  }
  if (response.status === 409) {
    throw new ProposalConflict();
  }
  if (!response.ok) {
    throw new Error(HTTP_ERROR);
  }
  try {
    return (await response.json()) as unknown;
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new Error(SHAPE_ERROR, { cause: error });
  }
}

function path(id: string, action: string): string {
  return `/api/grocery/proposals/${encodeURIComponent(id)}${action}`;
}

export async function fetchProposal(id: string, signal: AbortSignal): Promise<Proposal> {
  return parseProposal(await request(path(id, ""), "GET", signal));
}

export async function applyProposal(id: string, signal: AbortSignal): Promise<string> {
  const data = await request(path(id, "/apply"), "POST", signal);
  if (!isRecord(data) || !isUuid(data.plan_revision_id)) {
    throw new Error(SHAPE_ERROR);
  }
  return data.plan_revision_id;
}

export async function discardProposal(id: string, signal: AbortSignal): Promise<void> {
  const data = await request(path(id, "/discard"), "POST", signal);
  if (!isRecord(data) || data.status !== "discarded") {
    throw new Error(SHAPE_ERROR);
  }
}
