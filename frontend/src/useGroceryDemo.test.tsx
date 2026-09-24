/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  HTTP_ERROR,
  SAMPLE_ESTIMATE_NOTICE,
  type GroceryConfig,
  type GroceryJob,
  type GroceryJobCreate,
} from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import { buildRequest, initialForm } from "./BudgetForm";
import { useGroceryDemo, type GroceryDemo } from "./useGroceryDemo";
import { useGroceryJob } from "./useGroceryJob";

vi.mock("./useGroceryJob", () => ({
  useGroceryJob: vi.fn(),
}));

const CONFIG_MS = 20_000;
const CONFIG_UNAVAILABLE = "The grocery catalog is unavailable. Retry the catalog request.";

const demoConfig: GroceryConfig = {
  budget_period: "2026-09-01",
  source: "fixture",
  catalog_version: "sample-prices-v1",
  posted_cents: 1200,
  pending_cents: -50,
  spending_refreshed_at: "2026-09-07T16:00:00Z",
  notice: SAMPLE_ESTIMATE_NOTICE,
  recipes: [
    { id: "bean_tacos", name: "Bean tacos" },
    { id: "lentil_soup", name: "Lentil soup" },
    { id: "chickpea_curry", name: "Chickpea curry" },
  ],
  ingredients: [{ id: "black_beans", name: "black beans" }],
};

const succeededJob: GroceryJob = {
  id: "job-1",
  status: "succeeded",
  error_code: null,
  result: {
    spending_source: "fixture",
    budget: { available_cents: 5000, pending_cents: 0, stale: false, warnings: [] },
    meal_nutrition: sampleNutrition(),
    plan: {
      lines: [
        {
          ingredient_id: "black_beans",
          name: "black beans",
          unit: "g",
          quantity: 425,
          packages: 1,
          cost_cents: 129,
          from_pantry: false,
        },
      ],
      total_cents: 129,
      accepted: true,
      warnings: [],
      catalog_version: "sample-prices-v1",
      notice: SAMPLE_ESTIMATE_NOTICE,
    },
  },
};

const failedJob: GroceryJob = {
  id: "job-2",
  status: "failed",
  error_code: "tool",
  result: null,
};

function jsonOk(payload: unknown): Response {
  return { ok: true, json: () => Promise.resolve(payload) } as Response;
}

function hungFetch(init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    const signal = init?.signal;
    const fail = (): void => {
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (signal === undefined || signal === null) {
      return;
    }
    if (signal.aborted) {
      fail();
      return;
    }
    signal.addEventListener("abort", fail, { once: true });
  });
}

type JobMocks = {
  job: GroceryJob | null;
  error: string | null;
  pending: boolean;
  submit: ReturnType<typeof vi.fn<(body: GroceryJobCreate) => Promise<void>>>;
  clear: ReturnType<typeof vi.fn<() => void>>;
};

function HookHost(props: { bucket: { current: GroceryDemo | null } }): null {
  props.bucket.current = useGroceryDemo();
  return null;
}

function hookOf(bucket: { current: GroceryDemo | null }): GroceryDemo {
  if (bucket.current === null) {
    throw new Error("hook is not mounted");
  }
  return bucket.current;
}

