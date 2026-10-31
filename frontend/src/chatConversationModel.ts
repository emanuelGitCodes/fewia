import type { ChatJob, ChatJobCreate } from "./chatTypes";

export const MAX_MESSAGE_LENGTH = 4000;
export const MAX_VISIBLE_TURNS = 16;
export const TEXT_ERROR = "Enter a message of 1 to 4000 characters.";
export const BUDGET_ERROR = "Enter a monthly limit and an optional plan cap.";

export type ChatBudget = {
  monthly_limit_cents: number;
  plan_cap_cents: number | null;
};

export function validBudget(budget: ChatBudget | null): budget is ChatBudget {
  if (budget === null) {
    return false;
  }
  const cap = budget.plan_cap_cents;
  return (
    Number.isSafeInteger(budget.monthly_limit_cents) &&
    budget.monthly_limit_cents >= 0 &&
    (cap === null || (Number.isSafeInteger(cap) && cap >= 0))
  );
}

export function copyJobBody(body: ChatJobCreate): ChatJobCreate {
  return {
    message: body.message,
    monthly_limit_cents: body.monthly_limit_cents,
    plan_cap_cents: body.plan_cap_cents,
    previous_job_id: body.previous_job_id,
    plan_revision_id: body.plan_revision_id,
  };
}

export function sameJobBody(left: ChatJobCreate, right: ChatJobCreate): boolean {
  return (
    left.message === right.message &&
    left.monthly_limit_cents === right.monthly_limit_cents &&
    left.plan_cap_cents === right.plan_cap_cents &&
    left.previous_job_id === right.previous_job_id &&
    left.plan_revision_id === right.plan_revision_id
  );
}

export function shouldReplaySavedBody(
  job: ChatJob | null,
  lastBody: ChatJobCreate,
  nextBody: ChatJobCreate,
): boolean {
  if (!sameJobBody(lastBody, nextBody)) {
    return false;
  }
  return job === null || job.status === "queued" || job.status === "running";
}

export function keepLatestTurns<T>(messages: T[]): T[] {
  return messages.length <= MAX_VISIBLE_TURNS ? messages : messages.slice(-MAX_VISIBLE_TURNS);
}

export function beginDispatch(busy: { current: boolean }, generation: { current: number }): number {
  busy.current = true;
  generation.current += 1;
  return generation.current;
}

export function endDispatch(
  busy: { current: boolean },
  generation: { current: number },
  started: number,
): void {
  if (generation.current === started) {
    busy.current = false;
  }
}
