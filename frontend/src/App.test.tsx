/** @vitest-environment jsdom */

import { createElement, useState, type JSX } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
import { useTemplateSuggestions } from "./useTemplateSuggestions";
import { sampleNutrition } from "../tests/apiFixtures";

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

vi.mock("./useTemplateSuggestions", () => ({
  useTemplateSuggestions: vi.fn(),
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
type TemplateHook = ReturnType<typeof useTemplateSuggestions>;

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
    meal_nutrition: sampleNutrition(),
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
    meal_nutrition: sampleNutrition(),
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

function childText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(root: HTMLElement, name: string): HTMLButtonElement {
  return within(root).getByRole("button", { name }) as HTMLButtonElement;
}

function mealIdeas(root: HTMLElement): HTMLFieldSetElement {
  return within(root).getByRole("group", { name: "Meal ideas" }) as HTMLFieldSetElement;
}

function hasButton(root: HTMLElement, name: string): boolean {
  return within(root).queryByRole("button", { name }) !== null;
}

function elementWithText(text: string): HTMLElement {
  return screen.getByText(
    (_content, node) =>
      node?.textContent === text &&
      Array.from(node.children).every((child) => child.textContent !== text),
  );
}

afterEach(cleanup);

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

function templateState(overrides: Partial<TemplateHook> = {}): TemplateHook {
  return {
    pending: false,
    error: null,
    suggestions: null,
    find: vi.fn(),
    ...overrides,
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
  templates: TemplateHook = templateState(),
): RenderResult {
  vi.mocked(useGroceryDemo).mockReturnValue(demo);
  vi.mocked(useChatConversation).mockReturnValue(chat);
  vi.mocked(useProviderCapabilities).mockReturnValue(provider);
  vi.mocked(useHandoff).mockReturnValue(handoff);
  vi.mocked(useTemplateSuggestions).mockReturnValue(templates);
  return render(createElement(App));
}

function AppUnresolvedHost(props: {
  chat: ChatHook;
  pending?: boolean;
  job?: GroceryJob | null;
}): JSX.Element {
  const [form, setForm] = useState(initialForm());
  vi.mocked(useGroceryDemo).mockReturnValue(
    demoState({
      form,
      setForm,
      job: props.job ?? null,
      dirty: false,
      pending: props.pending === true,
    }),
  );
  vi.mocked(useChatConversation).mockReturnValue(props.chat);
  vi.mocked(useProviderCapabilities).mockReturnValue(instacartProviders());
  vi.mocked(useHandoff).mockReturnValue(handoffState());
  return createElement(App);
}

describe("App", () => {
  beforeEach(() => {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value: function (this: HTMLDialogElement): void {
        this.open = true;
        this.querySelector<HTMLButtonElement>("button")?.focus();
      },
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value: function (this: HTMLDialogElement): void {
        this.open = false;
      },
    });
    vi.mocked(useGroceryDemo).mockReset();
    vi.mocked(useChatConversation).mockReset();
    vi.mocked(useProviderCapabilities).mockReset();
    vi.mocked(useHandoff).mockReset();
    vi.mocked(useTemplateSuggestions).mockReset();
    vi.mocked(useTemplateSuggestions).mockReturnValue(templateState());
  });

  it("keeps the shell wordmark, local demo label, title, and footer", () => {
    const renderer = mount(demoState());
    const text = childText(renderer.container);
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
    const status = screen.getByText("Loading the grocery catalog.");
    expect(status.getAttribute("role")).toBe("status");
    expect(childText(status)).toBe("Loading the grocery catalog.");
    expect(childText(renderer.container)).not.toContain("Submitting your grocery request.");
    expect(renderer.container.querySelectorAll("form")).toHaveLength(1);
    expect(childText(renderer.container)).toContain("Meal chat");
    expect(childText(renderer.container)).toContain(NOTICE);
    expect(buttonNamed(renderer.container, "Bean tacos for two").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Three vegan dinners (2 servings each)").disabled).toBe(true);
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
    const status = screen.getByText(CATALOG_UNAVAILABLE);
    expect(status.getAttribute("role")).toBe("status");
    expect(childText(status)).toBe(CATALOG_UNAVAILABLE);
    expect(childText(renderer.container)).toContain("$17.03");
    expect(buttonNamed(renderer.container, "Build my estimate").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Bean tacos for two").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Three vegan dinners (2 servings each)").disabled).toBe(true);
    act(() => {
      fireEvent.click(buttonNamed(renderer.container, "Retry catalog"));
    });
    expect(reloadConfig).toHaveBeenCalledTimes(1);
    expect(example).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("labels a manual spending source without pending amounts", () => {
    const manual = mount(demoState({ config: { ...demoConfig, source: "manual" } }));
    const manualSource = elementWithText("Source Your entered budget.");
    expect(childText(manualSource)).toBe("Source Your entered budget.");
    expect(childText(manualSource)).not.toContain("Pending");
    manual.unmount();
    const fixture = mount(demoState());
    const fixtureSource = elementWithText("Source Demo spending. Pending -$0.50");
    expect(childText(fixtureSource)).toBe("Source Demo spending. Pending -$0.50");
    fixture.unmount();
  });

  it("submits the composer form and shows form errors", () => {
    const submitForm = vi.fn(async () => undefined);
    const renderer = mount(demoState({ submitForm, formError: "Choose 1 to 3 meals." }));
    const alert = screen.getByRole("alert");
    expect(childText(alert)).toBe("Choose 1 to 3 meals.");
    expect(childText(renderer.container)).toContain("Source Demo spending. Pending -$0.50");
    const budgetForm = buttonNamed(renderer.container, "Build my estimate").closest("form");
    if (budgetForm === null) {
      throw new Error("missing Build my estimate form");
    }
    const submitEvent = new Event("submit", { bubbles: true, cancelable: true });
    act(() => {
      fireEvent(budgetForm, submitEvent);
    });
    expect(submitEvent.defaultPrevented).toBe(true);
    expect(submitForm).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("renders the estimate amount, notice, and provenance from the job", () => {
    const renderer = mount(demoState({ job: succeededJob }));
    const text = childText(renderer.container);
    expect(text).toContain("$17.03");
    expect(text).toContain("Source Demo spending");
    expect(text).toContain(NOTICE);
    expect(text).toContain("Plan warning");
    expect(text).toContain("black beans");
    expect(screen.getAllByRole("heading", { level: 2 }).map(childText)).toEqual([
      "Your conversation",
      "Meal chat",
      "Grocery estimate",
    ]);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
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
    expect(buttonNamed(renderer.container, "Build my estimate").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Bean tacos for two").disabled).toBe(true);
    expect(
      (screen.getByRole("group", { name: "Budget and meals" }) as HTMLFieldSetElement).disabled,
    ).toBe(true);
    expect(childText(renderer.container)).toContain("Previous estimate");
    expect(childText(renderer.container)).toContain("$17.03");
    const box = screen.getByLabelText(/black beans/i, { selector: 'input[id="pantry-black_beans"]' });
    act(() => {
      fireEvent.click(box);
    });
    expect(togglePantry).toHaveBeenCalledWith("black_beans");
    expect(childText(renderer.container)).toContain("$17.03");
    expect(buttonNamed(renderer.container, "Rebuild estimate").disabled).toBe(true);
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
    expect(buttonNamed(renderer.container, "Rebuild estimate").disabled).toBe(false);
    expect(childText(renderer.container)).toContain("$17.03");
    act(() => {
      fireEvent.click(buttonNamed(renderer.container, "Rebuild estimate"));
    });
    expect(submitForm).toHaveBeenCalledTimes(1);
    act(() => {
      fireEvent.click(
        screen.getByLabelText(/black beans/i, { selector: 'input[id="pantry-black_beans"]' }),
      );
    });
    expect(togglePantry).toHaveBeenCalledWith("black_beans");
    expect(submitForm).toHaveBeenCalledTimes(1);
    expect(childText(renderer.container)).toContain("$17.03");
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
    expect(buttonNamed(renderer.container, "Rebuild estimate").disabled).toBe(true);
    expect(submitForm).not.toHaveBeenCalled();
    expect(childText(renderer.container)).toContain("$17.03");
    renderer.unmount();
  });

  it("wires example, retry, and new-request actions", () => {
    const example = vi.fn();
    const retry = vi.fn();
    const newRequest = vi.fn();
    const ready = mount(demoState({ example, retry, newRequest }));
    act(() => {
      fireEvent.click(buttonNamed(ready.container, "Bean tacos for two"));
    });
    expect(example).toHaveBeenCalledWith("beans");
    ready.unmount();
    const retryView = mount(
      demoState({ example, retry, newRequest, error: "The grocery request failed." }),
    );
    act(() => {
      fireEvent.click(buttonNamed(retryView.container, "Retry request"));
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
      fireEvent.click(buttonNamed(failed.container, "Start a new request"));
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
    expect(buttonNamed(renderer.container, "Start a new request").disabled).toBe(true);
    expect(newRequest).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("shows named exclusion reject text on the conversation status", () => {
    const renderer = mount(
      demoState({
        config: demoConfig,
        job: {
          id: "job-3",
          status: "failed",
          result: null,
          error_code: "exclusion_reject",
          error_detail: { recipe_id: "lentil_soup", ingredient_id: "black_beans" },
        },
      }),
    );
    const status = within(screen.getByRole("region", { name: "Your conversation" })).getByRole(
      "status",
    );
    expect(childText(status)).toBe(
      "The grocery request failed. Lentil soup needs black beans, which is excluded. Clear the black beans exclusion or choose another meal, then rebuild.",
    );
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
    const retryButton = buttonNamed(renderer.container, "Retry request");
    expect(retryButton.disabled).toBe(false);
    act(() => {
      fireEvent.click(retryButton);
    });
    expect(retry).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("shows meal chat and disables the form while chat is pending", () => {
    const renderer = mount(demoState(), chatState({ pending: true, message: "Plan tacos" }));
    expect(childText(renderer.container)).toContain("Meal chat");
    expect(childText(renderer.container)).toContain("Your request is in progress.");
    expect(buttonNamed(renderer.container, "Build my estimate").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Bean tacos for two").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Send").disabled).toBe(true);
    expect(
      (screen.getByRole("group", { name: "Budget and meals" }) as HTMLFieldSetElement).disabled,
    ).toBe(true);
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
    expect(childText(renderer.container)).toContain("$17.03");
    expect(childText(renderer.container)).toContain(NOTICE);
    expect(childText(renderer.container)).toContain("Plan warning");
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
    expect(childText(renderer.container)).toContain(PROVIDER_UNAVAILABLE);
    expect(childText(renderer.container)).toContain("Meal chat is unavailable.");
    expect(childText(renderer.container).toLowerCase()).not.toContain("chat is connected");
    act(() => {
      fireEvent.click(buttonNamed(renderer.container, "Retry provider status"));
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
    expect(childText(renderer.container)).toContain(REBUILD_CHAT_GUIDANCE);
    expect(buttonNamed(renderer.container, "Send").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Rebuild estimate").disabled).toBe(false);
    expect(buttonNamed(renderer.container, "Build my estimate").disabled).toBe(false);
    act(() => {
      fireEvent.click(buttonNamed(renderer.container, "Rebuild estimate"));
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
    expect(buttonNamed(renderer.container, "Send").disabled).toBe(true);
    expect(buttonNamed(renderer.container, "Retry the same request").disabled).toBe(false);
    const chatForm = buttonNamed(renderer.container, "Send").closest("form");
    if (chatForm === null) {
      throw new Error("missing Send form");
    }
    expect((within(chatForm).getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    expect(childText(renderer.container)).not.toContain(REBUILD_CHAT_GUIDANCE);
    act(() => {
      fireEvent.click(buttonNamed(renderer.container, "Retry the same request"));
    });
    expect(retry).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("keeps chat-first send when no saved plan owns the form", () => {
    const renderer = mount(
      demoState({ form: { ...initialForm(), pantry: ["black_beans"] } }),
      chatState({ message: "Plan bean tacos for two." }),
    );
    expect(childText(renderer.container)).not.toContain(REBUILD_CHAT_GUIDANCE);
    expect(buttonNamed(renderer.container, "Send").disabled).toBe(false);
    renderer.unmount();
  });

  it("shows Create shopping list for a succeeded accepted estimate when Instacart is configured", () => {
    const renderer = mount(demoState({ job: succeededJob }), chatState(), instacartProviders());
    expect(hasButton(renderer.container, "Create shopping list")).toBe(true);
    expect(childText(renderer.container)).toContain("No purchases are made here.");
    renderer.unmount();
  });

  it("hides start and shopping links when Instacart is not configured", () => {
    const renderer = mount(demoState({ job: succeededJob }));
    expect(hasButton(renderer.container, "Create shopping list")).toBe(false);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(childText(renderer.container)).not.toContain("Open shopping list");
    renderer.unmount();
  });

  it.each(["succeeded", "uncertain"] as const)(
    "hides a stale %s handoff until Instacart is configured",
    (state) => {
      const url = "https://www.instacart.com/store/lists/demo?retailer_key=abc";
      const handoff = handoffState({
        view: {
          id: "00000000-0000-0000-0000-000000000001",
          state,
          attempts: 1,
          url: state === "succeeded" ? url : null,
          error_code: state === "uncertain" ? "invalid_cached_url" : null,
          expires_at: "2026-09-06T15:00:00+00:00",
          retry_allowed: state === "uncertain",
        },
      });
      const renderer = mount(demoState({ job: succeededJob }), chatState(), undefined, handoff);
      expect(renderer.container.querySelector(".handoff-controls")).toBeNull();
      expect(hasButton(renderer.container, "Create shopping list")).toBe(false);
      expect(hasButton(renderer.container, "Retry shopping list")).toBe(false);
      expect(screen.queryByRole("link", { name: "Open shopping list" })).toBeNull();
      expect(handoff.start).not.toHaveBeenCalled();
      expect(handoff.retry).not.toHaveBeenCalled();

      vi.mocked(useProviderCapabilities).mockReturnValue(instacartProviders());
      renderer.rerender(createElement(App));
      if (state === "succeeded") {
        expect(screen.getByRole("link", { name: "Open shopping list" }).getAttribute("href")).toBe(
          url,
        );
      } else {
        expect(childText(renderer.container)).toContain(
          "The shopping link is uncertain. Retry only if you choose to.",
        );
        fireEvent.click(buttonNamed(renderer.container, "Retry shopping list"));
        expect(handoff.retry).toHaveBeenCalledTimes(1);
      }
      expect(handoff.start).not.toHaveBeenCalled();

      vi.mocked(useProviderCapabilities).mockReturnValue({
        ...instacartProviders(),
        capabilities: providersReady,
      });
      renderer.rerender(createElement(App));
      expect(renderer.container.querySelector(".handoff-controls")).toBeNull();
      expect(hasButton(renderer.container, "Retry shopping list")).toBe(false);
      expect(screen.queryByRole("link", { name: "Open shopping list" })).toBeNull();
      renderer.unmount();
    },
  );

  it("hides start when the estimate is dirty", () => {
    const renderer = mount(
      demoState({ job: succeededJob, dirty: true }),
      chatState(),
      instacartProviders(),
    );
    expect(hasButton(renderer.container, "Create shopping list")).toBe(false);
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
    expect(hasButton(renderer.container, "Create shopping list")).toBe(false);
    renderer.unmount();
  });

  it("opens consent before starting handoff with the succeeded job id", () => {
    const start = vi.fn(async () => undefined);
    const renderer = mount(
      demoState({ job: succeededJob }),
      chatState(),
      instacartProviders(),
      handoffState({ start }),
    );
    act(() => {
      fireEvent.click(buttonNamed(renderer.container, "Create shopping list"));
    });
    expect(start).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Create shopping list?" })).toBeTruthy();
    const confirm = buttonNamed(renderer.container, "Confirm shopping list");
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(start).toHaveBeenCalledTimes(1);
    expect(start).toHaveBeenCalledWith("job-1");
    expect(screen.queryByRole("dialog")).toBeNull();
    renderer.unmount();
  });

  it.each(["Cancel", "Escape"])("does not start handoff after %s", (action) => {
    const handoff = handoffState();
    const renderer = mount(
      demoState({ job: succeededJob }),
      chatState(),
      instacartProviders(),
      handoff,
    );
    const trigger = buttonNamed(renderer.container, "Create shopping list");
    fireEvent.click(trigger);
    if (action === "Cancel") {
      fireEvent.click(buttonNamed(renderer.container, "Cancel"));
    } else {
      fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    }
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(handoff.start).not.toHaveBeenCalled();
  });

  it.each([
    "provider disabled",
    "provider pending",
    "provider error",
    "catalog blocked",
    "dirty",
    "busy",
    "unaccepted",
    "no price",
    "all pantry",
    "new job",
    "changed plan",
  ])("closes consent and rejects stale confirmation after %s", (change) => {
    const handoff = handoffState();
    const demo = demoState({ job: succeededJob });
    const provider = instacartProviders();
    const renderer = mount(demo, chatState(), provider, handoff);
    fireEvent.click(buttonNamed(renderer.container, "Create shopping list"));
    const staleConfirm = buttonNamed(renderer.container, "Confirm shopping list");
    const result = succeededJob.result;
    if (result === null) {
      throw new Error("missing succeeded job result");
    }
    switch (change) {
      case "provider disabled":
        provider.capabilities = providersReady;
        break;
      case "provider pending":
        provider.pending = true;
        break;
      case "provider error":
        provider.error = PROVIDER_UNAVAILABLE;
        break;
      case "catalog blocked":
        demo.configError = CATALOG_UNAVAILABLE;
        break;
      case "dirty":
        demo.dirty = true;
        break;
      case "busy":
        demo.pending = true;
        break;
      case "new job":
        demo.job = { ...succeededJob, id: "job-2" };
        break;
      default:
        demo.job = {
          ...succeededJob,
          result: {
            ...result,
            plan: {
              ...result.plan,
              accepted: change !== "unaccepted",
              total_cents: change === "no price" ? null : result.plan.total_cents,
              lines: result.plan.lines.map((line) => ({
                ...line,
                from_pantry: change === "all pantry",
                quantity: change === "changed plan" ? line.quantity + 1 : line.quantity,
              })),
            },
          },
        };
    }
    vi.mocked(useGroceryDemo).mockReturnValue(demo);
    vi.mocked(useProviderCapabilities).mockReturnValue(provider);
    renderer.rerender(createElement(App));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(staleConfirm);
    expect(handoff.start).not.toHaveBeenCalled();
    vi.mocked(useGroceryDemo).mockReturnValue(demoState({ job: succeededJob }));
    vi.mocked(useProviderCapabilities).mockReturnValue(instacartProviders());
    renderer.rerender(createElement(App));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("marks an unresolved chat estimate as previous and hides shopping start", () => {
    const live = render(createElement(AppUnresolvedHost, { chat: chatState() }));
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
            hasRequest: true,
          }),
        }),
      );
    });
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [
              { id: "user-1", role: "user", content: "Plan lentil soup." },
              { id: "chat-1", role: "assistant", content: "Bean tacos fit the budget." },
            ],
            job: chatJob(plannedChat()),
            hasRequest: true,
          }),
        }),
      );
    });
    expect(childText(live.container)).toContain("Grocery estimate");
    expect(childText(live.container)).toContain("$17.03");
    expect(hasButton(live.container, "Create shopping list")).toBe(true);
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [
              { id: "user-1", role: "user", content: "Plan lentil soup." },
              { id: "user-2", role: "user", content: "Add soup." },
            ],
            job: {
              id: "chat-2",
              status: "succeeded",
              result: {
                ...plannedChat(),
                status: "clarification",
                answer: "Which meals should I plan?",
                plan: null,
                budget: null,
                request: null,
                evidence_revision_id: null,
              },
              error_code: null,
            },
            hasRequest: true,
          }),
        }),
      );
    });
    expect(childText(live.container)).toContain("Previous estimate");
    expect(childText(live.container)).toContain("$17.03");
    expect(hasButton(live.container, "Create shopping list")).toBe(false);
    live.unmount();
  });

  it("shows a missing-price clarification candidate as the current grocery estimate", () => {
    const live = render(createElement(AppUnresolvedHost, { chat: chatState() }));
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
            hasRequest: true,
          }),
        }),
      );
    });
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [
              { id: "user-1", role: "user", content: "Plan lentil soup." },
              { id: "chat-1", role: "assistant", content: "Bean tacos fit the budget." },
            ],
            job: chatJob(plannedChat()),
            hasRequest: true,
          }),
        }),
      );
    });
    expect(childText(live.container)).toContain("Grocery estimate");
    expect(childText(live.container)).toContain("$17.03");
    const priced = plannedChat();
    if (priced.plan === null) {
      throw new Error("missing planned chat plan");
    }
    const pricedPlan = priced.plan;
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [
              { id: "user-1", role: "user", content: "Plan lentil soup." },
              { id: "user-2", role: "user", content: "Add soup." },
              { id: "chat-2", role: "assistant", content: "Which meals should I plan?" },
            ],
            job: {
              id: "chat-2",
              status: "succeeded",
              result: {
                ...priced,
                status: "clarification",
                answer: "Which meals should I plan?",
                plan: {
                  ...pricedPlan,
                  total_cents: null,
                  accepted: false,
                  lines: pricedPlan.lines.map((line) => ({ ...line, cost_cents: null })),
                },
              },
              error_code: null,
            },
            hasRequest: true,
          }),
        }),
      );
    });
    expect(childText(live.container)).toContain("Grocery estimate");
    expect(childText(live.container)).not.toContain("Previous estimate");
    expect(childText(live.container)).toContain("This plan is incomplete.");
    expect(childText(live.container)).toContain("Incomplete estimate");
    expect(childText(live.container)).toContain("black beans");
    expect(hasButton(live.container, "Create shopping list")).toBe(false);
    live.unmount();
  });

  it("clears Previous after a newer manual rebuild started after a no-plan clarification", () => {
    const clarification = chatState({
      messages: [
        { id: "user-1", role: "user", content: "Plan lentil soup." },
        { id: "user-2", role: "user", content: "Add soup." },
      ],
      job: {
        id: "chat-2",
        status: "succeeded",
        result: {
          ...plannedChat(),
          status: "clarification",
          answer: "Which meals should I plan?",
          plan: null,
          budget: null,
          request: null,
          evidence_revision_id: null,
        },
        error_code: null,
      },
      hasRequest: true,
    });
    const live = render(createElement(AppUnresolvedHost, { chat: chatState() }));
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [{ id: "user-1", role: "user", content: "Plan lentil soup." }],
            hasRequest: true,
          }),
        }),
      );
    });
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: chatState({
            messages: [
              { id: "user-1", role: "user", content: "Plan lentil soup." },
              { id: "chat-1", role: "assistant", content: "Bean tacos fit the budget." },
            ],
            job: chatJob(plannedChat()),
            hasRequest: true,
          }),
        }),
      );
    });
    act(() => {
      live.rerender(createElement(AppUnresolvedHost, { chat: clarification }));
    });
    expect(childText(live.container)).toContain("Previous estimate");
    expect(hasButton(live.container, "Create shopping list")).toBe(false);
    act(() => {
      live.rerender(createElement(AppUnresolvedHost, { chat: clarification, pending: true }));
    });
    act(() => {
      live.rerender(
        createElement(AppUnresolvedHost, {
          chat: clarification,
          pending: false,
          job: succeededJob,
        }),
      );
    });
    expect(childText(live.container)).toContain("Grocery estimate");
    expect(childText(live.container)).not.toContain("Previous estimate");
    live.unmount();
  });

  it("mounts meal ideas on the budget form with the form setter and busy or blocked disable", () => {
    const setForm = vi.fn();
    const form: FormState = {
      monthly: "300",
      cap: "25.00",
      diet: "vegan",
      pantry: ["black_beans"],
      exclusions: ["black_beans"],
      meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    };
    const ready = mount(
      demoState({ setForm, form }),
      chatState(),
      {
        capabilities: providersReady,
        pending: false,
        error: null,
        retry: vi.fn(),
      },
      handoffState(),
      templateState({
        suggestions: [
          {
            template_id: "bean_lentil",
            recipe_ids: ["bean_tacos", "lentil_soup"],
            servings: 4,
            total_cents: 1703,
            catalog_version: "sample-prices-v1",
            notice: NOTICE,
          },
        ],
      }),
    );
    const budgetForm = buttonNamed(ready.container, "Build my estimate").closest("form");
    if (budgetForm === null) {
      throw new Error("missing Build my estimate form");
    }
    const find = buttonNamed(budgetForm, "Find meal ideas");
    expect(mealIdeas(budgetForm).disabled).toBe(false);
    expect(find.getAttribute("type")).toBe("button");
    expect(find).toBe(buttonNamed(ready.container, "Find meal ideas"));
    expect((within(budgetForm).getByLabelText("Servings per meal") as HTMLSelectElement).value).toBe("2");
    act(() => {
      fireEvent.click(buttonNamed(budgetForm, "Use these meals: Bean tacos, Lentil soup"));
    });
    expect(setForm).toHaveBeenCalledTimes(1);
    const updater = setForm.mock.calls[0]?.[0];
    if (typeof updater !== "function") {
      throw new Error("expected demo.setForm updater");
    }
    const meals = [
      { recipe_id: "bean_tacos", servings: 4 },
      { recipe_id: "lentil_soup", servings: 4 },
    ];
    const next = updater(form) as FormState;
    expect(next.monthly).toBe("300");
    expect(next.cap).toBe("25.00");
    expect(next.diet).toBe("vegan");
    expect(next.pantry).toEqual(["black_beans"]);
    expect(next.exclusions).toEqual(["black_beans"]);
    expect(next.meals).toEqual(meals);
    const current: FormState = {
      monthly: "80",
      cap: "10.00",
      diet: "omnivore",
      pantry: [],
      exclusions: [],
      meals: [{ recipe_id: "lentil_soup", servings: 8 }],
    };
    expect(updater(current)).toEqual({ ...current, meals });
    ready.unmount();
    const busy = mount(demoState({ setForm, pending: true }));
    expect(mealIdeas(busy.container).disabled).toBe(true);
    busy.unmount();
    const chatBusy = mount(demoState({ setForm }), chatState({ pending: true }));
    expect(mealIdeas(chatBusy.container).disabled).toBe(true);
    chatBusy.unmount();
    const blocked = mount(demoState({ setForm, configError: CATALOG_UNAVAILABLE }));
    expect(mealIdeas(blocked.container).disabled).toBe(true);
    blocked.unmount();
  });
});
