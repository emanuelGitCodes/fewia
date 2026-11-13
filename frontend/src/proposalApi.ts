import {
  HTTP_ERROR,
  SHAPE_ERROR,
  apiRequest,
  captureSessionGuard,
  isAbortError,
} from "./api";
import { UUID, isRecord, isSafeInteger, isString } from "./apiTypes";
import { isKnownIngredient, isKnownRecipe } from "./prototype/prototypeData";

export type ProposalStatus = "pending" | "applied" | "discarded";
export type PlanSnapshot = {
  meals: { recipe_id: string; servings: number }[];
  pantry_ingredient_ids: string[];
  plan_cap_cents: number | null;
};
export type ProposalPreview = PlanSnapshot;
export type AppliedProposal = {
  plan_revision_id: string;
  snapshot: PlanSnapshot;
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

export type ProposalConstraintReason =
  | "over_budget"
  | "diet_conflict"
  | "exclusion_conflict"
  | "estimate_unavailable";

export class ProposalConstraintsError extends Error {
  constructor(
    readonly reason: ProposalConstraintReason,
    readonly amounts: { totalCents: number; availableCents: number } | null = null,
  ) {
    super("The proposed change does not meet your constraints.");
    this.name = "ProposalConstraintsError";
  }
}

function parseConstraints(value: unknown): ProposalConstraintsError | null {
  if (!isRecord(value) || !isRecord(value.detail)) {
    return null;
  }
  const { code, reason, total_cents: total, available_cents: available } = value.detail;
  if (
    code !== "proposal_constraints" ||
    (reason !== "over_budget" && reason !== "diet_conflict" &&
      reason !== "exclusion_conflict" && reason !== "estimate_unavailable")
  ) {
    return null;
  }
  const amounts = reason === "over_budget" &&
    isSafeInteger(total) && total >= 0 &&
    isSafeInteger(available) && available >= 0 && total > available
    ? { totalCents: total, availableCents: available }
    : null;
  return new ProposalConstraintsError(reason, amounts);
}

function isUuid(value: unknown): value is string {
  return isString(value) && UUID.test(value);
}

function parseSnapshot(value: unknown): PlanSnapshot {
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
    if (!isString(id) || !isKnownIngredient(id)) {
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
    preview: parseSnapshot(value.preview),
    applied_plan_revision_id: applied,
  };
}

function readBody(response: Response, signal: AbortSignal): Promise<unknown> {
  if (signal.aborted) return Promise.reject(new DOMException("Aborted", "AbortError"));
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort);
    Promise.resolve().then(() => response.json() as Promise<unknown>).then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

async function request(
  path: string,
  method: "GET" | "POST",
  signal: AbortSignal,
  checkConstraints = false,
  body?: { plan_cap_cents: number } | { confirm: true },
): Promise<unknown> {
  const isCurrent = captureSessionGuard();
  const assertCurrent = (): void => {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    if (!isCurrent()) throw new Error(HTTP_ERROR);
  };
  assertCurrent();
  let response: Response;
  try {
    response = await apiRequest(path, {
      method,
      signal,
      ...(body === undefined ? {} : {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    });
  } catch (error) {
    assertCurrent();
    if (isAbortError(error)) throw error;
    throw new Error(HTTP_ERROR, { cause: error });
  }
  assertCurrent();
  if (!response.ok && response.status !== 409) throw new Error(HTTP_ERROR);
  let data: unknown;
  if (response.ok || checkConstraints) {
    try {
      data = await readBody(response, signal);
    } catch (error) {
      assertCurrent();
      if (isAbortError(error)) throw error;
      if (response.status === 409) throw new ProposalConflict();
      throw new Error(SHAPE_ERROR, { cause: error });
    }
  }
  assertCurrent();
  if (response.status === 409) {
    const rejection = checkConstraints ? parseConstraints(data) : null;
    throw rejection ?? new ProposalConflict();
  }
  return data;
}

function path(id: string, action: string): string {
  return `/api/grocery/proposals/${encodeURIComponent(id)}${action}`;
}

export async function fetchProposal(id: string, signal: AbortSignal): Promise<Proposal> {
  return parseProposal(await request(path(id, ""), "GET", signal));
}

export async function applyProposal(id: string, signal: AbortSignal, planCapCents: number): Promise<AppliedProposal> {
  if (!isSafeInteger(planCapCents) || planCapCents < 0) {
    throw new Error(SHAPE_ERROR);
  }
  const data = await request(path(id, "/apply"), "POST", signal, true, { plan_cap_cents: planCapCents });
  if (!isRecord(data) || !isUuid(data.plan_revision_id)) {
    throw new Error(SHAPE_ERROR);
  }
  return { plan_revision_id: data.plan_revision_id, snapshot: parseSnapshot(data.snapshot) };
}

export async function discardProposal(id: string, signal: AbortSignal): Promise<void> {
  const data = await request(path(id, "/discard"), "POST", signal, false, { confirm: true });
  if (!isRecord(data) || data.status !== "discarded") {
    throw new Error(SHAPE_ERROR);
  }
}