describe("useGroceryDemo", () => {
  let jobState: JobMocks;

  function bindJob(): void {
    vi.mocked(useGroceryJob).mockImplementation(() => ({
      job: jobState.job,
      error: jobState.error,
      pending: jobState.pending,
      submit: jobState.submit,
      clear: jobState.clear,
    }));
  }

  function mount(): {
    bucket: { current: GroceryDemo | null };
    renderer: ReactTestRenderer;
    refresh: () => void;
  } {
    const bucket: { current: GroceryDemo | null } = { current: null };
    let renderer: ReactTestRenderer | undefined;
    act(() => {
      renderer = create(createElement(HookHost, { bucket }));
    });
    if (renderer === undefined) {
      throw new Error("renderer failed to mount");
    }
    const live = renderer;
    return {
      bucket,
      renderer: live,
      refresh: (): void => {
        act(() => {
          live.update(createElement(HookHost, { bucket }));
        });
      },
    };
  }

  async function flush(): Promise<void> {
    await act(async () => {
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      writable: true,
      value: globalThis,
    });
    vi.useFakeTimers();
    jobState = {
      job: null,
      error: null,
      pending: false,
      submit: vi.fn(async (_body: GroceryJobCreate) => undefined),
      clear: vi.fn(() => undefined),
    };
    bindJob();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonOk(demoConfig)),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads config, keeps the initial form, and hides raw fetch errors", async () => {
    const { bucket, renderer } = mount();
    expect(hookOf(bucket).configPending).toBe(true);
    expect(hookOf(bucket).form).toEqual(initialForm());
    await flush();
    expect(hookOf(bucket).config).toEqual(demoConfig);
    expect(hookOf(bucket).configPending).toBe(false);
    expect(hookOf(bucket).configError).toBeNull();
    expect(hookOf(bucket).dirty).toBe(false);
    renderer.unmount();
  });

  it("retries a failed catalog fetch and uses a static error", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) } as Response)
      .mockResolvedValueOnce(jsonOk(demoConfig));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();
    await flush();
    expect(hookOf(bucket).config).toBeNull();
    expect(hookOf(bucket).configError).toBe(CONFIG_UNAVAILABLE);
    expect(hookOf(bucket).configError).not.toBe(HTTP_ERROR);
    expect(hookOf(bucket).configPending).toBe(false);
    await act(async () => {
      hookOf(bucket).reloadConfig();
    });
    await flush();
    expect(hookOf(bucket).config).toEqual(demoConfig);
    expect(hookOf(bucket).configError).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    renderer.unmount();
  });

  it("aborts an in-flight catalog fetch on unmount and ignores a late response", async () => {
    let seenSignal: AbortSignal | undefined;
    let resolvePost: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        seenSignal = init?.signal ?? undefined;
        return new Promise<Response>((resolve) => {
          resolvePost = resolve;
        });
      }),
    );
    const { bucket, renderer } = mount();
    expect(hookOf(bucket).configPending).toBe(true);
    act(() => {
      renderer.unmount();
    });
    expect(seenSignal?.aborted).toBe(true);
    await act(async () => {
      resolvePost?.(jsonOk(demoConfig));
    });
  });

  it("times out a hung catalog fetch after 20s with the static error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => hungFetch(init)),
    );
    const { bucket, renderer } = mount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CONFIG_MS);
      await Promise.resolve();
    });
    expect(hookOf(bucket).configPending).toBe(false);
    expect(hookOf(bucket).config).toBeNull();
    expect(hookOf(bucket).configError).toBe(CONFIG_UNAVAILABLE);
    renderer.unmount();
  });

  it("aborts a stale catalog fetch when reload starts", async () => {
    let resolveFirst: ((value: Response) => void) | undefined;
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValue(jsonOk(demoConfig));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();
    await act(async () => {
      hookOf(bucket).reloadConfig();
    });
    await flush();
    expect(hookOf(bucket).config).toEqual(demoConfig);
    await act(async () => {
      resolveFirst?.(jsonOk({ ...demoConfig, budget_period: "1999-01-01" }));
    });
    expect(hookOf(bucket).config?.budget_period).toBe("2026-09-01");
    renderer.unmount();
  });

  it("blocks submit without config or while pending and maps domain errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => hungFetch(init)),
    );
    const hung = mount();
    await act(async () => {
      await hookOf(hung.bucket).submitForm();
    });
    expect(jobState.submit).not.toHaveBeenCalled();
    hung.renderer.unmount();

    vi.stubGlobal("fetch", vi.fn(async () => jsonOk(demoConfig)));
    const { bucket, renderer, refresh } = mount();
    await flush();
    jobState.pending = true;
    refresh();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    expect(jobState.submit).not.toHaveBeenCalled();
    jobState.pending = false;
    refresh();
    await act(async () => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, meals: [] });
    });
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    expect(hookOf(bucket).formError).toBe("Choose 1 to 3 meals.");
    expect(jobState.submit).not.toHaveBeenCalled();
    await act(async () => {
      hookOf(bucket).setForm({
        ...initialForm(),
        meals: [{ recipe_id: "bean_tacos", servings: 9 }],
      });
    });
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    expect(hookOf(bucket).formError).toBe("Each meal uses 1 to 8 servings.");
    renderer.unmount();
  });

  it("submits explicit example state and preserves budget and pantry", async () => {
    const { bucket, renderer } = mount();
    await flush();
    await act(async () => {
      hookOf(bucket).setForm({
        ...initialForm(),
        monthly: "250",
        cap: "15",
        pantry: ["black_beans"],
        exclusions: ["black_beans"],
        diet: "vegetarian",
      });
    });
    await act(async () => {
      hookOf(bucket).example("beans");
    });
    expect(hookOf(bucket).form.diet).toBe("omnivore");
    expect(hookOf(bucket).form.meals).toEqual([{ recipe_id: "bean_tacos", servings: 2 }]);
    expect(hookOf(bucket).form.pantry).toEqual(["black_beans"]);
    expect(hookOf(bucket).form.monthly).toBe("250");
    expect(jobState.submit).toHaveBeenCalledWith(
      buildRequest(demoConfig, {
        monthly: "250",
        cap: "15",
        pantry: ["black_beans"],
        exclusions: ["black_beans"],
        diet: "omnivore",
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
      }),
    );
    await act(async () => {
      hookOf(bucket).example("vegan");
    });
    expect(hookOf(bucket).form.diet).toBe("vegan");
    expect(hookOf(bucket).form.meals).toEqual([
      { recipe_id: "bean_tacos", servings: 2 },
      { recipe_id: "lentil_soup", servings: 2 },
      { recipe_id: "chickpea_curry", servings: 2 },
    ]);
    const veganBody = jobState.submit.mock.calls[1]?.[0] as ReturnType<typeof buildRequest>;
    expect(veganBody.request.diet).toBe("vegan");
    expect(veganBody.request.meals).toHaveLength(3);
    expect(veganBody.request.pantry_ingredients).toEqual(["black_beans"]);
    expect(veganBody.monthly_limit_cents).toBe(25000);
    renderer.unmount();
  });

  it("marks pantry and invalid drafts dirty and keeps the server price", async () => {
    const { bucket, renderer, refresh } = mount();
    await flush();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    jobState.job = succeededJob;
    refresh();
    expect(hookOf(bucket).dirty).toBe(false);
    expect(hookOf(bucket).job?.result?.plan.lines[0]?.cost_cents).toBe(129);
    await act(async () => {
      hookOf(bucket).togglePantry("black_beans");
    });
    expect(hookOf(bucket).form.pantry).toEqual(["black_beans"]);
    expect(hookOf(bucket).dirty).toBe(true);
    expect(hookOf(bucket).job).toBe(succeededJob);
    expect(hookOf(bucket).job?.result?.plan.total_cents).toBe(129);
    await act(async () => {
      hookOf(bucket).togglePantry("black_beans");
    });
    expect(hookOf(bucket).dirty).toBe(false);
    await act(async () => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, meals: [] });
    });
    expect(hookOf(bucket).dirty).toBe(true);
    expect(hookOf(bucket).job?.result?.plan.lines[0]?.cost_cents).toBe(129);
    renderer.unmount();
  });

  it("retries the original body after the draft changes", async () => {
    const { bucket, renderer } = mount();
    await flush();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    const original = jobState.submit.mock.calls[0]?.[0];
    await act(async () => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, monthly: "80" });
    });
    expect(hookOf(bucket).dirty).toBe(true);
    act(() => {
      hookOf(bucket).retry();
    });
    expect(jobState.submit).toHaveBeenLastCalledWith(original);
    expect(jobState.submit.mock.calls[1]?.[0]).toBe(original);
    expect(jobState.clear).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("clears the key after a terminal job and keeps it after an ambiguous failure", async () => {
    const { bucket, renderer, refresh } = mount();
    await flush();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    const original = jobState.submit.mock.calls[0]?.[0];
    expect(jobState.clear).not.toHaveBeenCalled();
    jobState.error = HTTP_ERROR;
    refresh();
    await act(async () => {
      hookOf(bucket).setForm({ ...hookOf(bucket).form, monthly: "90" });
    });
    act(() => {
      hookOf(bucket).retry();
    });
    expect(jobState.clear).not.toHaveBeenCalled();
    expect(jobState.submit).toHaveBeenLastCalledWith(original);
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    expect(jobState.clear).not.toHaveBeenCalled();
    const lastCall = jobState.submit.mock.calls[jobState.submit.mock.calls.length - 1]?.[0];
    expect(lastCall).not.toBe(original);
    jobState.job = succeededJob;
    jobState.error = null;
    refresh();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    expect(jobState.clear).toHaveBeenCalledTimes(1);
    jobState.clear.mockClear();
    jobState.job = failedJob;
    refresh();
    act(() => {
      hookOf(bucket).newRequest();
    });
    expect(jobState.clear).toHaveBeenCalledTimes(1);
    expect(jobState.submit.mock.calls.length).toBeGreaterThan(3);
    renderer.unmount();
  });

  it("blocks fresh posts of an old period during reload and keeps retry replay", async () => {
    const nextConfig: GroceryConfig = { ...demoConfig, budget_period: "2026-10-01" };
    let resolveReload: ((value: Response) => void) | undefined;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonOk(demoConfig))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveReload = resolve;
          }),
      )
      .mockResolvedValueOnce(jsonOk(nextConfig));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();
    await flush();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    const original = jobState.submit.mock.calls[0]?.[0];
    expect(original?.request.budget_period).toBe("2026-09-01");

    const expectFreshBlocked = async (): Promise<void> => {
      jobState.submit.mockClear();
      jobState.clear.mockClear();
      await act(async () => {
        await hookOf(bucket).submitForm();
        hookOf(bucket).newRequest();
        hookOf(bucket).example("beans");
      });
      expect(jobState.submit).not.toHaveBeenCalled();
      expect(jobState.clear).not.toHaveBeenCalled();
      act(() => {
        hookOf(bucket).retry();
      });
      expect(jobState.submit).toHaveBeenCalledTimes(1);
      expect(jobState.submit.mock.calls[0]?.[0]).toBe(original);
    };

    await act(async () => {
      hookOf(bucket).reloadConfig();
    });
    expect(hookOf(bucket).configPending).toBe(true);
    expect(hookOf(bucket).config?.budget_period).toBe("2026-09-01");
    await expectFreshBlocked();
    const settleReload = resolveReload;
    if (settleReload === undefined) {
      throw new Error("reload fetch was not started");
    }

    await act(async () => {
      settleReload({ ok: false, json: async () => ({}) } as Response);
    });
    await flush();
    expect(hookOf(bucket).configPending).toBe(false);
    expect(hookOf(bucket).configError).toBe(CONFIG_UNAVAILABLE);
    expect(hookOf(bucket).config?.budget_period).toBe("2026-09-01");
    await expectFreshBlocked();

    await act(async () => {
      hookOf(bucket).reloadConfig();
    });
    await flush();
    expect(hookOf(bucket).config).toEqual(nextConfig);
    expect(hookOf(bucket).configPending).toBe(false);
    expect(hookOf(bucket).configError).toBeNull();
    const expectNewPeriod = async (run: () => void | Promise<void>): Promise<void> => {
      jobState.submit.mockClear();
      await act(async () => {
        await run();
      });
      expect(jobState.submit.mock.calls[0]?.[0]?.request.budget_period).toBe("2026-10-01");
    };
    await expectNewPeriod(async () => hookOf(bucket).submitForm());
    await expectNewPeriod(() => hookOf(bucket).newRequest());
    await expectNewPeriod(() => hookOf(bucket).example("vegan"));
    renderer.unmount();
  });

  it("marks the last estimate dirty when spending fingerprint changes", async () => {
    const nextConfig: GroceryConfig = {
      ...demoConfig,
      posted_cents: 2400,
      spending_refreshed_at: "2026-09-08T16:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonOk(demoConfig))
      .mockResolvedValueOnce(jsonOk(nextConfig));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer, refresh } = mount();
    await flush();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    const original = jobState.submit.mock.calls[0]?.[0];
    jobState.job = succeededJob;
    refresh();
    expect(hookOf(bucket).dirty).toBe(false);
    const submittedForm = hookOf(bucket).form;
    await act(async () => {
      hookOf(bucket).reloadConfig();
    });
    await flush();
    expect(hookOf(bucket).config?.posted_cents).toBe(2400);
    expect(hookOf(bucket).dirty).toBe(true);
    expect(hookOf(bucket).form).toEqual(submittedForm);
    expect(hookOf(bucket).job?.result?.plan.total_cents).toBe(129);
    act(() => {
      hookOf(bucket).retry();
    });
    expect(jobState.submit).toHaveBeenLastCalledWith(original);
    renderer.unmount();
  });

  it("does not mark dirty when the config fingerprint is unchanged", async () => {
    const nextConfig: GroceryConfig = {
      ...demoConfig,
      recipes: demoConfig.recipes.map((recipe) =>
        recipe.id === "bean_tacos" ? { ...recipe, name: "Bean tacos (display)" } : recipe,
      ),
      ingredients: [...demoConfig.ingredients],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonOk(demoConfig))
      .mockResolvedValueOnce(jsonOk(nextConfig));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer, refresh } = mount();
    await flush();
    await act(async () => {
      await hookOf(bucket).submitForm();
    });
    jobState.job = succeededJob;
    refresh();
    await act(async () => {
      hookOf(bucket).reloadConfig();
    });
    await flush();
    expect(hookOf(bucket).config?.notice).toBe(SAMPLE_ESTIMATE_NOTICE);
    expect(hookOf(bucket).config?.recipes).toEqual(nextConfig.recipes);
    expect(hookOf(bucket).dirty).toBe(false);
    expect(hookOf(bucket).job?.result?.plan.total_cents).toBe(129);
    renderer.unmount();
  });
});
