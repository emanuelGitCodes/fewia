/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import type { ChatJob, ChatJobCreate, ChatResult } from "./chatTypes";
import { useChatJob } from "./useChatJob";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const POLL_MS = 750;
const BUDGET_MS = 8 * 60 * 1000;
const TIMEOUT_ERROR =
  "The chat request is still processing and may continue. Retry checks the same request.";
const CHAT_FAILURE = "The chat request failed. Retry checks the same request.";
const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";
const RAW = "do-not-echo-this";
const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

const body: ChatJobCreate = {
  message: "Plan bean tacos for two.",
  monthly_limit_cents: 20000,
  plan_cap_cents: null,
  previous_job_id: null,
  plan_revision_id: null,
};

const otherBody: ChatJobCreate = {
  ...body,
  message: "Plan lentil soup for four.",
};

const planned: ChatResult = {
  status: "planned",
  answer: "Bean tacos fit the budget.",
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
  budget: {
    available_cents: 5000,
    pending_cents: 200,
    stale: false,
    warnings: [],
  },
  request: {
    meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    budget_period: "2026-09-01",
    plan_cap_cents: null,
    pantry_ingredients: [],
    ingredient_exclusions: [],
    diet: "omnivore",
  },
  meal_nutrition: sampleNutrition(),
  evidence_id: null,
  evidence_revision_id: REVISION,
  spending_source: "fixture",
  tool_trace: [
    {
      tool: "select_meals",
      outcome: "success",
      tool_use_id: "tool-1",
      sequence: 1,
      revision_index: 1,
    },
  ],
  model_turns: 2,
  planner_revisions: 1,
  usage: { inputTokens: 11, outputTokens: 7 },
};

const succeededJob: ChatJob = {
  id: "job-1",
  status: "succeeded",
  result: planned,
  error_code: null,
};

const queuedJob: ChatJob = {
  id: "job-1",
  status: "queued",
  result: null,
  error_code: null,
};

const runningJob: ChatJob = {
  id: "job-1",
  status: "running",
  result: null,
  error_code: null,
};

const failedJob: ChatJob = {
  id: "job-1",
  status: "failed",
  result: null,
  error_code: RAW,
};

const clarificationJob: ChatJob = {
  id: "job-clarify",
  status: "succeeded",
  result: {
    ...planned,
    status: "clarification",
    answer: "Which meals should I plan?",
    plan: null,
    budget: null,
    request: null,
    meal_nutrition: null,
    evidence_id: null,
    evidence_revision_id: null,
  },
  error_code: null,
};

const limitJob: ChatJob = {
  id: "job-limit",
  status: "succeeded",
  result: {
    ...planned,
    status: "limit",
    answer: "The chat reached a turn limit.",
    plan: null,
    budget: null,
    request: null,
    meal_nutrition: null,
    evidence_id: null,
    evidence_revision_id: null,
  },
  error_code: null,
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

async function flushMicrotasks(): Promise<void> {
  await act(async () => {
    for (let i = 0; i < 10; i += 1) {
      await Promise.resolve();
    }
  });
}

describe("useChatJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads a succeeded planned job and does not mutate the caller body", async () => {
    const payload: ChatJobCreate = { ...body };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/grocery/chat/jobs") {
        return jsonOk({ job_id: "job-1", status: "queued" });
      }
      return jsonOk(succeededJob);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

    await act(async () => {
      await result.current.submit(payload);
    });

    expect(payload).toEqual(body);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.job).toEqual(succeededJob);
    expect(result.current.job?.result?.plan?.notice).toBe(NOTICE);
    unmount();
  });

  it("keeps nullable clarification and limit results as completed jobs", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => jsonOk({ job_id: "job-clarify", status: "queued" }))
      .mockImplementationOnce(async () => jsonOk(clarificationJob))
      .mockImplementationOnce(async () => jsonOk({ job_id: "job-limit", status: "queued" }))
      .mockImplementationOnce(async () => jsonOk(limitJob));
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

    await act(async () => {
      await result.current.submit(body);
    });
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.job?.result?.status).toBe("clarification");
    expect(result.current.job?.result?.plan).toBeNull();
    expect(result.current.job?.result?.budget).toBeNull();

    await act(async () => {
      await result.current.submit(otherBody);
    });
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.job?.result?.status).toBe("limit");
    expect(result.current.job?.result?.request).toBeNull();
    unmount();
  });

  it("polls queued and running jobs every 750ms until the job completes", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => jsonOk({ job_id: "job-1", status: "queued" }))
      .mockImplementationOnce(async () => jsonOk(queuedJob))
      .mockImplementationOnce(async () => jsonOk(runningJob))
      .mockImplementationOnce(async () => jsonOk(succeededJob));
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

    let finished: Promise<void> | undefined;
    await act(async () => {
      finished = result.current.submit(body);
    });
    await flushMicrotasks();
    expect(result.current.pending).toBe(true);
    expect(result.current.job?.status).toBe("queued");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    await flushMicrotasks();
    expect(result.current.job?.status).toBe("running");
    expect(result.current.pending).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
      await finished;
    });
    expect(result.current.job).toEqual(succeededJob);
    expect(result.current.pending).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    unmount();
  });

  it("reuses the idempotency key for the same body and issues a new key for a new body", async () => {
    const uuid = vi.spyOn(crypto, "randomUUID");
    uuid
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000002");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/grocery/chat/jobs") {
        return jsonOk({ job_id: "job-1", status: "queued" });
      }
      return jsonOk(succeededJob);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

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

  it("clears job state and starts a new idempotency key after clear", async () => {
    const uuid = vi.spyOn(crypto, "randomUUID");
    uuid
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000003");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/grocery/chat/jobs") {
        return jsonOk({ job_id: "job-1", status: "queued" });
      }
      return jsonOk(succeededJob);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

    await act(async () => {
      await result.current.submit(body);
    });
    act(() => {
      result.current.clear();
    });
    expect(result.current.job).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(false);

    await act(async () => {
      await result.current.submit(body);
    });
    const keys = fetchMock.mock.calls.map(postKey).filter((key) => key !== null);
    expect(keys).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000003",
    ]);
    unmount();
  });

  it("shows a static failure for a known failed job and hides the error code", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/grocery/chat/jobs") {
        return jsonOk({ job_id: "job-1", status: "queued" });
      }
      return jsonOk(failedJob);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

    await act(async () => {
      await result.current.submit(body);
    });
    expect(result.current.job?.status).toBe("failed");
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe(CHAT_FAILURE);
    expect(result.current.error).not.toContain(RAW);
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
      .mockImplementationOnce(async () => jsonOk({ ...succeededJob, id: "job-2" }));
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useChatJob());

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
    const { result, unmount } = renderHook(() => useChatJob());

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

  it("maps a network failure to a static chat error and hides the raw message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(RAW);
      }),
    );
    const { result, unmount } = renderHook(() => useChatJob());

    await act(async () => {
      await result.current.submit(body);
    });
    expect(result.current.pending).toBe(false);
    expect(result.current.job).toBeNull();
    expect(result.current.error).toBe(HTTP_FALLBACK);
    expect(result.current.error).not.toContain(RAW);
    unmount();
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
    const { result, unmount } = renderHook(() => useChatJob());

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
    expect(result.current.error).not.toMatch(/cancel/i);
    unmount();
  });
});
