/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestRenderer } from "react-test-renderer";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "./apiTypes";
import type { ChatJob, ChatJobCreate, ChatResult } from "./chatTypes";
import {
  BUDGET_ERROR,
  TEXT_ERROR,
  useChatConversation,
  type ChatBudget,
} from "./useChatConversation";
import { useChatJob } from "./useChatJob";

vi.mock("./useChatJob", () => ({
  useChatJob: vi.fn(),
}));

const CHAT_FAILURE = "The chat request failed. Retry checks the same request.";
const TIMEOUT =
  "The chat request is still processing and may continue. Retry checks the same request.";
const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";

type HookValue = ReturnType<typeof useChatConversation>;

type JobMocks = {
  job: ChatJob | null;
  error: string | null;
  pending: boolean;
  submit: ReturnType<typeof vi.fn<(body: ChatJobCreate) => Promise<void>>>;
  clear: ReturnType<typeof vi.fn<() => void>>;
};

const budget: ChatBudget = { monthly_limit_cents: 20000, plan_cap_cents: null };

function resultOf(status: ChatResult["status"], answer: string): ChatResult {
  const extras = status === "clarification" || status === "limit" || status === "incomplete";
  return {
    status,
    answer,
    plan: extras
      ? null
      : {
          lines: [],
          total_cents: 0,
          accepted: status === "planned",
          warnings: [],
          catalog_version: "sample-prices-v1",
          notice: SAMPLE_ESTIMATE_NOTICE,
        },
    budget: extras ? null : { available_cents: 5000, pending_cents: 0, stale: false, warnings: [] },
    request: extras
      ? null
      : {
          meals: [{ recipe_id: "bean_tacos", servings: 2 }],
          budget_period: "2026-09-01",
          plan_cap_cents: null,
          pantry_ingredients: [],
          ingredient_exclusions: [],
          diet: "omnivore",
        },
    evidence_id: null,
    evidence_revision_id: extras ? null : "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 1,
    planner_revisions: 0,
    usage: null,
  };
}

function succeeded(id: string, answer: string, status: ChatResult["status"] = "planned"): ChatJob {
  return { id, status: "succeeded", result: resultOf(status, answer), error_code: null };
}

function failed(id: string): ChatJob {
  return { id, status: "failed", result: null, error_code: "tool" };
}

function openJob(id: string, status: "queued" | "running"): ChatJob {
  return { id, status, result: null, error_code: null };
}

function HookHost(props: { bucket: { current: HookValue | null }; budget: ChatBudget | null }): null {
  props.bucket.current = useChatConversation(props.budget);
  return null;
}

function hookOf(bucket: { current: HookValue | null }): HookValue {
  if (bucket.current === null) {
    throw new Error("hook is not mounted");
  }
  return bucket.current;
}

function submitted(mocks: JobMocks, index: number): ChatJobCreate {
  const body = mocks.submit.mock.calls[index]?.[0];
  if (body === undefined) {
    throw new Error("missing submit body");
  }
  return body;
}

async function flushMicrotasks(): Promise<void> {
  await act(async () => {
    for (let i = 0; i < 10; i += 1) {
      await Promise.resolve();
    }
  });
}

async function sendAndSettle(bucket: { current: HookValue | null }): Promise<void> {
  await act(async () => {
    hookOf(bucket).send();
  });
  await flushMicrotasks();
}

async function retryAndSettle(bucket: { current: HookValue | null }): Promise<void> {
  await act(async () => {
    hookOf(bucket).retry();
  });
  await flushMicrotasks();
}

