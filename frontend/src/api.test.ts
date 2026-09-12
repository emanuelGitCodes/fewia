/** @vitest-environment node */

import { afterEach, describe, expect, it, vi } from "vitest";
import { budget, job, jobResult, plan } from "../tests/apiFixtures";
import { fetchJob, parseJob } from "./api";
import { SPOONACULAR_COST_NOTICE } from "./apiTypes";
import { NUTRITION_NOTICE, NUTRITION_PORTION_NOTICE } from "./nutritionTypes";

describe("fetchJob JSON abort", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("aborts a hung JSON body when the caller signal aborts", async () => {
    let markJsonStart: (() => void) | undefined;
    const jsonStarted = new Promise<void>((resolve) => {
      markJsonStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => {
          if (markJsonStart === undefined) {
            throw new Error("JSON start is not armed");
          }
          markJsonStart();
          return new Promise(() => undefined);
        },
      })),
    );
    const controller = new AbortController();
    const pending = fetchJob("job-1", controller.signal);
    await jsonStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("parseJob supermarket projection", () => {
  it("discards a legacy supermarket_estimate and keeps macros and budget", () => {
    const nutrition = {
      notice: NUTRITION_NOTICE,
      portion_notice: NUTRITION_PORTION_NOTICE,
      total: { energy_kcal: 400, protein_mg: 20000, carbohydrate_mg: 60000, fat_mg: 16000 },
      meals: [
        {
          recipe_id: "bean_tacos",
          servings: 2,
          per_serving: { energy_kcal: 200, protein_mg: 10000, carbohydrate_mg: 30000, fat_mg: 8000 },
          total: { energy_kcal: 400, protein_mg: 20000, carbohydrate_mg: 60000, fat_mg: 16000 },
        },
      ],
    };
    const request = { meals: [{ recipe_id: "bean_tacos", servings: 2 }] };
    const input = job({
      result: jobResult({
        plan: plan({ total_cents: 478 }),
        budget: budget({ available_cents: 5000, pending_cents: 200 }),
        supermarket_estimate: { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE },
        nutrition,
        evidence_revision_id: "rev-1",
        request,
        answer: "Bean tacos fit the budget.",
      }),
    });
    const snapshot = JSON.parse(JSON.stringify(input)) as unknown;
    const parsed = parseJob(input);
    const extra = parsed.result as
      | { evidence_revision_id?: unknown; request?: unknown; answer?: unknown }
      | null
      | undefined;
    expect(parsed.result?.supermarket_estimate).toBeUndefined();
    expect(parsed.result?.plan.total_cents).toBe(478);
    expect(parsed.result?.budget.available_cents).toBe(5000);
    expect(parsed.result?.budget.pending_cents).toBe(200);
    expect(parsed.result?.nutrition).toEqual(nutrition);
    expect(extra?.evidence_revision_id).toBe("rev-1");
    expect(extra?.request).toEqual(request);
    expect(extra?.answer).toBe("Bean tacos fit the budget.");
    expect(input).toEqual(snapshot);
    expect((input.result as { supermarket_estimate?: unknown }).supermarket_estimate).toEqual({
      total_cents: 1299,
      notice: SPOONACULAR_COST_NOTICE,
    });
  });
});
