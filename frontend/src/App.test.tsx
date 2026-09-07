/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryConfig, type GroceryJob } from "./apiTypes";
import { initialForm } from "./BudgetForm";
import { useGroceryDemo, type GroceryDemo } from "./useGroceryDemo";

vi.mock("./useGroceryDemo", () => ({
  useGroceryDemo: vi.fn(),
}));

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const CATALOG_UNAVAILABLE = "The grocery catalog is unavailable. Retry the catalog request.";

const demoConfig: GroceryConfig = {
  budget_period: "2026-09-01",
  source: "fixture",
  posted_cents: 1200,
  pending_cents: -50,
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

function mount(demo: GroceryDemo): ReactTestRenderer {
  vi.mocked(useGroceryDemo).mockReturnValue(demo);
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
    expect(renderer.root.findAllByType("form")).toHaveLength(0);
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
    const onSubmit = renderer.root.findByType("form").props.onSubmit as (event: {
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
});
