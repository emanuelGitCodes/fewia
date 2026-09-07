/** @vitest-environment node */

import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import { HTTP_ERROR, SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR } from "./apiTypes";
import { fetchChatJob, submitChatJob } from "./chatApi";
import type { ChatJob, ChatJobCreate, ChatResult } from "./chatTypes";

const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
const KEY = "idem-1";
const RAW = "do-not-echo-this";

const body: ChatJobCreate = {
  message: "Plan bean tacos for two.",
  monthly_limit_cents: 20000,
  plan_cap_cents: null,
  previous_job_id: null,
};

const result: ChatResult = {
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
    notice: SAMPLE_ESTIMATE_NOTICE,
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

const queuedJob: ChatJob = {
  id: "job/1?",
  status: "queued",
  result: null,
  error_code: null,
};

const succeededJob: ChatJob = {
  id: "job-1",
  status: "succeeded",
  result,
  error_code: null,
};

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    json: () => Promise.resolve(payload),
  } as Response;
}

type FetchMock = Mock<
  (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
>;

function lastInit(fetchMock: FetchMock): RequestInit {
  const init = fetchMock.mock.calls[0]?.[1];
  if (init === undefined) {
    throw new Error("fetch was not called");
  }
  return init;
}

async function expectStaticError(
  action: () => Promise<unknown>,
  message: string,
): Promise<void> {
  try {
    await action();
    throw new Error("expected a static error");
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(message);
    expect((error as Error).message).not.toContain(RAW);
  }
}

describe("chatApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts JSON and the Idempotency-Key to the chat jobs path", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({ job_id: "job-1", status: "queued" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const ack = await submitChatJob(body, KEY);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/grocery/chat/jobs");
    const init = lastInit(fetchMock);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify(body));
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      "Idempotency-Key": KEY,
    });
    expect(ack).toEqual({ job_id: "job-1", status: "queued" });
  });

  it("gets a chat job from the encoded jobs path", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(queuedJob),
    );
    vi.stubGlobal("fetch", fetchMock);
    const job = await fetchChatJob(queuedJob.id);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/grocery/chat/jobs/${encodeURIComponent(queuedJob.id)}`,
    );
    expect(lastInit(fetchMock).method).toBe("GET");
    expect(job).toEqual(queuedJob);
  });

  it("returns a typed succeeded job from a valid fixture", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(succeededJob)));
    await expect(fetchChatJob(succeededJob.id)).resolves.toEqual(succeededJob);
  });

  it("throws HTTP_ERROR for failed and network fetches and hides raw payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: RAW }, false)),
    );
    await expectStaticError(() => submitChatJob(body, KEY), HTTP_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(RAW);
      }),
    );
    await expectStaticError(() => fetchChatJob("job-1"), HTTP_ERROR);
  });

  it("throws SHAPE_ERROR for invalid JSON and invalid bodies and hides raw text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => Promise.reject(new SyntaxError(RAW)),
      })),
    );
    await expectStaticError(() => submitChatJob(body, KEY), SHAPE_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ id: RAW })));
    await expectStaticError(() => fetchChatJob("job-1"), SHAPE_ERROR);
  });

  it("cancels a hung fetch when the caller signal aborts", async () => {
    let markFetchStart: (() => void) | undefined;
    const fetchStarted = new Promise<void>((resolve) => {
      markFetchStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise(() => {
            if (markFetchStart === undefined) {
              throw new Error("fetch start is not armed");
            }
            markFetchStart();
          }),
      ),
    );
    const controller = new AbortController();
    const pending = fetchChatJob("job-1", controller.signal);
    await fetchStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
