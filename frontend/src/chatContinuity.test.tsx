/** @vitest-environment node */

import { createElement, useState } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryJob } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import { initialForm, type FormState } from "./BudgetForm";
import { ChatWorkspace, REBUILD_CHAT_GUIDANCE, useChatWorkspace } from "./ChatWorkspace";
import type { ChatJob, ChatJobCreate, ChatResult } from "./chatTypes";
import { useChatJob } from "./useChatJob";
import { useProviderCapabilities } from "./useProviderCapabilities";

vi.mock("./useChatJob", () => ({
  useChatJob: vi.fn(),
}));

vi.mock("./useProviderCapabilities", () => ({
  useProviderCapabilities: vi.fn(),
}));

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

type JobMocks = {
  job: ChatJob | null;
  error: string | null;
  pending: boolean;
  submit: ReturnType<typeof vi.fn<(body: ChatJobCreate) => Promise<void>>>;
  clear: ReturnType<typeof vi.fn<() => void>>;
};

type Bucket = {
  form: FormState;
  setForm: (value: FormState) => void;
  chat: ReturnType<typeof useChatWorkspace>;
};

function plannedResult(): ChatResult {
  return {
    status: "planned",
    answer: "Bean tacos fit the budget.",
    plan: {
      lines: [],
      total_cents: 1703,
      accepted: true,
      warnings: ["Plan warning"],
      catalog_version: "sample-prices-v1",
      notice: NOTICE,
    },
    budget: { available_cents: 5000, pending_cents: 0, stale: false, warnings: [] },
    request: {
      meals: [{ recipe_id: "lentil_soup", servings: 4 }],
      budget_period: "2026-09-01",
      plan_cap_cents: 5000,
      pantry_ingredients: ["black_beans"],
      ingredient_exclusions: [],
      diet: "vegetarian",
    },
    meal_nutrition: sampleNutrition(),
    evidence_id: null,
    evidence_revision_id: REVISION,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 2,
    planner_revisions: 1,
    usage: null,
  };
}

function chatJob(id = "chat-1"): ChatJob {
  return { id, status: "succeeded", result: plannedResult(), error_code: null };
}

function formJob(id = "form-1"): GroceryJob {
  return {
    id,
    status: "succeeded",
    error_code: null,
    result: {
      spending_source: "fixture",
      budget: { available_cents: 5000, pending_cents: 0, stale: false, warnings: [] },
      meal_nutrition: sampleNutrition(),
      plan: {
        lines: [],
        total_cents: 100,
        accepted: true,
        warnings: [],
        catalog_version: "sample-prices-v1",
        notice: NOTICE,
      },
    },
  };
}

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) {
    throw new Error(`missing button ${name}`);
  }
  return match;
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

