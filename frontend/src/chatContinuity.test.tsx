/** @vitest-environment jsdom */

import { createElement, useState, type JSX } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

function childText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(root: HTMLElement, name: string): HTMLButtonElement {
  return within(root).getByRole("button", { name }) as HTMLButtonElement;
}

afterEach(cleanup);

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
    renderer: RenderResult;
    refresh: (next?: { formJob?: GroceryJob | null; formDirty?: boolean }) => void;
  } {
    bindJob();
    const bucket: { current: Bucket | null } = { current: null };
    let liveJob = options.formJob ?? null;
    let liveDirty = options.formDirty ?? false;
    const live = render(
      createElement(HookHost, {
        bucket,
        formJob: liveJob,
        formDirty: liveDirty,
        start: options.start,
      }),
    );
    return {
      bucket,
      renderer: live,
      refresh: (next: { formJob?: GroceryJob | null; formDirty?: boolean } = {}): void => {
        liveJob = next.formJob === undefined ? liveJob : next.formJob;
        liveDirty = next.formDirty ?? liveDirty;
        bindJob();
        act(() => {
          live.rerender(
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

  async function sendAndSettle(): Promise<void> {
    await act(async () => {
      fireEvent.submit(screen.getByRole("textbox").closest("form")!);
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
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Plan lentil soup." } });
    });
    await sendAndSettle();
    refresh();
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Start a new conversation" }));
    });
    refresh();
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Use the same pantry." } });
    });
    await sendAndSettle();
    expect(submitted(jobState, 1).previous_job_id).toBe("chat-1");
    expect(submitted(jobState, 1).previous_job_id).not.toBe("form-1");
  });

  it("blocks a contextless send after a failed rebuild of a dirty pantry", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = chatJob();
    });
    const { bucket, refresh, renderer } = mount({ formJob: formJob() });
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Use the saved plan." } });
    });
    await sendAndSettle();
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
    expect(childText(renderer.container)).toContain(REBUILD_CHAT_GUIDANCE);
    expect(buttonNamed(renderer.container, "Send").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Retry the same request").disabled).toBe(false);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    const sends = jobState.submit.mock.calls.length;
    act(() => {
      fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    });
    expect(jobState.submit.mock.calls.length).toBe(sends);
    renderer.unmount();
  });

  it("lets a same-render manual success keep form ownership over chat", async () => {
    const start = { ...initialForm(), monthly: "300", cap: "40" };
    const { bucket, refresh } = mount({ start });
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Plan lentil soup." } });
    });
    await sendAndSettle();
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
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Plan lentil soup." } });
    });
    await sendAndSettle();
    refresh();
    act(() => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, pantry: [] });
    });
    expect(hookOf(bucket).chat.needsRebuild).toBe(true);
    expect(buttonNamed(renderer.container, "Send").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Retry the same request").disabled).toBe(false);
    expect(buttonNamed(renderer.container, "Start a new conversation").disabled).toBe(false);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    const retryCalls = jobState.submit.mock.calls.length;
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Retry the same request" }));
    });
    expect(jobState.submit.mock.calls.length).toBe(retryCalls + 1);
    expect(submitted(jobState, retryCalls)).toEqual(submitted(jobState, 0));
    renderer.unmount();
  });

  it("keeps an unresolved chat estimate after a pending follow-up and a new conversation", async () => {
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = chatJob();
    });
    const { bucket, refresh, renderer } = mount({});
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Plan lentil soup." } });
    });
    await sendAndSettle();
    refresh();
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
    expect(hookOf(bucket).chat.unresolvedChatEstimate).toBe(false);
    jobState.submit.mockImplementation(async (_body: ChatJobCreate) => {
      jobState.job = { id: "chat-2", status: "queued", result: null, error_code: null };
      jobState.pending = true;
    });
    act(() => {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "Add another meal." } });
    });
    await sendAndSettle();
    refresh();
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
    expect(hookOf(bucket).chat.unresolvedChatEstimate).toBe(true);
    jobState.pending = false;
    jobState.job = { id: "chat-2", status: "failed", result: null, error_code: "tool" };
    refresh();
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
    expect(hookOf(bucket).chat.unresolvedChatEstimate).toBe(true);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Start a new conversation" }));
    });
    refresh();
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
    expect(hookOf(bucket).chat.unresolvedChatEstimate).toBe(true);
    renderer.unmount();
  });
});
