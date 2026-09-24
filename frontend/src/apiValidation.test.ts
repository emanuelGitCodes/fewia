/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  SAMPLE_ESTIMATE_NOTICE,
  SHAPE_ERROR,
  SPOONACULAR_COST_NOTICE,
} from "./apiTypes";
import { copyMealPlanNutrition, parseConfig, parseJob } from "./apiValidation";
import { budget, config, job, jobResult, line, mealPlanNutrition, plan } from "../tests/apiFixtures";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const CATALOG = "sample-prices-v1";
const STAMP = "2026-09-07T16:00:00Z";

function groceryConfig(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return config({
    catalog_version: CATALOG,
    spending_refreshed_at: STAMP,
    ...overrides,
  });
}

describe("parseJob", () => {
  it("accepts an incomplete plan with a null total and accepted false", () => {
    const parsed = parseJob(
      job({
        result: jobResult({
          plan: plan({
            lines: [line({ cost_cents: null })],
            total_cents: null,
            accepted: false,
            warnings: ["Missing sample price"],
          }),
        }),
      }),
    );

    expect(parsed.result?.plan.total_cents).toBeNull();
    expect(parsed.result?.plan.accepted).toBe(false);
    expect(parsed.result?.plan.notice).toBe(NOTICE);
    expect(parsed.result?.spending_source).toBe("fixture");
  });

  it("rejects an incomplete plan when accepted is true", () => {
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            plan: plan({
              lines: [line({ cost_cents: null })],
              total_cents: null,
              accepted: true,
            }),
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
  });

  it("rejects fractional and unsafe cents", () => {
    expect(() => parseJob(job({ result: jobResult({ plan: plan({ total_cents: 1.5 }) }) }))).toThrow(
      SHAPE_ERROR,
    );
    expect(() =>
      parseJob(job({ result: jobResult({ plan: plan({ lines: [line({ cost_cents: 1.5 })] }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ budget: budget({ available_cents: 10.25 }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({ plan: plan({ total_cents: Number.MAX_SAFE_INTEGER + 1 }) }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() => parseJob(job({ result: jobResult({ plan: plan({ lines: [line({ packages: 1.5 })] }) }) }))).toThrow(
      SHAPE_ERROR,
    );
    expect(() => parseJob(job({ result: jobResult({ plan: plan({ lines: [line({ quantity: 0 })] }) }) }))).toThrow(
      SHAPE_ERROR,
    );
  });

  it("rejects a succeeded job with a null result", () => {
    expect(() => parseJob(job({ status: "succeeded", result: null }))).toThrow(SHAPE_ERROR);
  });

  it("accepts a queued job with a null result", () => {
    const parsed = parseJob(job({ status: "queued", result: null }));
    expect(parsed.result).toBeNull();
    expect(parsed.status).toBe("queued");
  });

  it("accepts a result with no overlay", () => {
    const parsed = parseJob(job());
    expect(parsed.result?.plan.total_cents).toBe(129);
    expect(parsed.result?.supermarket_estimate).toBeUndefined();
  });

  it("accepts overlay 1299 with the Spoonacular notice", () => {
    const parsed = parseJob(
      job({
        result: jobResult({
          supermarket_estimate: { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE },
        }),
      }),
    );
    expect(parsed.result?.plan.total_cents).toBe(129);
    expect(parsed.result?.supermarket_estimate?.total_cents).toBe(1299);
    expect(parsed.result?.supermarket_estimate?.notice).toBe(SPOONACULAR_COST_NOTICE);
  });

  it("rejects overlay notice store price and a negative overlay total", () => {
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            supermarket_estimate: { total_cents: 1299, notice: "store price" },
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            supermarket_estimate: { total_cents: -1, notice: SPOONACULAR_COST_NOTICE },
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
  });

  it("accepts required nutrition and keeps budget acceptance unchanged", () => {
    const parsed = parseJob(job());
    expect(parsed.result?.meal_nutrition?.notice).toBe(NUTRITION_NOTICE);
    expect(parsed.result?.meal_nutrition?.portion_notice).toBe(NUTRITION_PORTION_NOTICE);
    expect(parsed.result?.meal_nutrition?.total?.energy_kcal).toBe(200);
    expect(parsed.result?.plan.accepted).toBe(true);
    const rejected = parseJob(
      job({
        result: jobResult({
          plan: plan({ accepted: false, warnings: ["Over the remaining budget"] }),
        }),
      }),
    );
    expect(rejected.result?.plan.accepted).toBe(false);
    expect(rejected.result?.meal_nutrition?.total?.energy_kcal).toBe(200);
  });

  it("accepts a legacy manual result that omits meal_nutrition", () => {
    const result = jobResult();
    delete result.meal_nutrition;
    const parsed = parseJob(job({ result }));
    expect(parsed.result?.meal_nutrition).toBeUndefined();
    expect(parsed.result?.plan.accepted).toBe(true);
    expect(parsed.result?.plan.total_cents).toBe(129);
  });

  it("rejects malformed nutrition fields and wrong notices", () => {
    expect(() => parseJob(job({ result: jobResult({ meal_nutrition: null }) }))).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ meal_nutrition: mealPlanNutrition({ notice: "wrong" }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({ meal_nutrition: mealPlanNutrition({ portion_notice: "wrong" }) }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            meal_nutrition: mealPlanNutrition({
              meals: [
                {
                  recipe_id: "",
                  servings: 2,
                  per_serving: { energy_kcal: 1, protein_mg: 1, carbohydrate_mg: 1, fat_mg: 1 },
                  total: { energy_kcal: 1, protein_mg: 1, carbohydrate_mg: 1, fat_mg: 1 },
                },
              ],
            }),
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            meal_nutrition: mealPlanNutrition({
              total: { energy_kcal: -1, protein_mg: 0, carbohydrate_mg: 0, fat_mg: 0 },
            }),
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            meal_nutrition: mealPlanNutrition({
              meals: [
                {
                  recipe_id: "bean_tacos",
                  servings: 9,
                  per_serving: { energy_kcal: 1, protein_mg: 1, carbohydrate_mg: 1, fat_mg: 1 },
                  total: { energy_kcal: 1, protein_mg: 1, carbohydrate_mg: 1, fat_mg: 1 },
                },
              ],
            }),
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    const meal = {
      recipe_id: "bean_tacos",
      servings: 1,
      per_serving: { energy_kcal: 1, protein_mg: 1, carbohydrate_mg: 1, fat_mg: 1 },
      total: { energy_kcal: 1, protein_mg: 1, carbohydrate_mg: 1, fat_mg: 1 },
    };
    expect(() =>
      parseJob(
        job({ result: jobResult({ meal_nutrition: mealPlanNutrition({ meals: [meal, meal, meal, meal] }) }) }),
      ),
    ).toThrow(SHAPE_ERROR);
  });

  it("accepts a null nutrition total only with an empty meals array", () => {
    const parsed = parseJob(
      job({ result: jobResult({ meal_nutrition: mealPlanNutrition({ total: null, meals: [] }) }) }),
    );
    expect(parsed.result?.meal_nutrition?.total).toBeNull();
    expect(parsed.result?.meal_nutrition?.meals).toEqual([]);
    expect(() =>
      parseJob(job({ result: jobResult({ meal_nutrition: mealPlanNutrition({ total: null }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ meal_nutrition: mealPlanNutrition({ meals: [] }) }) })),
    ).toThrow(SHAPE_ERROR);
  });
});

describe("copyMealPlanNutrition", () => {
  it("deep-copies nutrition and does not mutate the input", () => {
    const input = mealPlanNutrition();
    const copied = copyMealPlanNutrition(input);
    if (copied === null || copied.total === null) {
      throw new Error("expected cloned nutrition");
    }
    copied.total.energy_kcal = 1;
    copied.meals[0].recipe_id = "mutated";
    copied.meals.push(copied.meals[0]);
    expect((input.total as { energy_kcal: number }).energy_kcal).toBe(200);
    expect((input.meals as { recipe_id: string }[])[0]?.recipe_id).toBe("bean_tacos");
    expect((input.meals as unknown[]).length).toBe(1);
  });
});

describe("parseConfig", () => {
  it("accepts signed posted and pending cents", () => {
    const parsed = parseConfig(groceryConfig({ posted_cents: -10, pending_cents: -3 }));
    expect(parsed.posted_cents).toBe(-10);
    expect(parsed.pending_cents).toBe(-3);
    expect(parsed.source).toBe("fixture");
    expect(parsed.notice).toBe(NOTICE);
  });

  it("rejects fractional posted cents", () => {
    expect(() => parseConfig(groceryConfig({ posted_cents: 1.5 }))).toThrow(SHAPE_ERROR);
  });

  it("accepts plaid_sandbox, catalog_version, and a timezone timestamp or null", () => {
    const parsed = parseConfig(
      groceryConfig({ source: "plaid_sandbox", spending_refreshed_at: "2026-09-07T12:00:00-04:00" }),
    );
    expect(parsed.source).toBe("plaid_sandbox");
    expect(parsed.catalog_version).toBe(CATALOG);
    expect(parsed.spending_refreshed_at).toBe("2026-09-07T12:00:00-04:00");
    expect(parseConfig(groceryConfig({ spending_refreshed_at: null })).spending_refreshed_at).toBeNull();
  });

  it("rejects unknown sources, empty catalog versions, and naive timestamps", () => {
    expect(() => parseConfig(groceryConfig({ source: "bedrock" }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(groceryConfig({ catalog_version: "" }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(groceryConfig({ spending_refreshed_at: "2026-09-07T16:00:00" }))).toThrow(
      SHAPE_ERROR,
    );
    expect(() => parseConfig(groceryConfig({ spending_refreshed_at: "" }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(config({ catalog_version: CATALOG }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(config({ spending_refreshed_at: STAMP }))).toThrow(SHAPE_ERROR);
  });
});