describe("chat continuity", () => {
  let jobState: JobMocks;

  function bindJob(): void {
    vi.mocked(useChatJob).mockImplementation(() => ({
      job: jobState.job,
      error: jobState.error,
      pending: jobState.pending,
      submit: jobState.submit,
      clear: jobState.clear,
    }));
    vi.mocked(useProviderCapabilities).mockImplementation(() => ({
      capabilities: {
        chat_configured: true,
        plaid_configured: false,
        instacart_configured: false,
        spending_source: "fixture",
      },
      pending: false,
      error: null,
      retry: vi.fn(),
    }));
  }

  function HookHost(props: {
    bucket: { current: Bucket | null };
    formJob: GroceryJob | null;
    formDirty: boolean;
    start?: FormState;
  }): JSX.Element {
    const [form, setForm] = useState(props.start ?? initialForm());
    const chat = useChatWorkspace({
      form,
      setForm,
      formJob: props.formJob,
      formDirty: props.formDirty,
    });
    props.bucket.current = { form, setForm, chat };
    return createElement(ChatWorkspace, {
      formPending: false,
      configured: chat.configured,
      configurationPending: chat.configurationPending,
      providerError: chat.providerError,
      retryProviders: chat.retryProviders,
      conversation: chat.conversation,
      freshSendBlocked: chat.needsRebuild,
    });
  }

  function mount(options: { formJob?: GroceryJob | null; formDirty?: boolean; start?: FormState } = {}): {
    bucket: { current: Bucket | null };
    renderer: ReactTestRenderer;
    refresh: (next?: { formJob?: GroceryJob | null; formDirty?: boolean }) => void;
  } {
    bindJob();
    const bucket: { current: Bucket | null } = { current: null };
    let liveJob = options.formJob ?? null;
    let liveDirty = options.formDirty ?? false;
    let renderer: ReactTestRenderer | undefined;
    act(() => {
      renderer = create(
        createElement(HookHost, {
          bucket,
          formJob: liveJob,
          formDirty: liveDirty,
          start: options.start,
        }),
      );
    });
    if (renderer === undefined) {
      throw new Error("renderer failed to mount");
    }
    const live = renderer;
    return {
      bucket,
      renderer: live,
      refresh: (next: { formJob?: GroceryJob | null; formDirty?: boolean } = {}): void => {
        liveJob = next.formJob === undefined ? liveJob : next.formJob;
        liveDirty = next.formDirty ?? liveDirty;
        bindJob();
        act(() => {
          live.update(
            createElement(HookHost, {
              bucket,
              formJob: liveJob,
              formDirty: liveDirty,
              start: options.start,
            }),
          );
        });
      },
    };
  }

  function hookOf(bucket: { current: Bucket | null }): Bucket {
    if (bucket.current === null) {
      throw new Error("workspace is not mounted");
    }
    return bucket.current;
  }

  async function sendAndSettle(bucket: { current: Bucket | null }): Promise<void> {
    await act(async () => {
      hookOf(bucket).chat.conversation.send();
    });
    await flushMicrotasks();
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

  it("keeps the accepted chat plan as the next parent after reset", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = chatJob();
    });
    const { bucket, refresh } = mount({ formJob: formJob() });
    act(() => {
      hookOf(bucket).chat.conversation.setMessage("Plan lentil soup.");
    });
    await sendAndSettle(bucket);
    refresh();
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    act(() => {
      hookOf(bucket).chat.conversation.newConversation();
    });
    refresh();
    act(() => {
      hookOf(bucket).chat.conversation.setMessage("Use the same pantry.");
    });
    await sendAndSettle(bucket);
    expect(submitted(jobState, 1).previous_job_id).toBe("chat-1");
    expect(submitted(jobState, 1).previous_job_id).not.toBe("form-1");
  });

  it("blocks a contextless send after a failed rebuild of a dirty pantry", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = chatJob();
    });
    const { bucket, refresh, renderer } = mount({ formJob: formJob() });
    act(() => {
      hookOf(bucket).chat.conversation.setMessage("Use the saved plan.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, pantry: [] });
    });
    refresh({ formDirty: true });
    refresh({
      formJob: { id: "form-2", status: "failed", error_code: "tool", result: null },
      formDirty: false,
    });
    expect(hookOf(bucket).chat.needsRebuild).toBe(true);
    expect(childText(renderer.root)).toContain(REBUILD_CHAT_GUIDANCE);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Retry the same request").props.disabled).toBe(false);
    expect(renderer.root.findByType("textarea").props.disabled).toBe(false);
    const sends = jobState.submit.mock.calls.length;
    act(() => {
      (
        renderer.root.findByType("form").props.onSubmit as (event: { preventDefault: () => void }) => void
      )({ preventDefault: vi.fn() });
    });
    expect(jobState.submit.mock.calls.length).toBe(sends);
    renderer.unmount();
  });

  it("lets a same-render manual success keep form ownership over chat", async () => {
    const start = { ...initialForm(), monthly: "300", cap: "40" };
    const { bucket, refresh } = mount({ start });
    act(() => {
      hookOf(bucket).chat.conversation.setMessage("Plan lentil soup.");
    });
    await sendAndSettle(bucket);
    jobState.job = chatJob();
    refresh({ formJob: formJob() });
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "bean_tacos", servings: 2 }]);
    expect(hookOf(bucket).chat.estimateJob).toBeNull();
    expect(hookOf(bucket).chat.needsRebuild).toBe(false);
  });

  it("disables a fresh send and keeps retry when the displayed plan is dirty", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = chatJob();
    });
    const { bucket, refresh, renderer } = mount({});
    act(() => {
      hookOf(bucket).chat.conversation.setMessage("Plan lentil soup.");
    });
    await sendAndSettle(bucket);
    refresh();
    act(() => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, pantry: [] });
    });
    expect(hookOf(bucket).chat.needsRebuild).toBe(true);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Retry the same request").props.disabled).toBe(false);
    expect(buttonNamed(renderer.root, "Start a new conversation").props.disabled).toBe(false);
    expect(renderer.root.findByType("textarea").props.disabled).toBe(false);
    const retryCalls = jobState.submit.mock.calls.length;
    act(() => {
      hookOf(bucket).chat.conversation.retry();
    });
    expect(jobState.submit.mock.calls.length).toBe(retryCalls + 1);
    expect(submitted(jobState, retryCalls)).toEqual(submitted(jobState, 0));
    renderer.unmount();
  });
});
