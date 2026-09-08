/** @vitest-environment node */

import { createElement, useState } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryJob, type ProviderCapabilities } from "./apiTypes";
import { initialForm, type FormState } from "./BudgetForm";
import type { ChatJob, ChatResult } from "./chatTypes";
import { ChatWorkspace, useChatWorkspace } from "./ChatWorkspace";
import { useChatConversation, type ChatTurn } from "./useChatConversation";
import { useProviderCapabilities } from "./useProviderCapabilities";

vi.mock("./useChatConversation", () => ({
  useChatConversation: vi.fn(),
}));

vi.mock("./useProviderCapabilities", () => ({
  useProviderCapabilities: vi.fn(),
}));

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const PROVIDER_UNAVAILABLE =
  "The provider configuration is unavailable. Retry the provider request.";
const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

const loaded: ProviderCapabilities = {
  chat_configured: true,
  plaid_configured: false,
  instacart_configured: false,
  spending_source: "fixture",
};

type ChatHook = ReturnType<typeof useChatConversation>;
type WorkspaceHook = ReturnType<typeof useChatWorkspace>;

function plannedResult(overrides: Partial<ChatResult> = {}): ChatResult {
  return {
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
          cost_cents: 1703,
          from_pantry: false,
        },
      ],
      total_cents: 1703,
      accepted: true,
      warnings: ["Plan warning"],
      catalog_version: "sample-prices-v1",
      notice: NOTICE,
    },
    budget: { available_cents: 5000, pending_cents: 200, stale: false, warnings: [] },
    request: {
      meals: [{ recipe_id: "lentil_soup", servings: 4 }],
      budget_period: "2026-09-01",
      plan_cap_cents: 5000,
      pantry_ingredients: ["black_beans"],
      ingredient_exclusions: [],
      diet: "vegetarian",
    },
    evidence_id: null,
    evidence_revision_id: REVISION,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 2,
    planner_revisions: 1,
    usage: null,
    ...overrides,
  };
}

function chatJob(
  result: ChatResult | null,
  status: ChatJob["status"] = "succeeded",
  id = "chat-1",
): ChatJob {
  return { id, status, result, error_code: null };
}

function userTurnList(ids: string[]): ChatTurn[] {
  return ids.map((id) => ({
    id,
    role: "user",
    content: "Plan lentil soup.",
  }));
}

