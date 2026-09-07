/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import type { ChatJob, ChatJobCreate } from "./chatTypes";
import {
  BUDGET_ERROR,
  MAX_VISIBLE_TURNS,
  beginDispatch,
  copyJobBody,
  endDispatch,
  keepLatestTurns,
  sameJobBody,
  shouldReplaySavedBody,
  validBudget,
} from "./chatConversationModel";

const body: ChatJobCreate = {
  message: "Plan bean tacos for two.",
  monthly_limit_cents: 20000,
  plan_cap_cents: null,
  previous_job_id: null,
};

function job(status: ChatJob["status"]): ChatJob {
  return { id: "job-1", status, result: null, error_code: null };
}

describe("chatConversationModel", () => {
  it("copies the four wire fields and does not mutate the source", () => {
    const source = { ...body, extra: "drop" } as ChatJobCreate & { extra: string };
    const copied = copyJobBody(source);
    source.message = "mutated";
    source.monthly_limit_cents = 1;
    source.plan_cap_cents = 2;
    source.previous_job_id = "job-1";
    expect(copied).toEqual(body);
    expect(Object.keys(copied).sort()).toEqual([
      "message",
      "monthly_limit_cents",
      "plan_cap_cents",
      "previous_job_id",
    ]);
  });

  it("compares the four wire fields only", () => {
    expect(sameJobBody(body, copyJobBody(body))).toBe(true);
    expect(sameJobBody(body, { ...body, message: "Plan lentil soup." })).toBe(false);
    expect(sameJobBody(body, { ...body, monthly_limit_cents: 1 })).toBe(false);
    expect(sameJobBody(body, { ...body, plan_cap_cents: 4000 })).toBe(false);
    expect(sameJobBody(body, { ...body, previous_job_id: "job-1" })).toBe(false);
  });

  it("replays the saved body for null, queued, and running jobs", () => {
    const next = copyJobBody(body);
    expect(shouldReplaySavedBody(null, body, next)).toBe(true);
    expect(shouldReplaySavedBody(job("queued"), body, next)).toBe(true);
    expect(shouldReplaySavedBody(job("running"), body, next)).toBe(true);
    expect(shouldReplaySavedBody(job("succeeded"), body, next)).toBe(false);
    expect(shouldReplaySavedBody(job("failed"), body, next)).toBe(false);
    expect(shouldReplaySavedBody(null, body, { ...body, message: "other" })).toBe(false);
  });

  it("accepts a monthly limit with an optional plan cap", () => {
    expect(validBudget(null)).toBe(false);
    expect(validBudget({ monthly_limit_cents: 1.5, plan_cap_cents: null })).toBe(false);
    expect(validBudget({ monthly_limit_cents: 20000, plan_cap_cents: -1 })).toBe(false);
    expect(validBudget({ monthly_limit_cents: 20000, plan_cap_cents: null })).toBe(true);
    expect(validBudget({ monthly_limit_cents: 20000, plan_cap_cents: 4000 })).toBe(true);
    expect(BUDGET_ERROR).toContain("monthly limit");
    expect(BUDGET_ERROR).toContain("plan cap");
  });

  it("keeps the latest visible turns", () => {
    const items = Array.from({ length: MAX_VISIBLE_TURNS + 2 }, (_, index) => index);
    expect(keepLatestTurns([0, 1])).toEqual([0, 1]);
    expect(keepLatestTurns(items)).toEqual(items.slice(2));
  });

  it("starts a dispatch generation and only the matching generation releases the fence", () => {
    const busy = { current: false };
    const generation = { current: 0 };
    const first = beginDispatch(busy, generation);
    expect(first).toBe(1);
    expect(busy.current).toBe(true);
    expect(generation.current).toBe(1);
    const second = beginDispatch(busy, generation);
    expect(second).toBe(2);
    endDispatch(busy, generation, first);
    expect(busy.current).toBe(true);
    endDispatch(busy, generation, second);
    expect(busy.current).toBe(false);
  });

  it("keeps a newer fence after generation advances without beginDispatch", () => {
    const busy = { current: false };
    const generation = { current: 0 };
    const started = beginDispatch(busy, generation);
    generation.current += 1;
    busy.current = false;
    const next = beginDispatch(busy, generation);
    endDispatch(busy, generation, started);
    expect(busy.current).toBe(true);
    expect(generation.current).toBe(next);
    endDispatch(busy, generation, next);
    expect(busy.current).toBe(false);
  });
});
