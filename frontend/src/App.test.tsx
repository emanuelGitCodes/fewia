/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { REBUILD_CHAT_GUIDANCE } from "./ChatWorkspace";
import {
  SAMPLE_ESTIMATE_NOTICE,
  type GroceryConfig,
  type GroceryJob,
  type ProviderCapabilities,
} from "./apiTypes";
import { initialForm, type FormState } from "./BudgetForm";
import type { ChatJob, ChatResult } from "./chatTypes";
import { useChatConversation } from "./useChatConversation";
import { useGroceryDemo, type GroceryDemo } from "./useGroceryDemo";
import { useHandoff } from "./useHandoff";
import { useProviderCapabilities } from "./useProviderCapabilities";

vi.mock("./useGroceryDemo", () => ({
  useGroceryDemo: vi.fn(),
}));

vi.mock("./useChatConversation", () => ({
  useChatConversation: vi.fn(),
}));

vi.mock("./useProviderCapabilities", () => ({
  useProviderCapabilities: vi.fn(),
}));

vi.mock("./useHandoff", () => ({
  useHandoff: vi.fn(),
}));

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const CATALOG_UNAVAILABLE = "The grocery catalog is unavailable. Retry the catalog request.";
const PROVIDER_UNAVAILABLE =
  "The provider configuration is unavailable. Retry the provider request.";
const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

const providersReady: ProviderCapabilities = {
  chat_configured: true,
  plaid_configured: false,
  instacart_configured: false,
  spending_source: "fixture",
};

type ChatHook = ReturnType<typeof useChatConversation>;
type HandoffHook = ReturnType<typeof useHandoff>;

function chatState(overrides: Partial<ChatHook> = {}): ChatHook {
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

function plannedChat(): ChatResult {
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
      plan_cap_cents: 2000,
      pantry_ingredients: ["black_beans"],
      ingredient_exclusions: [],
      diet: "vegetarian",
    },
    evidence_id: null,
    evidence_revision_id: REVISION,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 1,
    planner_revisions: 0,
    usage: null,
  };
}

function chatJob(result: ChatResult): ChatJob {
  return { id: "chat-1", status: "succeeded", result, error_code: null };
}

const demoConfig: GroceryConfig = {
  budget_period: "2026-09-01",
  source: "fixture",
  catalog_version: "sample-prices-v1",
  posted_cents: 1200,
  pending_cents: -50,
  spending_refreshed_at: "2026-09-07T16:00:00Z",
  notice: NOTICE,
  recipes: [
    { id: "bean_tacos", name: "Bean tacos" },
    { id: "lentil_soup", name: "Lentil soup" },
  ],
  ingredients: [{ id: "black_beans", name: "black beans" }],
};

const succeededJob: GroceryJob = {
  id: "job-1",
  status: "succeeded",
  error_code: null,
  result: {
    spending_source: "fixture",
    budget: { available_cents: 5000, pending_cents: 200, stale: false, warnings: [] },
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
  },
};

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

function hasButton(root: ReactTestInstance, name: string): boolean {
  return root.findAllByType("button").some((node) => childText(node) === name);
}

function handoffState(overrides: Partial<HandoffHook> = {}): HandoffHook {
  return {
    view: null,
    error: null,
    pending: false,
    start: vi.fn(async () => undefined),
    retry: vi.fn(async () => undefined),
    clear: vi.fn(),
    ...overrides,
  };
}

function instacartProviders(): ReturnType<typeof useProviderCapabilities> {
  return {
    capabilities: { ...providersReady, instacart_configured: true },
    pending: false,
    error: null,
    retry: vi.fn(),
  };
}

function demoState(overrides: Partial<GroceryDemo> = {}): GroceryDemo {
  return {
    config: demoConfig,
    configPending: false,
    configError: null,
    reloadConfig: vi.fn(),
    form: initialForm(),
    setForm: vi.fn(),
    formError: null,
    job: null,
    error: null,
    pending: false,
    submitForm: vi.fn(async () => undefined),
    retry: vi.fn(),
    newRequest: vi.fn(),
    example: vi.fn(),
    togglePantry: vi.fn(),
    dirty: false,
    ...overrides,
  };
}

function mount(
  demo: GroceryDemo,
  chat: ChatHook = chatState(),
  provider: ReturnType<typeof useProviderCapabilities> = {
    capabilities: providersReady,
    pending: false,
    error: null,
    retry: vi.fn(),
  },
  handoff: HandoffHook = handoffState(),
): ReactTestRenderer {
  vi.mocked(useGroceryDemo).mockReturnValue(demo);
  vi.mocked(useChatConversation).mockReturnValue(chat);
  vi.mocked(useProviderCapabilities).mockReturnValue(provider);
  vi.mocked(useHandoff).mockReturnValue(handoff);
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(createElement(App));
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return renderer;
}