function formJob(): GroceryJob {
  return {
    id: "form-1",
    status: "succeeded",
    error_code: null,
    result: {
      spending_source: "fixture",
      budget: { available_cents: 5000, pending_cents: 0, stale: false, warnings: [] },
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

function conversationState(overrides: Partial<ChatHook> = {}): ChatHook {
  return {
    message: "",
    setMessage: vi.fn(),
    messages: [],
    job: null,
    error: null,
    pending: false,
    hasRequest: false,
    send: vi.fn(),
    retry: vi.fn(),
    newConversation: vi.fn(),
    ...overrides,
  };
}

function providerState(
  overrides: Partial<ReturnType<typeof useProviderCapabilities>> = {},
): ReturnType<typeof useProviderCapabilities> {
  return {
    capabilities: loaded,
    pending: false,
    error: null,
    retry: vi.fn(),
    ...overrides,
  };
}

let chatState: ChatHook;
let providers: ReturnType<typeof useProviderCapabilities>;

function bind(): void {
  vi.mocked(useChatConversation).mockImplementation(() => chatState);
  vi.mocked(useProviderCapabilities).mockImplementation(() => providers);
}

type Bucket = {
  form: FormState;
  setForm: (value: FormState) => void;
  chat: WorkspaceHook;
};

function HookHost(props: {
  bucket: { current: Bucket | null };
  formJob: GroceryJob | null;
  formPending: boolean;
  start?: FormState;
}): JSX.Element {
  const [form, setForm] = useState(props.start ?? initialForm());
  const chat = useChatWorkspace({ form, setForm, formJob: props.formJob });
  props.bucket.current = { form, setForm, chat };
  return createElement(ChatWorkspace, {
    formPending: props.formPending,
    configured: chat.configured,
    configurationPending: chat.configurationPending,
    providerError: chat.providerError,
    retryProviders: chat.retryProviders,
    conversation: chat.conversation,
  });
}

function mount(options: {
  formJob?: GroceryJob | null;
  formPending?: boolean;
  start?: FormState;
}): {
  bucket: { current: Bucket | null };
  renderer: ReactTestRenderer;
  refresh: (next?: { formJob?: GroceryJob | null; formPending?: boolean }) => void;
} {
  bind();
  const bucket: { current: Bucket | null } = { current: null };
  let liveJob = options.formJob ?? null;
  let livePending = options.formPending ?? false;
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(
      createElement(HookHost, {
        bucket,
        formJob: liveJob,
        formPending: livePending,
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
    refresh: (next: { formJob?: GroceryJob | null; formPending?: boolean } = {}): void => {
      liveJob = next.formJob === undefined ? liveJob : next.formJob;
      livePending = next.formPending ?? livePending;
      bind();
      act(() => {
        live.update(
          createElement(HookHost, {
            bucket,
            formJob: liveJob,
            formPending: livePending,
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

describe("ChatWorkspace", () => {
  beforeEach(() => {
    chatState = conversationState();
    providers = providerState();
    bind();
  });

  it("shows configured meal chat beside an idle composer", () => {
    const { renderer } = mount({});
    expect(childText(renderer.root)).toContain("Meal chat");
    expect(childText(renderer.root)).toContain("No messages yet");
    expect(childText(renderer.root)).not.toContain("Checking meal chat configuration.");
    expect(childText(renderer.root)).not.toContain("Meal chat is unavailable.");
    expect(childText(renderer.root).toLowerCase()).not.toContain("chat is connected");
    expect(childText(renderer.root)).not.toContain("Bedrock");
    renderer.unmount();
  });

  it("shows loading, unavailable, and retry provider states", () => {
    providers = providerState({ pending: true, capabilities: null });
    const waiting = mount({});
    expect(childText(waiting.renderer.root)).toContain("Checking meal chat configuration.");
    expect(buttonNamed(waiting.renderer.root, "Send").props.disabled).toBe(true);
    waiting.renderer.unmount();
    providers = providerState({ capabilities: { ...loaded, chat_configured: false } });
    const off = mount({});
    expect(childText(off.renderer.root)).toContain("Meal chat is unavailable.");
    expect(buttonNamed(off.renderer.root, "Send").props.disabled).toBe(true);
    off.renderer.unmount();
    const retry = vi.fn();
    providers = providerState({
      capabilities: null,
      error: PROVIDER_UNAVAILABLE,
      retry,
    });
    const failed = mount({});
    expect(childText(failed.renderer.root)).toContain(PROVIDER_UNAVAILABLE);
    act(() => {
      (buttonNamed(failed.renderer.root, "Retry provider status").props.onClick as () => void)();
    });
    expect(retry).toHaveBeenCalledTimes(1);
    failed.renderer.unmount();
  });

  it("disables chat send while a form request is pending", () => {
    chatState = conversationState({ message: "Plan bean tacos for two." });
    const { renderer, refresh } = mount({ formPending: true });
    expect(renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Start a new conversation").props.disabled).toBe(true);
    refresh({ formPending: false });
    expect(renderer.root.findByType("textarea").props.disabled).toBe(false);
    renderer.unmount();
  });

  it("applies a chat plan to the form without raising the monthly limit", () => {
    const { bucket, refresh } = mount({
      start: { ...initialForm(), monthly: "300", cap: "40" },
    });
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages: [
        { id: "user-1", role: "user", content: "Plan lentil soup." },
        { id: "chat-1", role: "assistant", content: "Bean tacos fit the budget." },
      ],
      job: chatJob(plannedResult()),
      hasRequest: true,
    });
    refresh();
    const next = hookOf(bucket).form;
    expect(next.monthly).toBe("300");
    expect(next.cap).toBe("40");
    expect(next.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    expect(next.diet).toBe("vegetarian");
    expect(next.pantry).toEqual(["black_beans"]);
    expect(hookOf(bucket).chat.estimateJob?.result?.plan.total_cents).toBe(1703);
    expect(hookOf(bucket).chat.estimateJob?.result?.plan.notice).toBe(NOTICE);
    expect(hookOf(bucket).chat.estimateDirty).toBe(false);
  });

  it("does not overwrite newer manual edits with a stale chat plan", () => {
    const { bucket, refresh } = mount({
      start: { ...initialForm(), monthly: "300", cap: "40" },
    });
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
      hasRequest: true,
    });
    refresh();
    act(() => {
      hookOf(bucket).setForm({
        ...hookOf(bucket).form,
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
        monthly: "250",
      });
    });
    chatState = conversationState({
      messages: [
        { id: "user-1", role: "user", content: "Plan lentil soup." },
        { id: "chat-1", role: "assistant", content: "Bean tacos fit the budget." },
      ],
      job: chatJob(plannedResult()),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).form.monthly).toBe("250");
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "bean_tacos", servings: 2 }]);
    expect(hookOf(bucket).chat.estimateJob).toBeNull();
  });

  it("does not apply a clarification with no plan and does not invent assistant text", () => {
    const { bucket, refresh, renderer } = mount({});
    const start = structuredClone(hookOf(bucket).form);
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan dinner." }],
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages: [
        { id: "user-1", role: "user", content: "Plan dinner." },
        { id: "chat-1", role: "assistant", content: "Which meals should I plan?" },
      ],
      job: chatJob(
        plannedResult({
          status: "clarification",
          answer: "Which meals should I plan?",
          plan: null,
          budget: null,
          request: null,
          evidence_revision_id: null,
        }),
      ),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).form).toEqual(start);
    expect(hookOf(bucket).chat.estimateJob).toBeNull();
    expect(childText(renderer.root)).toContain("Which meals should I plan?");
    expect(childText(renderer.root)).not.toContain("fake");
    renderer.unmount();
  });

  it("lets a later form estimate replace the chat estimate", () => {
    const { bucket, refresh } = mount({});
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
      job: chatJob(plannedResult()),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
    refresh({ formJob: formJob() });
    expect(hookOf(bucket).chat.estimateJob).toBeNull();
  });

  it("applies a later chat plan when visible user count stays the same and user ids change", () => {
    const { bucket, refresh } = mount({
      start: { ...initialForm(), monthly: "300", cap: "40" },
    });
    const firstWindow = userTurnList([
      "user-1",
      "user-2",
      "user-3",
      "user-4",
      "user-5",
      "user-6",
      "user-7",
      "user-8",
    ]);
    chatState = conversationState({ messages: firstWindow, hasRequest: true });
    refresh();
    act(() => {
      hookOf(bucket).setForm({
        ...hookOf(bucket).form,
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
        monthly: "250",
      });
    });
    const laterWindow = userTurnList([
      "user-9",
      "user-10",
      "user-11",
      "user-12",
      "user-13",
      "user-14",
      "user-15",
      "user-16",
    ]);
    chatState = conversationState({ messages: laterWindow, hasRequest: true });
    refresh();
    chatState = conversationState({
      messages: laterWindow,
      job: chatJob(plannedResult(), "succeeded", "chat-2"),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).form.monthly).toBe("250");
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-2");
    expect(hookOf(bucket).chat.estimateDirty).toBe(false);
  });

  it("applies a chat plan after a form edit that happens before the next send", () => {
    const { bucket, refresh } = mount({
      start: { ...initialForm(), monthly: "300", cap: "40" },
    });
    chatState = conversationState({
      messages: userTurnList(["user-1"]),
      hasRequest: true,
    });
    refresh();
    act(() => {
      hookOf(bucket).setForm({
        ...hookOf(bucket).form,
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
      });
    });
    chatState = conversationState({
      messages: userTurnList(["user-1", "user-2"]),
      job: chatJob(plannedResult(), "succeeded", "chat-2"),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-2");
  });

  it("treats a new conversation user turn as a new request after ids reset", () => {
    const { bucket, refresh } = mount({});
    chatState = conversationState({
      messages: userTurnList(["user-1"]),
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages: userTurnList(["user-1"]),
      job: chatJob(plannedResult()),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
    chatState = conversationState({
      messages: [],
      job: null,
      hasRequest: false,
    });
    refresh();
    act(() => {
      hookOf(bucket).setForm({
        ...hookOf(bucket).form,
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
      });
    });
    chatState = conversationState({
      messages: userTurnList(["user-1"]),
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages: userTurnList(["user-1"]),
      job: chatJob(plannedResult(), "succeeded", "chat-2"),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-2");
  });

  it("does not treat a replay of the same user turn as a new submitted form", () => {
    const { bucket, refresh } = mount({});
    const messages = userTurnList(["user-1"]);
    chatState = conversationState({ messages, hasRequest: true });
    refresh();
    act(() => {
      hookOf(bucket).setForm({
        ...hookOf(bucket).form,
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
        monthly: "250",
      });
    });
    chatState = conversationState({
      messages,
      job: chatJob(plannedResult(), "queued"),
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages,
      job: chatJob(plannedResult()),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).form.monthly).toBe("250");
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "bean_tacos", servings: 2 }]);
    expect(hookOf(bucket).chat.estimateJob).toBeNull();
  });

  it("marks the chat estimate dirty after a later form edit", () => {
    const { bucket, refresh } = mount({});
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
      hasRequest: true,
    });
    refresh();
    chatState = conversationState({
      messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
      job: chatJob(plannedResult()),
      hasRequest: true,
    });
    refresh();
    expect(hookOf(bucket).chat.estimateDirty).toBe(false);
    act(() => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, pantry: [] });
    });
    expect(hookOf(bucket).chat.estimateDirty).toBe(true);
    expect(hookOf(bucket).chat.estimateJob?.id).toBe("chat-1");
  });
});

describe("ChatWorkspace panel", () => {
  it("renders escaped assistant text from supplied messages", () => {
    const messages: ChatTurn[] = [
      { id: "u1", role: "user", content: "<script>alert(1)</script>" },
      { id: "a1", role: "assistant", content: "<script>alert(1)</script>" },
    ];
    let renderer: ReactTestRenderer | undefined;
    act(() => {
      renderer = create(
        createElement(ChatWorkspace, {
          formPending: false,
          configured: true,
          configurationPending: false,
          providerError: null,
          retryProviders: vi.fn(),
          conversation: conversationState({ messages, message: "Hi" }),
        }),
      );
    });
    if (renderer === undefined) {
      throw new Error("renderer failed to mount");
    }
    expect(renderer.root.findAll((node) => node.props.dangerouslySetInnerHTML !== undefined)).toHaveLength(
      0,
    );
    expect(childText(renderer.root)).toContain("<script>alert(1)</script>");
    renderer.unmount();
  });
});