describe("useChatConversation", () => {
  let jobState: JobMocks;

  function bindJob(): void {
    vi.mocked(useChatJob).mockImplementation(() => ({
      job: jobState.job,
      error: jobState.error,
      pending: jobState.pending,
      submit: jobState.submit,
      clear: jobState.clear,
    }));
  }

  function mount(currentBudget: ChatBudget | null = budget): {
    bucket: { current: HookValue | null };
    renderer: ReactTestRenderer;
    refresh: (next?: ChatBudget | null) => void;
  } {
    const bucket: { current: HookValue | null } = { current: null };
    let liveBudget = currentBudget;
    let renderer: ReactTestRenderer | undefined;
    act(() => {
      renderer = create(createElement(HookHost, { bucket, budget: liveBudget }));
    });
    if (renderer === undefined) {
      throw new Error("renderer failed to mount");
    }
    const live = renderer;
    return {
      bucket,
      renderer: live,
      refresh: (next: ChatBudget | null | undefined = liveBudget): void => {
        liveBudget = next;
        bindJob();
        act(() => {
          live.update(createElement(HookHost, { bucket, budget: liveBudget }));
        });
      },
    };
  }

  beforeEach(() => {
    jobState = {
      job: null,
      error: null,
      pending: false,
      submit: vi.fn(async (_body: ChatJobCreate) => undefined),
      clear: vi.fn((): void => {
        jobState.job = null;
        jobState.error = null;
        jobState.pending = false;
      }),
    };
    bindJob();
  });

  it("sends the first request without a parent and appends the answer once", async () => {
    const caller = { ...budget };
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    });
    const { bucket, refresh } = mount(caller);
    act(() => {
      hookOf(bucket).setMessage("  Plan bean tacos for two.  ");
    });
    await sendAndSettle(bucket);
    refresh();
    const body = submitted(jobState, 0);
    expect(body).toEqual({
      message: "Plan bean tacos for two.",
      monthly_limit_cents: 20000,
      plan_cap_cents: null,
      previous_job_id: null,
    });
    expect(Object.keys(body).sort()).toEqual([
      "message",
      "monthly_limit_cents",
      "plan_cap_cents",
      "previous_job_id",
    ]);
    expect(hookOf(bucket).hasRequest).toBe(true);
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
      { id: "job-1", role: "assistant", content: "Bean tacos fit the budget." },
    ]);
    expect(caller).toEqual(budget);
  });

  it("sends a followup with the last succeeded job as parent", async () => {
    let count = 0;
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      count += 1;
      jobState.job = succeeded(`job-${count}`, `answer ${count}`);
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).setMessage("Add lentil soup.");
    });
    await sendAndSettle(bucket);
    refresh();
    expect(submitted(jobState, 1).previous_job_id).toBe("job-1");
    expect(submitted(jobState, 1).message).toBe("Add lentil soup.");
    expect(hookOf(bucket).messages.map((item) => item.id)).toEqual(["user-1", "job-1", "user-2", "job-2"]);
  });

  it("tracks a clarification parent and appends a nullable clarification answer", async () => {
    let count = 0;
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      count += 1;
      jobState.job =
        count === 1
          ? succeeded("job-clarify", "Which meals should I plan?", "clarification")
          : succeeded("job-2", "Bean tacos fit the budget.");
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan dinner.");
    });
    await sendAndSettle(bucket);
    refresh();
    expect(hookOf(bucket).messages[1]).toEqual({
      id: "job-clarify",
      role: "assistant",
      content: "Which meals should I plan?",
    });
    act(() => {
      hookOf(bucket).setMessage("Bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    expect(submitted(jobState, 1).previous_job_id).toBe("job-clarify");
  });

  it("retries the exact last body without a duplicate user turn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("job-1");
      jobState.error = CHAT_FAILURE;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
    ]);
    jobState.clear.mockClear();
    await retryAndSettle(bucket);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(hookOf(bucket).messages).toHaveLength(1);
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
      jobState.error = null;
    });
    await retryAndSettle(bucket);
    refresh();
    jobState.clear.mockClear();
    await retryAndSettle(bucket);
    refresh();
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(submitted(jobState, 3)).toEqual(submitted(jobState, 0));
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
      { id: "job-1", role: "assistant", content: "Bean tacos fit the budget." },
    ]);
  });

  it("starts a new conversation without a parent and clears the retry gate", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).newConversation();
    });
    refresh();
    expect(hookOf(bucket).messages).toEqual([]);
    expect(hookOf(bucket).message).toBe("");
    expect(hookOf(bucket).hasRequest).toBe(false);
    act(() => {
      hookOf(bucket).setMessage("Plan lentil soup.");
    });
    await sendAndSettle(bucket);
    expect(submitted(jobState, 1).previous_job_id).toBe(null);
    expect(submitted(jobState, 1).message).toBe("Plan lentil soup.");
  });

  it("does not use a failed job as the followup parent", async () => {
    let count = 0;
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      count += 1;
      if (count === 1) {
        jobState.job = failed("job-fail");
        jobState.error = CHAT_FAILURE;
        return;
      }
      jobState.job = succeeded("job-2", "Bean tacos fit the budget.");
      jobState.error = null;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).setMessage("Plan lentil soup.");
    });
    await sendAndSettle(bucket);
    expect(submitted(jobState, 1).previous_job_id).toBe(null);
  });

  it("does not append a stale duplicate succeeded completion", async () => {
    const first = succeeded("job-1", "Bean tacos fit the budget.");
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = first;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    refresh();
    expect(hookOf(bucket).messages.filter((item) => item.role === "assistant")).toHaveLength(1);
  });

  it("rejects invalid budget and text without submitting", async () => {
    const { bucket, refresh } = mount(null);
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    expect(hookOf(bucket).error).toBe(BUDGET_ERROR);
    expect(jobState.submit).not.toHaveBeenCalled();
    refresh({ monthly_limit_cents: 1.5, plan_cap_cents: null });
    await sendAndSettle(bucket);
    expect(hookOf(bucket).error).toBe(BUDGET_ERROR);
    refresh(budget);
    act(() => {
      hookOf(bucket).setMessage("   ");
    });
    await sendAndSettle(bucket);
    expect(hookOf(bucket).error).toBe(TEXT_ERROR);
    act(() => {
      hookOf(bucket).setMessage("a".repeat(4001));
    });
    await sendAndSettle(bucket);
    expect(hookOf(bucket).error).toBe(TEXT_ERROR);
    expect(jobState.submit).not.toHaveBeenCalled();
    expect(hookOf(bucket).hasRequest).toBe(false);
  });

  it("does not mutate caller budget or job results and suppresses pending sends", async () => {
    const caller: ChatBudget = { monthly_limit_cents: 20000, plan_cap_cents: 4000 };
    const planned = resultOf("planned", "Bean tacos fit the budget.");
    const snapshot = structuredClone(planned);
    const originalBody: ChatJobCreate = {
      message: "Plan bean tacos for two.",
      monthly_limit_cents: 20000,
      plan_cap_cents: 4000,
      previous_job_id: null,
    };
    const received: ChatJobCreate[] = [];
    jobState.submit.mockImplementation(async (body: ChatJobCreate) => {
      received.push({ ...body });
      body.message = "mutated";
      body.previous_job_id = "tampered";
      jobState.job = { id: "job-1", status: "succeeded", result: planned, error_code: null };
    });
    const { bucket, refresh } = mount(caller);
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    jobState.pending = true;
    refresh();
    await sendAndSettle(bucket);
    await retryAndSettle(bucket);
    expect(jobState.submit).not.toHaveBeenCalled();
    jobState.pending = false;
    refresh();
    await sendAndSettle(bucket);
    refresh();
    expect(caller).toEqual({ monthly_limit_cents: 20000, plan_cap_cents: 4000 });
    expect(planned).toEqual(snapshot);
    expect(submitted(jobState, 0).plan_cap_cents).toBe(4000);
    expect(received[0]).toEqual(originalBody);
    expect(submitted(jobState, 0)).toEqual({
      message: "mutated",
      monthly_limit_cents: 20000,
      plan_cap_cents: 4000,
      previous_job_id: "tampered",
    });
    await retryAndSettle(bucket);
    expect(received[1]).toEqual(originalBody);
    expect(submitted(jobState, 1)).toEqual({
      message: "mutated",
      monthly_limit_cents: 20000,
      plan_cap_cents: 4000,
      previous_job_id: "tampered",
    });
  });

  it("keeps a limit outcome as parent and trims visible history to 16", async () => {
    let count = 0;
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      count += 1;
      jobState.job =
        count === 1
          ? succeeded("job-limit", "The chat reached a turn limit.", "limit")
          : succeeded(`job-${count}`, `answer ${count}`);
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan dinner.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).setMessage("Retry with tacos.");
    });
    await sendAndSettle(bucket);
    expect(submitted(jobState, 1).previous_job_id).toBe("job-limit");
    for (let index = 0; index < 7; index += 1) {
      act(() => {
        hookOf(bucket).setMessage(`Turn ${index}`);
      });
      await sendAndSettle(bucket);
      refresh();
    }
    refresh();
    expect(hookOf(bucket).messages).toHaveLength(16);
    expect(hookOf(bucket).messages[0]?.id).not.toBe("user-1");
  });

  it("replays the saved body after a timeout without a new turn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = null;
      jobState.error = TIMEOUT;
      jobState.pending = false;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(bucket);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
    ]);
  });

  it("replays the saved body after an HTTP fallback without a new turn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = null;
      jobState.error = HTTP_FALLBACK;
      jobState.pending = false;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(bucket);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(hookOf(bucket).messages.map((item) => item.id)).toEqual(["user-1"]);
  });

  it("replays the saved body for queued and running jobs", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = openJob("job-1", "queued");
      jobState.pending = false;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(bucket);
    jobState.job = openJob("job-1", "running");
    refresh();
    await sendAndSettle(bucket);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(3);
    expect(hookOf(bucket).messages).toHaveLength(1);
  });

  it("sends a fresh intent after a failed job", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("job-fail");
      jobState.error = CHAT_FAILURE;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(bucket);
    expect(jobState.clear).toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(hookOf(bucket).messages.map((item) => item.id)).toEqual(["user-1", "user-2"]);
  });

  it("sends a fresh followup after a succeeded job", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(bucket);
    expect(jobState.clear).toHaveBeenCalled();
    expect(submitted(jobState, 1).previous_job_id).toBe("job-1");
    expect(hookOf(bucket).messages.map((item) => item.id)).toEqual(["user-1", "job-1", "user-2"]);
  });

  it("clears a local validation error on retry and submits the saved body", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("job-1");
      jobState.error = CHAT_FAILURE;
    });
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).setMessage("   ");
    });
    await sendAndSettle(bucket);
    expect(hookOf(bucket).error).toBe(TEXT_ERROR);
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
      jobState.error = null;
    });
    jobState.clear.mockClear();
    await retryAndSettle(bucket);
    refresh();
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(hookOf(bucket).error).toBe(null);
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
      { id: "job-1", role: "assistant", content: "Bean tacos fit the budget." },
    ]);
  });

  it("fences two send calls in one act", () => {
    const { bucket } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    act(() => {
      hookOf(bucket).send();
      hookOf(bucket).send();
    });
    expect(jobState.submit).toHaveBeenCalledTimes(1);
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
    ]);
  });

  it("does not let a late completion release a newer dispatch guard", async () => {
    const resolvers: Array<() => void> = [];
    jobState.submit.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolvers.push(resolve);
        }),
    );
    const { bucket, refresh } = mount();
    act(() => {
      hookOf(bucket).setMessage("Plan bean tacos for two.");
    });
    act(() => {
      hookOf(bucket).send();
    });
    act(() => {
      hookOf(bucket).newConversation();
    });
    refresh();
    act(() => {
      hookOf(bucket).setMessage("Plan lentil soup.");
    });
    act(() => {
      hookOf(bucket).send();
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    await act(async () => {
      resolvers[0]?.();
    });
    await flushMicrotasks();
    act(() => {
      hookOf(bucket).send();
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(hookOf(bucket).messages).toEqual([
      { id: "user-1", role: "user", content: "Plan lentil soup." },
    ]);
    await act(async () => {
      resolvers[1]?.();
      await Promise.resolve();
    });
    await flushMicrotasks();
    await sendAndSettle(bucket);
    expect(jobState.submit).toHaveBeenCalledTimes(3);
  });
});

