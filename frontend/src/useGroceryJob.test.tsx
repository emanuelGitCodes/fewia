/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearTestSession, seedTestSession } from "./testSession";
import type { GroceryJobCreate } from "./apiTypes";
import { useGroceryJob } from "./useGroceryJob";

const body: GroceryJobCreate = {
  request: {
    meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    budget_period: "2026-11-01",
    plan_cap_cents: null,
    pantry_ingredients: [],
    ingredient_exclusions: [],
    diet: "omnivore",
  },
  monthly_limit_cents: 20000,
};
const GUIDANCE = "Untrusted server retry guidance";
const GENERIC = "The grocery request failed. Try again.";

function respond(error_code: string, error_detail: unknown) {
  return vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => ({
    ok: true,
    status: 200,
    json: async () => init?.method === "POST"
      ? { job_id: "job-1", status: "queued" }
      : { id: "job-1", status: "failed", result: null, error_code, error_detail },
  } as Response));
}

describe("useGroceryJob model failures", () => {
  beforeEach(() => {
    seedTestSession();
    vi.useFakeTimers();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    clearTestSession();
  });

  it.each([
    ["model_budget_exhausted", "The daily chat limit has been reached. Try again after the limit resets."],
    ["model_capacity_unavailable", "Chat is busy. Wait a moment, then try again."],
  ])("shows fixed text for %s and waits for a user retry", async (code, message) => {
    const fetchMock = respond(code, { code, retry_guidance: GUIDANCE });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useGroceryJob());
    await act(async () => { await result.current.submit(body); });
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe(message);
    expect(result.current.error).not.toContain(GUIDANCE);
    await act(async () => { await vi.advanceTimersByTimeAsync(12 * 60 * 1000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => { await result.current.submit(body); });
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts).toHaveLength(2);
    const first = new Headers(posts[0][1]?.headers).get("Idempotency-Key");
    const second = new Headers(posts[1][1]?.headers).get("Idempotency-Key");
    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(second).not.toBe(first);
  });

  it.each([
    ["unknown", { code: "model_budget_exhausted", retry_guidance: GUIDANCE }],
    ["model_budget_exhausted", { code: "model_capacity_unavailable", retry_guidance: GUIDANCE }],
    ["model_budget_exhausted", { code: "model_budget_exhausted", retry_guidance: GUIDANCE, forged: true }],
    ["model_budget_exhausted", null],
  ] as const)("keeps malformed or unknown %s failures generic", async (code, detail) => {
    const fetchMock = respond(code, detail);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useGroceryJob());
    await act(async () => { await result.current.submit(body); });
    expect(result.current.job?.status).toBe("failed");
    expect(result.current.error).toBe(GENERIC);
    expect(result.current.error).not.toContain(GUIDANCE);
    await act(async () => { await vi.advanceTimersByTimeAsync(12 * 60 * 1000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries a generic terminal failure with a new key only on user action", async () => {
    const fetchMock = respond("tool", null);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useGroceryJob());
    await act(async () => { await result.current.submit(body); });
    expect(result.current.error).toBe(GENERIC);
    await act(async () => { await vi.advanceTimersByTimeAsync(12 * 60 * 1000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => { await result.current.submit(body); });
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts).toHaveLength(2);
    const first = new Headers(posts[0][1]?.headers).get("Idempotency-Key");
    const second = new Headers(posts[1][1]?.headers).get("Idempotency-Key");
    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(second).not.toBe(first);
  });
});
