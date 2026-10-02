/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR, type GroceryConfig } from "./apiTypes";
import { initialForm, type FormState } from "./BudgetForm";
import { parseDollars } from "./money";
import {
  fetchTemplates,
  type TemplateSuggestion,
  type TemplateSuggestions,
} from "./templateApi";
import { useTemplateSuggestions } from "./useTemplateSuggestions";

vi.mock("./templateApi", () => ({
  fetchTemplates: vi.fn(),
}));

const RAW = "do-not-echo-this";
const NOTICE = SAMPLE_ESTIMATE_NOTICE;

function amountError(): string {
  try {
    parseDollars("nope");
  } catch (caught: unknown) {
    if (caught instanceof Error) {
      return caught.message;
    }
  }
  throw new Error("parseDollars did not throw");
}

function groceryConfig(overrides: Partial<GroceryConfig> = {}): GroceryConfig {
  return {
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
    ...overrides,
  };
}

function formState(overrides: Partial<FormState> = {}): FormState {
  return {
    ...initialForm(),
    pantry: ["black_beans"],
    exclusions: [],
    ...overrides,
  };
}

function suggestion(overrides: Partial<TemplateSuggestion> = {}): TemplateSuggestion {
  return {
    template_id: "bean_lentil",
    recipe_ids: ["bean_tacos", "lentil_soup"],
    servings: 2,
    total_cents: 400,
    catalog_version: "sample-prices-v1",
    notice: NOTICE,
    ...overrides,
  };
}

function suggestionsResult(
  items: TemplateSuggestion[] = [suggestion()],
): TemplateSuggestions {
  return {
    budget_period: "2026-09-01",
    spending_source: "fixture",
    budget: {
      available_cents: 5000,
      pending_cents: 200,
      stale: false,
      warnings: ["cap applied"],
    },
    catalog_version: "sample-prices-v1",
    notice: NOTICE,
    suggestions: items,
  };
}

type HookProps = {
  config: GroceryConfig;
  form: FormState;
  servings: number;
};

function mount(props: HookProps = { config: groceryConfig(), form: formState(), servings: 2 }) {
  return renderHook(
    ({ config, form, servings }: HookProps) => useTemplateSuggestions(config, form, servings),
    { initialProps: props },
  );
}