describe("App", () => {
  beforeEach(() => {
    vi.mocked(useGroceryDemo).mockReset();
    vi.mocked(useChatConversation).mockReset();
    vi.mocked(useProviderCapabilities).mockReset();
    vi.mocked(useHandoff).mockReset();
  });

  it("keeps the shell wordmark, local demo label, title, and footer", () => {
    const renderer = mount(demoState());
    const text = childText(renderer.root);
    expect(text).toContain("FEWIA");
    expect(text).toContain("Local demo · Sample prices");
    expect(text).toContain("Meals that fit your budget");
    expect(text).toContain("No purchases are made here.");
    expect(text.toLowerCase()).not.toContain("bank connected");
    expect(text.toLowerCase()).not.toContain("chat is connected");
    renderer.unmount();
  });

  it("shows accessible catalog loading and does not call it a job submission", () => {
    const example = vi.fn();
    const renderer = mount(demoState({ config: null, configPending: true, example }));
    const status = renderer.root.findByProps({ className: "catalog-status" });
    expect(status.props.role).toBe("status");
    expect(childText(status)).toBe("Loading the grocery catalog.");
    expect(childText(renderer.root)).not.toContain("Submitting your grocery request.");
    expect(renderer.root.findAllByType("form")).toHaveLength(1);
    expect(childText(renderer.root)).toContain("Meal chat");
    expect(childText(renderer.root)).toContain(NOTICE);
    expect(buttonNamed(renderer.root, "Bean tacos for two").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Three vegan dinners (2 servings each)").props.disabled).toBe(true);
    expect(example).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("shows catalog error with retry and keeps an old estimate", () => {
    const reloadConfig = vi.fn();
    const example = vi.fn();
    const renderer = mount(
      demoState({
        config: demoConfig,
        configError: CATALOG_UNAVAILABLE,
        reloadConfig,
        example,
        job: succeededJob,
      }),
    );
    const status = renderer.root.findByProps({ className: "catalog-error" });
    expect(status.props.role).toBe("status");
    expect(childText(status)).toBe(CATALOG_UNAVAILABLE);
    expect(childText(renderer.root)).toContain("$17.03");
    expect(buttonNamed(renderer.root, "Build my estimate").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Bean tacos for two").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Three vegan dinners (2 servings each)").props.disabled).toBe(true);
    act(() => {
      (buttonNamed(renderer.root, "Retry catalog").props.onClick as () => void)();
    });
    expect(reloadConfig).toHaveBeenCalledTimes(1);
    expect(example).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("submits the composer form and shows form errors", () => {
    const submitForm = vi.fn(async () => undefined);
    const preventDefault = vi.fn();
    const renderer = mount(demoState({ submitForm, formError: "Choose 1 to 3 meals." }));
    const alert = renderer.root.findByProps({ role: "alert" });
    expect(childText(alert)).toBe("Choose 1 to 3 meals.");
    expect(childText(renderer.root)).toContain("Source Demo spending. Pending -$0.50");
    const budgetForm = renderer.root.findAllByType("form").find((form) =>
      form.findAllByType("button").some((node) => childText(node) === "Build my estimate"),
    );
    if (budgetForm === undefined) {
      throw new Error("missing Build my estimate form");
    }
    const onSubmit = budgetForm.props.onSubmit as (event: {
      preventDefault: () => void;
    }) => void;
    act(() => {
      onSubmit({ preventDefault });
    });
    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(submitForm).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("renders the estimate amount, notice, and provenance from the job", () => {
    const renderer = mount(demoState({ job: succeededJob }));
    const text = childText(renderer.root);
    expect(text).toContain("$17.03");
    expect(text).toContain("Source Demo spending");
    expect(text).toContain(NOTICE);
    expect(text).toContain("Plan warning");
    expect(text).toContain("black beans");
    expect(renderer.root.findAllByType("h2").map(childText)).toEqual([
      "Your conversation",
      "Meal chat",
      "Grocery estimate",
    ]);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("disables controls while pending and does not reprice locally", () => {
    const togglePantry = vi.fn();
    const renderer = mount(
      demoState({
        pending: true,
        dirty: true,
        job: succeededJob,
        form: { ...initialForm(), pantry: ["black_beans"] },
        togglePantry,
      }),
    );
    expect(buttonNamed(renderer.root, "Build my estimate").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Bean tacos for two").props.disabled).toBe(true);
    expect(renderer.root.findByType("fieldset").props.disabled).toBe(true);
    expect(childText(renderer.root)).toContain("Previous estimate");
    expect(childText(renderer.root)).toContain("$17.03");
    const box = renderer.root.findByProps({ id: "pantry-black_beans" });
    act(() => {
      (box.props.onChange as () => void)();
    });
    expect(togglePantry).toHaveBeenCalledWith("black_beans");
    expect(childText(renderer.root)).toContain("$17.03");
    expect(buttonNamed(renderer.root, "Rebuild estimate").props.disabled).toBe(true);
    renderer.unmount();
  });

  it("rebuilds from the estimate when pantry is dirty", () => {
    const submitForm = vi.fn(async () => undefined);
    const togglePantry = vi.fn();
    const renderer = mount(
      demoState({
        dirty: true,
        job: succeededJob,
        submitForm,
        togglePantry,
      }),
    );
    expect(buttonNamed(renderer.root, "Rebuild estimate").props.disabled).toBe(false);
    expect(childText(renderer.root)).toContain("$17.03");
    act(() => {
      (buttonNamed(renderer.root, "Rebuild estimate").props.onClick as () => void)();
    });
    expect(submitForm).toHaveBeenCalledTimes(1);
    act(() => {
      (renderer.root.findByProps({ id: "pantry-black_beans" }).props.onChange as () => void)();
    });
    expect(togglePantry).toHaveBeenCalledWith("black_beans");
    expect(submitForm).toHaveBeenCalledTimes(1);
    expect(childText(renderer.root)).toContain("$17.03");
    renderer.unmount();
  });

  it("disables rebuild when the catalog is blocked", () => {
    const submitForm = vi.fn(async () => undefined);
    const renderer = mount(
      demoState({
        dirty: true,
        job: succeededJob,
        configError: CATALOG_UNAVAILABLE,
        submitForm,
      }),
    );
    expect(buttonNamed(renderer.root, "Rebuild estimate").props.disabled).toBe(true);
    expect(submitForm).not.toHaveBeenCalled();
    expect(childText(renderer.root)).toContain("$17.03");
    renderer.unmount();
  });

  it("wires example, retry, and new-request actions", () => {
    const example = vi.fn();
    const retry = vi.fn();
    const newRequest = vi.fn();
    const ready = mount(demoState({ example, retry, newRequest }));
    act(() => {
      (buttonNamed(ready.root, "Bean tacos for two").props.onClick as () => void)();
    });
    expect(example).toHaveBeenCalledWith("beans");
    ready.unmount();
    const retryView = mount(
      demoState({ example, retry, newRequest, error: "The grocery request failed." }),
    );
    act(() => {
      (buttonNamed(retryView.root, "Retry request").props.onClick as () => void)();
    });
    expect(retry).toHaveBeenCalledTimes(1);
    expect(newRequest).not.toHaveBeenCalled();
    retryView.unmount();
    const failed = mount(
      demoState({
        example,
        retry,
        newRequest,
        job: { id: "job-2", status: "failed", error_code: "tool", result: null },
      }),
    );
    act(() => {
      (buttonNamed(failed.root, "Start a new request").props.onClick as () => void)();
    });
    expect(newRequest).toHaveBeenCalledTimes(1);
    failed.unmount();
  });

  it("disables a failed new request when the catalog is blocked", () => {
    const newRequest = vi.fn();
    const renderer = mount(
      demoState({
        config: demoConfig,
        configError: CATALOG_UNAVAILABLE,
        job: { id: "job-2", status: "failed", error_code: "tool", result: null },
        newRequest,
      }),
    );
    expect(buttonNamed(renderer.root, "Start a new request").props.disabled).toBe(true);
    expect(newRequest).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("keeps Retry request available when the catalog is blocked", () => {
    const retry = vi.fn();
    const renderer = mount(
      demoState({
        config: null,
        configPending: true,
        error: "The grocery request failed.",
        retry,
      }),
    );
    const retryButton = buttonNamed(renderer.root, "Retry request");
    expect(retryButton.props.disabled).toBe(false);
    act(() => {
      (retryButton.props.onClick as () => void)();
    });
    expect(retry).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("shows meal chat and disables the form while chat is pending", () => {
    const renderer = mount(demoState(), chatState({ pending: true, message: "Plan tacos" }));
    expect(childText(renderer.root)).toContain("Meal chat");
    expect(childText(renderer.root)).toContain("Your request is in progress.");
    expect(buttonNamed(renderer.root, "Build my estimate").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Bean tacos for two").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(renderer.root.findByType("fieldset").props.disabled).toBe(true);
    renderer.unmount();
  });

  it("applies a chat plan to the shared estimate without raising the monthly budget", () => {
    const setForm = vi.fn();
    const form: FormState = { ...initialForm(), monthly: "300", cap: "40" };
    const renderer = mount(
      demoState({ setForm, form }),
      chatState({
        messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
        job: chatJob(plannedChat()),
        hasRequest: true,
      }),
    );
    expect(childText(renderer.root)).toContain("$17.03");
    expect(childText(renderer.root)).toContain(NOTICE);
    expect(childText(renderer.root)).toContain("Plan warning");
    expect(setForm).toHaveBeenCalled();
    const next = setForm.mock.calls[0]?.[0] as FormState;
    expect(next.monthly).toBe("300");
    expect(next.cap).toBe("20.00");
    expect(next.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    renderer.unmount();
  });

  it("shows provider retry and does not claim a live chat connection", () => {
    const retry = vi.fn();
    const renderer = mount(demoState(), chatState(), {
      capabilities: null,
      pending: false,
      error: PROVIDER_UNAVAILABLE,
      retry,
    });
    expect(childText(renderer.root)).toContain(PROVIDER_UNAVAILABLE);
    expect(childText(renderer.root)).toContain("Meal chat is unavailable.");
    expect(childText(renderer.root).toLowerCase()).not.toContain("chat is connected");
    act(() => {
      (buttonNamed(renderer.root, "Retry provider status").props.onClick as () => void)();
    });
    expect(retry).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("shows rebuild guidance when dirty pantry is not in the saved plan", () => {
    const submitForm = vi.fn(async () => undefined);
    const renderer = mount(
      demoState({
        dirty: true,
        job: succeededJob,
        submitForm,
        form: { ...initialForm(), pantry: ["black_beans"] },
      }),
      chatState({ message: "Add soup to the plan." }),
    );
    expect(childText(renderer.root)).toContain(REBUILD_CHAT_GUIDANCE);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Rebuild estimate").props.disabled).toBe(false);
    expect(buttonNamed(renderer.root, "Build my estimate").props.disabled).toBe(false);
    act(() => {
      (buttonNamed(renderer.root, "Rebuild estimate").props.onClick as () => void)();
    });
    expect(submitForm).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("disables a fresh chat send when the catalog is blocked and keeps retry", () => {
    const retry = vi.fn();
    const renderer = mount(
      demoState({
        configError: CATALOG_UNAVAILABLE,
        job: succeededJob,
      }),
      chatState({
        message: "Add soup to the plan.",
        hasRequest: true,
        retry,
      }),
    );
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Retry the same request").props.disabled).toBe(false);
    expect(renderer.root.findByType("textarea").props.disabled).toBe(false);
    expect(childText(renderer.root)).not.toContain(REBUILD_CHAT_GUIDANCE);
    act(() => {
      (buttonNamed(renderer.root, "Retry the same request").props.onClick as () => void)();
    });
    expect(retry).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("keeps chat-first send when no saved plan owns the form", () => {
    const renderer = mount(
      demoState({ form: { ...initialForm(), pantry: ["black_beans"] } }),
      chatState({ message: "Plan bean tacos for two." }),
    );
    expect(childText(renderer.root)).not.toContain(REBUILD_CHAT_GUIDANCE);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(false);
    renderer.unmount();
  });

  it("shows Create shopping list for a succeeded accepted estimate when Instacart is configured", () => {
    const renderer = mount(demoState({ job: succeededJob }), chatState(), instacartProviders());
    expect(hasButton(renderer.root, "Create shopping list")).toBe(true);
    expect(childText(renderer.root)).toContain("No purchases are made here.");
    renderer.unmount();
  });

  it("hides start and shopping links when Instacart is not configured", () => {
    const renderer = mount(demoState({ job: succeededJob }));
    expect(hasButton(renderer.root, "Create shopping list")).toBe(false);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(childText(renderer.root)).not.toContain("Open shopping list");
    renderer.unmount();
  });

  it("hides start when the estimate is dirty", () => {
    const renderer = mount(
      demoState({ job: succeededJob, dirty: true }),
      chatState(),
      instacartProviders(),
    );
    expect(hasButton(renderer.root, "Create shopping list")).toBe(false);
    renderer.unmount();
  });

  it("hides start when the plan is not accepted", () => {
    const result = succeededJob.result;
    if (result === null) {
      throw new Error("missing succeeded job result");
    }
    const renderer = mount(
      demoState({
        job: {
          ...succeededJob,
          result: { ...result, plan: { ...result.plan, accepted: false } },
        },
      }),
      chatState(),
      instacartProviders(),
    );
    expect(hasButton(renderer.root, "Create shopping list")).toBe(false);
    renderer.unmount();
  });

  it("starts handoff with the succeeded job id", () => {
    const start = vi.fn(async () => undefined);
    const renderer = mount(
      demoState({ job: succeededJob }),
      chatState(),
      instacartProviders(),
      handoffState({ start }),
    );
    act(() => {
      (buttonNamed(renderer.root, "Create shopping list").props.onClick as () => void)();
    });
    expect(start).toHaveBeenCalledTimes(1);
    expect(start).toHaveBeenCalledWith("job-1");
    renderer.unmount();
  });
});
