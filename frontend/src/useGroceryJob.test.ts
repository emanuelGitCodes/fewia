/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GroceryJobCreate } from "./apiTypes";
import { SAMPLE_ESTIMATE_NOTICE } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import { useGroceryJob } from "./useGroceryJob";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const TIMEOUT_ERROR =
  "The grocery request is still processing. Retry checks the same request.";
const BUDGET_MS = 6 * 60 * 1000;

const body: GroceryJobCreate = {
  request: {
    meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    budget_period: "2026-09-01",
    plan_cap_cents: null,
    pantry_ingredients: [],
    ingredient_exclusions: [],
    diet: "omnivore",
  },
  monthly_limit_cents: 20000,
};

const otherBody: GroceryJobCreate = {
  ...body,
  monthly_limit_cents: 10000,
};

const succeededJob = {
  id: "job-1",
  status: "succeeded",
  error_code: null,
  result: {
    spending_source: "fixture",
    budget: {
      available_cents: 5000,
      pending_cents: 0,
      stale: false,
      warnings: [],
    },
    plan: {
      lines: [
        {
          ingredient_id: "black_beans",
          name: "black beans",
          unit: "g",
          quantity: 425,
          packages: 1,
          cost_cents: 129,
          from_pantry: false,
        },
      ],
      total_cents: 129,
      accepted: true,
      warnings: [],
      catalog_version: "sample-prices-v1",
      notice: NOTICE,
    },
    meal_nutrition: sampleNutrition(),
  },
};

function jsonOk(payload: unknown): Response {
  return {
    ok: true,
    json: () => Promise.resolve(payload),
  } as Response;
}

function postKey(call: unknown[]): string | null {
  const init = call[1] as RequestInit | undefined;
  if (init === undefined || init.method !== "POST") {
    return null;
  }
  const headers = init.headers as Record<string, string>;
  return headers["Idempotency-Key"] ?? null;
}

describe("useGroceryJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("reuses the idempotency key for the same body and issues a new key for a new body", async () => {
    const uuid = vi.spyOn(crypto, "randomUUID");
    uuid
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000002");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/grocery/jobs") {
        return jsonOk({ job_id: "job-1", status: "queued" });
      }
      return jsonOk(succeededJob);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useGroceryJob());

    await act(async () => {
      await result.current.submit(body);
    });
    await act(async () => {
      await result.current.submit(body);
    });
    await act(async () => {
      await result.current.submit(otherBody);
    });

    const keys = fetchMock.mock.calls.map(postKey).filter((key) => key !== null);
    expect(keys).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
    ]);
    expect(uuid).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("clears the prior job and error at submit start", async () => {
    const hung = new Promise<Response>(() => undefined);
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => jsonOk({ job_id: "job-1", status: "queued" }))
      .mockImplementationOnce(async () => jsonOk(succeededJob))
      .mockImplementation(() => hung);
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useGroceryJob());

    await act(async () => {
      await result.current.submit(body);
    });
    expect(result.current.job?.id).toBe("job-1");

    let second: Promise<void> | undefined;
    await act(async () => {
      second = result.current.submit(otherBody);
    });
    expect(result.current.job).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(true);
    unmount();
    await act(async () => {
      await second;
    });
  });

  it("times out a hung POST, sets the timeout error, and sets pending false", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        const fail = (): void => {
          reject(new DOMException("Aborted", "AbortError"));
        };
        if (signal === undefined || signal === null) {
          return;
        }
        if (signal.aborted) {
          fail();
          return;
        }
        signal.addEventListener("abort", fail, { once: true });
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useGroceryJob());

    let finished: Promise<void> | undefined;
    await act(async () => {
      finished = result.current.submit(body);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(BUDGET_MS);
      await finished;
    });

    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe(TIMEOUT_ERROR);
    unmount();
  });

  it("ignores a late response from an aborted earlier attempt", async () => {
    let resolveFirst: ((value: Response) => void) | undefined;
    const firstPost = new Promise<Response>((resolve) => {
      resolveFirst = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => firstPost)
      .mockImplementationOnce(async () => jsonOk({ job_id: "job-2", status: "queued" }))
      .mockImplementationOnce(async () =>
        jsonOk({ ...succeededJob, id: "job-2" }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useGroceryJob());

    let firstSubmit: Promise<void> | undefined;
    await act(async () => {
      firstSubmit = result.current.submit(body);
    });
    await act(async () => {
      await result.current.submit(otherBody);
    });
    await act(async () => {
      resolveFirst?.(jsonOk({ job_id: "job-old", status: "queued" }));
      await firstSubmit;
    });

    expect(result.current.job?.id).toBe("job-2");
    unmount();
  });

  it("aborts the in-flight attempt on unmount and ignores a late response", async () => {
    let seenSignal: AbortSignal | undefined;
    let resolvePost: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      seenSignal = init?.signal ?? undefined;
      return new Promise<Response>((resolve) => {
        resolvePost = resolve;
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useGroceryJob());

    let submitResult: Promise<void> | undefined;
    await act(async () => {
      submitResult = result.current.submit(body);
    });
    expect(result.current.pending).toBe(true);

    act(() => {
      unmount();
    });
    expect(seenSignal?.aborted).toBe(true);

    await act(async () => {
      resolvePost?.(jsonOk({ job_id: "job-late", status: "queued" }));
      await submitResult;
    });
  });
});
