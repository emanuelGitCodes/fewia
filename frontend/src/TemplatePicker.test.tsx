/** @vitest-environment jsdom */

import { createElement, type Dispatch, type SetStateAction } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import {
  HTTP_ERROR,
  SAMPLE_ESTIMATE_NOTICE,
  SHAPE_ERROR,
  type GroceryConfig,
} from "./apiTypes";
import { initialForm, type FormState } from "./BudgetForm";
import { fetchTemplates, type TemplateRequest, type TemplateSuggestions } from "./templateApi";
import { TemplatePicker } from "./TemplatePicker";

vi.mock("./templateApi", () => ({
  fetchTemplates: vi.fn(),
}));

const PERIOD = "2026-09-01";
const CATALOG = "sample-prices-v1";
const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const AMOUNT_ERROR = "Enter a non-negative dollar amount with at most two decimal places.";
const GUIDANCE = "Use Build my estimate after choosing meals.";
const RAW = "do-not-echo-this";

function groceryConfig(overrides: Partial<GroceryConfig> = {}): GroceryConfig {
  return {
    budget_period: PERIOD,
    source: "fixture",
    catalog_version: CATALOG,
    posted_cents: 1200,
    pending_cents: -50,
    spending_refreshed_at: "2026-09-07T16:00:00Z",
    notice: NOTICE,
    recipes: [
      { id: "bean_tacos", name: "Bean tacos" },
      { id: "lentil_soup", name: "Lentil soup" },
    ],
    ingredients: [{ id: "black_beans", name: "black beans" }],
    ...overrides,
  };
}

function formState(overrides: Partial<FormState> = {}): FormState {
  return {
    ...initialForm(),
    monthly: "300",
    cap: "40",
    diet: "vegan",
    pantry: ["black_beans"],
    exclusions: ["black_beans"],
    meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    ...overrides,
  };
}