function fetchMock(): ReturnType<typeof vi.mocked<typeof fetchTemplates>> {
  return vi.mocked(fetchTemplates);
}

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useTemplateSuggestions", () => {
  afterEach(() => {
    cleanup();
    fetchMock().mockReset();
    vi.restoreAllMocks();
  });

  it("returns empty state and does not request until find runs", () => {
    const { result, unmount } = mount();
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.suggestions).toBeNull();
    expect(fetchMock()).not.toHaveBeenCalled();
    unmount();
  });

  it("sends current budget inputs on find and omits meal rows", async () => {
    fetchMock().mockResolvedValue(suggestionsResult());
    const form = formState({
      monthly: "100",
      cap: "",
      diet: "vegetarian",
      pantry: ["black_beans"],
      exclusions: ["black_beans"],
      meals: [{ recipe_id: "lentil_soup", servings: 8 }],
    });
    const config = groceryConfig();
    const { result, unmount } = mount({ config, form, servings: 3 });
    await act(async () => {
      result.current.find();
    });
    await flush();
    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(fetchMock().mock.calls[0]?.[0]).toEqual({
      budget_period: "2026-09-01",
      monthly_limit_cents: 10000,
      plan_cap_cents: null,
      servings: 3,
      diet: "vegetarian",
      pantry_ingredients: ["black_beans"],
      ingredient_exclusions: ["black_beans"],
    });
    expect(fetchMock().mock.calls[0]?.[1]).toBe(config);
    expect(fetchMock().mock.calls[0]?.[0]).not.toHaveProperty("meals");
    expect(JSON.stringify(fetchMock().mock.calls[0]?.[0])).not.toContain("lentil_soup");
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.suggestions).toEqual([suggestion()]);
    unmount();
  });

  it("keeps the parseDollars message for invalid money and skips the request", async () => {
    const { result, unmount } = mount({
      config: groceryConfig(),
      form: formState({ monthly: "12.345" }),
      servings: 2,
    });
    await act(async () => {
      result.current.find();
    });
    expect(fetchMock()).not.toHaveBeenCalled();
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe(amountError());
    expect(result.current.suggestions).toBeNull();
    unmount();
    const cap = mount({
      config: groceryConfig(),
      form: formState({ cap: "1.239" }),
      servings: 2,
    });
    await act(async () => {
      cap.result.current.find();
    });
    expect(fetchMock()).not.toHaveBeenCalled();
    expect(cap.result.current.error).toBe(amountError());
    cap.unmount();
  });

  it("maps network and unknown failures to HTTP_ERROR and hides raw details", async () => {
    fetchMock().mockRejectedValueOnce(new Error(RAW)).mockRejectedValueOnce("nope");
    const props = { config: groceryConfig(), form: formState(), servings: 2 };
    const first = mount(props);
    await act(async () => {
      first.result.current.find();
    });
    await flush();
    expect(first.result.current.error).toBe(HTTP_ERROR);
    expect(first.result.current.error).not.toContain(RAW);
    expect(first.result.current.suggestions).toBeNull();
    first.unmount();
    const second = mount(props);
    await act(async () => {
      second.result.current.find();
    });
    await flush();
    expect(second.result.current.error).toBe(HTTP_ERROR);
    expect(second.result.current.pending).toBe(false);
    second.unmount();
  });

  it("keeps SHAPE_ERROR and treats an empty suggestion list as success", async () => {
    fetchMock()
      .mockRejectedValueOnce(new Error(SHAPE_ERROR))
      .mockResolvedValueOnce(suggestionsResult([]));
    const props = { config: groceryConfig(), form: formState(), servings: 2 };
    const first = mount(props);
    await act(async () => {
      first.result.current.find();
    });
    await flush();
    expect(first.result.current.error).toBe(SHAPE_ERROR);
    expect(first.result.current.suggestions).toBeNull();
    first.unmount();
    const second = mount(props);
    await act(async () => {
      second.result.current.find();
    });
    await flush();
    expect(second.result.current.error).toBeNull();
    expect(second.result.current.suggestions).toEqual([]);
    expect(second.result.current.pending).toBe(false);
    second.unmount();
  });

  it("hides stale state when budget config or form context changes", async () => {
    fetchMock().mockResolvedValue(suggestionsResult());
    const config = groceryConfig();
    const form = formState();
    const { result, rerender, unmount } = mount({ config, form, servings: 2 });
    await act(async () => {
      result.current.find();
    });
    await flush();
    expect(result.current.suggestions).toEqual([suggestion()]);
    rerender({ config: { ...config, posted_cents: 1800 }, form, servings: 2 });
    expect(result.current.suggestions).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(false);
    rerender({ config, form, servings: 2 });
    await act(async () => {
      result.current.find();
    });
    await flush();
    expect(result.current.suggestions).toEqual([suggestion()]);
    rerender({
      config: {
        ...config,
        recipes: config.recipes.map((item) =>
          item.id === "bean_tacos" ? { ...item, name: "Bean tacos v2" } : item,
        ),
      },
      form,
      servings: 2,
    });
    expect(result.current.suggestions).toBeNull();
    rerender({
      config,
      form: { ...form, meals: [{ recipe_id: "lentil_soup", servings: 1 }] },
      servings: 2,
    });
    expect(result.current.suggestions).toBeNull();
    expect(fetchMock()).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("aborts on context change and ignores a late success or failure", async () => {
    const pending = deferred<TemplateSuggestions>();
    let seenSignal: AbortSignal | undefined;
    fetchMock().mockImplementation(async (_request, _config, signal) => {
      seenSignal = signal;
      return pending.promise;
    });
    const config = groceryConfig();
    const form = formState();
    const { result, rerender, unmount } = mount({ config, form, servings: 2 });
    await act(async () => {
      result.current.find();
    });
    expect(result.current.pending).toBe(true);
    rerender({ config: { ...config, catalog_version: "sample-prices-v2" }, form, servings: 2 });
    expect(result.current.pending).toBe(false);
    expect(result.current.suggestions).toBeNull();
    expect(seenSignal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(suggestionsResult());
    });
    expect(result.current.suggestions).toBeNull();
    expect(result.current.error).toBeNull();
    const failed = deferred<TemplateSuggestions>();
    fetchMock().mockImplementation(async (_request, _config, signal) => {
      seenSignal = signal;
      return failed.promise;
    });
    rerender({ config, form, servings: 4 });
    await act(async () => {
      result.current.find();
    });
    rerender({ config, form, servings: 5 });
    expect(seenSignal?.aborted).toBe(true);
    await act(async () => {
      failed.reject(new Error(SHAPE_ERROR));
    });
    expect(result.current.error).toBeNull();
    expect(result.current.suggestions).toBeNull();
    unmount();
  });

  it("aborts on unmount and ignores AbortError", async () => {
    const pending = deferred<TemplateSuggestions>();
    let seenSignal: AbortSignal | undefined;
    fetchMock().mockImplementation(async (_request, _config, signal) => {
      seenSignal = signal;
      return pending.promise;
    });
    const { result, unmount } = mount();
    await act(async () => {
      result.current.find();
    });
    act(() => {
      unmount();
    });
    expect(seenSignal?.aborted).toBe(true);
    await act(async () => {
      pending.reject(new DOMException("Aborted", "AbortError"));
    });
  });
});
