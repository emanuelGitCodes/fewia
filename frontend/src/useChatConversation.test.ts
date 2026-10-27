/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
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
    meal_nutrition: extras ? null : sampleNutrition(),
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

async function sendAndSettle(result: { current: HookValue }): Promise<void> {
  await act(async () => {
    result.current.send();
  });
  await flushMicrotasks();
}

async function retryAndSettle(result: { current: HookValue }): Promise<void> {
  await act(async () => {
    result.current.retry();
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

  function mount(
    currentBudget: ChatBudget | null = budget,
    manualJobId: string | null = null,
  ): {
    result: { current: HookValue };
    refresh: (next?: ChatBudget | null, nextManual?: string | null) => void;
  } {
    let liveBudget = currentBudget;
    let liveManual = manualJobId;
    const { result, rerender } = renderHook(
      (props) => useChatConversation(props.budget, props.manualJobId),
      { initialProps: { budget: liveBudget, manualJobId: liveManual } },
    );
    return {
      result,
      refresh: (
        next: ChatBudget | null | undefined = liveBudget,
        nextManual: string | null | undefined = liveManual,
      ): void => {
        liveBudget = next;
        liveManual = nextManual;
        bindJob();
        rerender({ budget: liveBudget, manualJobId: liveManual });
      },
    };
  }

  afterEach(() => {
    cleanup();
  });

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
    const { result, refresh } = mount(caller);
    act(() => {
      result.current.setMessage("  Plan bean tacos for two.  ");
    });
    await sendAndSettle(result);
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
    expect(result.current.hasRequest).toBe(true);
    expect(result.current.messages).toEqual([
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
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.setMessage("Add lentil soup.");
    });
    await sendAndSettle(result);
    refresh();
    expect(submitted(jobState, 1).previous_job_id).toBe("job-1");
    expect(submitted(jobState, 1).message).toBe("Add lentil soup.");
    expect(result.current.messages.map((item) => item.id)).toEqual(["user-1", "job-1", "user-2", "job-2"]);
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
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan dinner.");
    });
    await sendAndSettle(result);
    refresh();
    expect(result.current.messages[1]).toEqual({
      id: "job-clarify",
      role: "assistant",
      content: "Which meals should I plan?",
    });
    act(() => {
      result.current.setMessage("Bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    expect(submitted(jobState, 1).previous_job_id).toBe("job-clarify");
  });

  it("retries the exact last body without a duplicate user turn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("job-1");
      jobState.error = CHAT_FAILURE;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    expect(result.current.messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
    ]);
    jobState.clear.mockClear();
    await retryAndSettle(result);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(result.current.messages).toHaveLength(1);
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
      jobState.error = null;
    });
    await retryAndSettle(result);
    refresh();
    jobState.clear.mockClear();
    await retryAndSettle(result);
    refresh();
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(submitted(jobState, 3)).toEqual(submitted(jobState, 0));
    expect(result.current.messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
      { id: "job-1", role: "assistant", content: "Bean tacos fit the budget." },
    ]);
  });

  it("starts a new conversation without a parent and clears the retry gate", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.newConversation();
    });
    refresh();
    expect(result.current.messages).toEqual([]);
    expect(result.current.message).toBe("");
    expect(result.current.hasRequest).toBe(false);
    act(() => {
      result.current.setMessage("Plan lentil soup.");
    });
    await sendAndSettle(result);
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
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.setMessage("Plan lentil soup.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe(null);
  });

  it("does not append a stale duplicate succeeded completion", async () => {
    const first = succeeded("job-1", "Bean tacos fit the budget.");
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = first;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    refresh();
    expect(result.current.messages.filter((item) => item.role === "assistant")).toHaveLength(1);
  });

  it("rejects invalid budget and text without submitting", async () => {
    const { result, refresh } = mount(null);
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    expect(result.current.error).toBe(BUDGET_ERROR);
    expect(jobState.submit).not.toHaveBeenCalled();
    refresh({ monthly_limit_cents: 1.5, plan_cap_cents: null });
    await sendAndSettle(result);
    expect(result.current.error).toBe(BUDGET_ERROR);
    refresh(budget);
    act(() => {
      result.current.setMessage("   ");
    });
    await sendAndSettle(result);
    expect(result.current.error).toBe(TEXT_ERROR);
    act(() => {
      result.current.setMessage("a".repeat(4001));
    });
    await sendAndSettle(result);
    expect(result.current.error).toBe(TEXT_ERROR);
    expect(jobState.submit).not.toHaveBeenCalled();
    expect(result.current.hasRequest).toBe(false);
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
    const { result, refresh } = mount(caller);
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    jobState.pending = true;
    refresh();
    await sendAndSettle(result);
    await retryAndSettle(result);
    expect(jobState.submit).not.toHaveBeenCalled();
    jobState.pending = false;
    refresh();
    await sendAndSettle(result);
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
    await retryAndSettle(result);
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
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan dinner.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.setMessage("Retry with tacos.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe("job-limit");
    for (let index = 0; index < 7; index += 1) {
      act(() => {
        result.current.setMessage(`Turn ${index}`);
      });
      await sendAndSettle(result);
      refresh();
    }
    refresh();
    expect(result.current.messages).toHaveLength(16);
    expect(result.current.messages[0]?.id).not.toBe("user-1");
  });

  it("replays the saved body after a timeout without a new turn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = null;
      jobState.error = TIMEOUT;
      jobState.pending = false;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(result);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(result.current.messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
    ]);
  });

  it("replays the saved body after an HTTP fallback without a new turn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = null;
      jobState.error = HTTP_FALLBACK;
      jobState.pending = false;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(result);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(result.current.messages.map((item) => item.id)).toEqual(["user-1"]);
  });

  it("replays the saved body for queued and running jobs", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = openJob("job-1", "queued");
      jobState.pending = false;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(result);
    jobState.job = openJob("job-1", "running");
    refresh();
    await sendAndSettle(result);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(3);
    expect(result.current.messages).toHaveLength(1);
  });

  it("sends a fresh intent after a failed job", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("job-fail");
      jobState.error = CHAT_FAILURE;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(result);
    expect(jobState.clear).toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(result.current.messages.map((item) => item.id)).toEqual(["user-1", "user-2"]);
  });

  it("sends a fresh followup after a succeeded job", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    jobState.clear.mockClear();
    await sendAndSettle(result);
    expect(jobState.clear).toHaveBeenCalled();
    expect(submitted(jobState, 1).previous_job_id).toBe("job-1");
    expect(result.current.messages.map((item) => item.id)).toEqual(["user-1", "job-1", "user-2"]);
  });

  it("clears a local validation error on retry and submits the saved body", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("job-1");
      jobState.error = CHAT_FAILURE;
    });
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.setMessage("   ");
    });
    await sendAndSettle(result);
    expect(result.current.error).toBe(TEXT_ERROR);
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("job-1", "Bean tacos fit the budget.");
      jobState.error = null;
    });
    jobState.clear.mockClear();
    await retryAndSettle(result);
    refresh();
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(result.current.error).toBe(null);
    expect(result.current.messages).toEqual([
      { id: "user-1", role: "user", content: "Plan bean tacos for two." },
      { id: "job-1", role: "assistant", content: "Bean tacos fit the budget." },
    ]);
  });

  it("fences two send calls in one act", () => {
    const { result } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    act(() => {
      result.current.send();
      result.current.send();
    });
    expect(jobState.submit).toHaveBeenCalledTimes(1);
    expect(result.current.messages).toEqual([
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
    const { result, refresh } = mount();
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    act(() => {
      result.current.send();
    });
    act(() => {
      result.current.newConversation();
    });
    refresh();
    act(() => {
      result.current.setMessage("Plan lentil soup.");
    });
    act(() => {
      result.current.send();
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    await act(async () => {
      resolvers[0]?.();
    });
    await flushMicrotasks();
    act(() => {
      result.current.send();
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(result.current.messages).toEqual([
      { id: "user-1", role: "user", content: "Plan lentil soup." },
    ]);
    await act(async () => {
      resolvers[1]?.();
      await Promise.resolve();
    });
    await flushMicrotasks();
    await sendAndSettle(result);
    expect(jobState.submit).toHaveBeenCalledTimes(3);
  });

  it("uses a one-argument call with no parent", async () => {
    const { result } = renderHook(() => useChatConversation(budget));
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 0).previous_job_id).toBe(null);
  });

  it("composes the request message and keeps the typed text in the user turn", async () => {
    const { result } = renderHook(() =>
      useChatConversation(budget, null, { composeMessage: (text) => `PLAN. ${text}` }),
    );
    act(() => {
      result.current.setMessage("  Add tofu.  ");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 0)).toEqual({
      message: "PLAN. Add tofu.",
      monthly_limit_cents: 20000,
      plan_cap_cents: null,
      previous_job_id: null,
    });
    expect(result.current.messages).toEqual([{ id: "user-1", role: "user", content: "Add tofu." }]);
  });

  it("rejects a composed message over the limit without submitting", async () => {
    const { result } = renderHook(() =>
      useChatConversation(budget, null, {
        composeMessage: (text) => `${"x".repeat(3990)}${text}`,
      }),
    );
    act(() => {
      result.current.setMessage("a".repeat(20));
    });
    await sendAndSettle(result);
    expect(result.current.error).toBe(TEXT_ERROR);
    expect(jobState.submit).not.toHaveBeenCalled();
    expect(result.current.messages).toEqual([]);
    expect(result.current.hasRequest).toBe(false);
  });

  it("sends the first request with a saved manual job as parent", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("chat-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved pantry and four servings.");
    });
    await sendAndSettle(result);
    refresh();
    expect(submitted(jobState, 0).previous_job_id).toBe("manual-1");
    expect(submitted(jobState, 0).message).toBe("Use the saved pantry and four servings.");
  });

  it("uses the chat job as the followup parent after a succeeded reply", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("chat-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.setMessage("Add lentil soup.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe("chat-1");
  });

  it("lets a newer manual job supersede the chat parent on the next send", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("chat-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    await sendAndSettle(result);
    refresh();
    refresh(budget, "manual-2");
    act(() => {
      result.current.setMessage("Use the rebuilt plan.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe("manual-2");
  });

  it("retries the frozen parent after a newer manual job arrives", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = failed("chat-fail");
      jobState.error = CHAT_FAILURE;
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    await sendAndSettle(result);
    refresh();
    refresh(budget, "manual-2");
    await retryAndSettle(result);
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(submitted(jobState, 1).previous_job_id).toBe("manual-1");
  });

  it("replays a queued body with the frozen parent after context change", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = openJob("chat-1", "queued");
      jobState.pending = false;
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    await sendAndSettle(result);
    refresh();
    refresh(budget, "manual-2");
    jobState.clear.mockClear();
    await sendAndSettle(result);
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(submitted(jobState, 1)).toEqual(submitted(jobState, 0));
    expect(submitted(jobState, 1).previous_job_id).toBe("manual-1");
  });

  it("seeds the current manual job after a new conversation", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("chat-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    await sendAndSettle(result);
    refresh();
    act(() => {
      result.current.newConversation();
    });
    refresh();
    act(() => {
      result.current.setMessage("Start from the saved plan.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe("manual-1");
  });

  it("does not adopt a late chat parent after a newer manual job", async () => {
    const resolvers: Array<() => void> = [];
    jobState.submit.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolvers.push(resolve);
        }),
    );
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    act(() => {
      result.current.send();
    });
    refresh(budget, "manual-2");
    jobState.job = succeeded("chat-late", "Bean tacos fit the budget.");
    await act(async () => {
      resolvers[0]?.();
    });
    await flushMicrotasks();
    refresh();
    act(() => {
      result.current.setMessage("Use the rebuilt plan.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe("manual-2");
  });

  it("does not resurrect a chat parent after manual context is withdrawn", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = succeeded("chat-1", "Bean tacos fit the budget.");
    });
    const { result, refresh } = mount(budget, "manual-1");
    act(() => {
      result.current.setMessage("Use the saved plan.");
    });
    await sendAndSettle(result);
    refresh();
    refresh(budget, null);
    act(() => {
      result.current.setMessage("Plan lentil soup.");
    });
    await sendAndSettle(result);
    expect(submitted(jobState, 1).previous_job_id).toBe(null);
  });

  it("keeps budget validation when a manual parent is present", async () => {
    const { result } = mount(null, "manual-1");
    act(() => {
      result.current.setMessage("Plan bean tacos for two.");
    });
    await sendAndSettle(result);
    expect(result.current.error).toBe(BUDGET_ERROR);
    expect(jobState.submit).not.toHaveBeenCalled();
  });
});