function payload(overrides: Partial<TemplateSuggestions> = {}): TemplateSuggestions {
  return {
    budget_period: PERIOD,
    spending_source: "fixture",
    budget: { available_cents: 5000, pending_cents: 200, stale: false, warnings: [] },
    catalog_version: CATALOG,
    notice: NOTICE,
    suggestions: [
      {
        template_id: "bean_lentil",
        recipe_ids: ["bean_tacos", "lentil_soup"],
        servings: 2,
        total_cents: 1703,
        catalog_version: CATALOG,
        notice: NOTICE,
      },
    ],
    ...overrides,
  };
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

type FormSetter = Dispatch<SetStateAction<FormState>>;

type Mounted = {
  view: RenderResult;
  onChange: Mock<FormSetter>;
};

function mount(
  form: FormState = formState(),
  config: GroceryConfig = groceryConfig(),
  disabled = false,
  onChange: Mock<FormSetter> = vi.fn<FormSetter>(),
): Mounted {
  const view = render(
    createElement(TemplatePicker, { config, form, onChange, disabled }),
  );
  return { view, onChange };
}

function findButton(root: HTMLElement): HTMLButtonElement {
  return within(root).getByRole("button", { name: "Find meal ideas" }) as HTMLButtonElement;
}

function mealIdeas(root: HTMLElement): HTMLFieldSetElement {
  return within(root).getByRole("group", { name: "Meal ideas" }) as HTMLFieldSetElement;
}

function clickFind(root: HTMLElement): void {
  fireEvent.click(findButton(root));
}

afterEach(() => {
  cleanup();
  vi.mocked(fetchTemplates).mockReset();
});

describe("TemplatePicker", () => {
  beforeEach(() => {
    vi.mocked(fetchTemplates).mockReset();
  });

  it("does not fetch on mount or when servings change", () => {
    const { view } = mount();
    expect(fetchTemplates).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Servings per meal"), { target: { value: "4" } });
    expect(fetchTemplates).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Servings per meal") as HTMLSelectElement).value).toBe("4");
    view.unmount();
  });

  it("sends the current restrictions after an explicit click", async () => {
    const form = formState();
    const config = groceryConfig();
    const { view } = mount(form, config);
    fireEvent.change(screen.getByLabelText("Servings per meal"), { target: { value: "4" } });
    vi.mocked(fetchTemplates).mockResolvedValueOnce(payload({ suggestions: [] }));
    await act(async () => {
      clickFind(view.container);
    });
    expect(fetchTemplates).toHaveBeenCalledTimes(1);
    const request = vi.mocked(fetchTemplates).mock.calls[0]?.[0] as TemplateRequest;
    expect(request).toEqual({
      budget_period: PERIOD,
      monthly_limit_cents: 30000,
      plan_cap_cents: 4000,
      servings: 4,
      diet: "vegan",
      pantry_ingredients: ["black_beans"],
      ingredient_exclusions: ["black_beans"],
    });
    expect(vi.mocked(fetchTemplates).mock.calls[0]?.[1]).toBe(config);
    expect(vi.mocked(fetchTemplates).mock.calls[0]?.[2]).toBeInstanceOf(AbortSignal);
    expect(request).not.toHaveProperty("meals");
    view.unmount();
  });

  it("shows a local money error without fetching", () => {
    const { view } = mount(formState({ monthly: "nope" }));
    act(() => {
      clickFind(view.container);
    });
    expect(fetchTemplates).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe(AMOUNT_ERROR);
    expect(screen.getByRole("alert").textContent).not.toContain(RAW);
    view.unmount();
  });

  it("shows a retryable static network error and hides raw text", async () => {
    const { view } = mount();
    vi.mocked(fetchTemplates).mockRejectedValueOnce(new Error(RAW));
    await act(async () => {
      clickFind(view.container);
    });
    expect(screen.getByRole("alert").textContent).toBe(HTTP_ERROR);
    expect(view.container.textContent).not.toContain(RAW);
    vi.mocked(fetchTemplates).mockResolvedValueOnce(payload({ suggestions: [] }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Retry meal ideas" }));
    });
    expect(fetchTemplates).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status").textContent).toBe(
      "No meal idea fits these restrictions. Choose meals manually.",
    );
    view.unmount();
  });

  it("shows a static shape error on retryable failure", async () => {
    const { view } = mount();
    vi.mocked(fetchTemplates).mockRejectedValueOnce(new Error(SHAPE_ERROR));
    await act(async () => {
      clickFind(view.container);
    });
    expect(screen.getByRole("alert").textContent).toBe(SHAPE_ERROR);
    view.unmount();
  });

  it("renders suggestions and applies meals while preserving restrictions", async () => {
    const form = formState();
    const { view, onChange } = mount(form);
    vi.mocked(fetchTemplates).mockResolvedValueOnce(payload());
    await act(async () => {
      clickFind(view.container);
    });
    expect(view.container.textContent).toContain("Bean tacos, Lentil soup");
    expect(view.container.textContent).toContain("2 servings");
    expect(view.container.textContent).toContain("$17.03");
    expect(view.container.textContent).toContain(NOTICE);
    const use = screen.getByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" });
    act(() => {
      fireEvent.click(use);
    });
    expect(onChange).toHaveBeenCalledTimes(1);
    const updater = onChange.mock.calls[0]?.[0] as (current: FormState) => FormState;
    const next = updater(form);
    expect(next).toEqual({
      ...form,
      meals: [
        { recipe_id: "bean_tacos", servings: 2 },
        { recipe_id: "lentil_soup", servings: 2 },
      ],
    });
    expect(screen.getByText(GUIDANCE)).toBeTruthy();
    view.rerender(
      createElement(TemplatePicker, { config: groceryConfig(), form: next, onChange, disabled: false }),
    );
    expect(screen.queryByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeNull();
    expect(screen.getByText(GUIDANCE)).toBeTruthy();
    expect(fetchTemplates).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("clears results and aborts when the form, servings, or config change", async () => {
    const hung = deferred<TemplateSuggestions>();
    let signal: AbortSignal | undefined;
    vi.mocked(fetchTemplates).mockImplementation(
      async (_request: TemplateRequest, _config: GroceryConfig, next?: AbortSignal) => {
        signal = next;
        return hung.promise;
      },
    );
    const form = formState();
    const config = groceryConfig();
    const onChange = vi.fn<FormSetter>();
    const view = render(createElement(TemplatePicker, { config, form, onChange, disabled: false }));
    act(() => {
      clickFind(view.container);
    });
    expect(screen.getByRole("status").textContent).toBe("Finding meal ideas.");
    view.rerender(
      createElement(TemplatePicker, { config, form: { ...form, monthly: "200" }, onChange, disabled: false }),
    );
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByRole("status")).toBeNull();
    await act(async () => {
      hung.resolve(payload());
    });
    expect(screen.queryByText("Bean tacos, Lentil soup")).toBeNull();
    expect(screen.queryByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeNull();
    view.unmount();
  });

  it("drops a completed list when servings or catalog context change", async () => {
    const form = formState();
    const config = groceryConfig();
    const onChange = vi.fn<FormSetter>();
    const view = render(createElement(TemplatePicker, { config, form, onChange, disabled: false }));
    vi.mocked(fetchTemplates).mockResolvedValueOnce(payload());
    await act(async () => {
      clickFind(view.container);
    });
    expect(screen.getByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Servings per meal"), { target: { value: "8" } });
    expect(screen.queryByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeNull();
    vi.mocked(fetchTemplates).mockResolvedValueOnce(payload());
    await act(async () => {
      clickFind(view.container);
    });
    view.rerender(
      createElement(TemplatePicker, {
        config: groceryConfig({ catalog_version: "other" }),
        form,
        onChange,
        disabled: false,
      }),
    );
    expect(screen.queryByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeNull();
    view.unmount();
  });

  it("does not display or apply a late response after unmount", async () => {
    const hung = deferred<TemplateSuggestions>();
    vi.mocked(fetchTemplates).mockReturnValueOnce(hung.promise);
    const { view, onChange } = mount();
    act(() => {
      clickFind(view.container);
    });
    view.unmount();
    await act(async () => {
      hung.resolve(payload());
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByText("Bean tacos, Lentil soup")).toBeNull();
  });

  it("disables picking while blocked and does not fetch", () => {
    const { view } = mount(formState(), groceryConfig(), true);
    expect(mealIdeas(view.container).disabled).toBe(true);
    act(() => {
      clickFind(view.container);
    });
    expect(fetchTemplates).not.toHaveBeenCalled();
    view.unmount();
  });

  it("drops suggestions when posted spending changes", async () => {
    const form = formState();
    const config = groceryConfig();
    const onChange = vi.fn<FormSetter>();
    const view = render(createElement(TemplatePicker, { config, form, onChange, disabled: false }));
    vi.mocked(fetchTemplates).mockResolvedValueOnce(payload());
    await act(async () => {
      clickFind(view.container);
    });
    expect(screen.getByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeTruthy();
    view.rerender(
      createElement(TemplatePicker, {
        config: groceryConfig({ posted_cents: 50 }),
        form,
        onChange,
        disabled: false,
      }),
    );
    expect(screen.queryByRole("button", { name: "Use these meals: Bean tacos, Lentil soup" })).toBeNull();
    expect(screen.getByText(GUIDANCE)).toBeTruthy();
    view.unmount();
  });
});
