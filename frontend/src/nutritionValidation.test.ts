/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SHAPE_ERROR, SPOONACULAR_COST_NOTICE } from "./apiTypes";
import { parseJob } from "./apiValidation";
import { parseChatResult } from "./chatValidation";
import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  type MacroTotals,
  type MealPlanNutrition,
} from "./nutritionTypes";
import { budget, job, jobResult, plan } from "../tests/apiFixtures";

const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

function macros(overrides: Partial<MacroTotals> = {}): MacroTotals {
  return {
    energy_kcal: 200,
    protein_mg: 10000,
    carbohydrate_mg: 30000,
    fat_mg: 8000,
    ...overrides,
  };
}

function meal(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    recipe_id: "bean_tacos",
    servings: 2,
    per_serving: macros(),
    total: macros({ energy_kcal: 400 }),
    ...overrides,
  };
}

function nutrition(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    notice: NUTRITION_NOTICE,
    portion_notice: NUTRITION_PORTION_NOTICE,
    total: macros({ energy_kcal: 400 }),
    meals: [meal()],
    ...overrides,
  };
}

function unavailable(): Record<string, unknown> {
  return nutrition({ total: null, meals: [] });
}

function chatCandidate(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    status: "planned",
    answer: "Bean tacos fit the budget.",
    plan: plan(),
    budget: budget(),
    request: {
      meals: [{ recipe_id: "bean_tacos", servings: 2 }],
      budget_period: "2026-09-01",
      plan_cap_cents: null,
      pantry_ingredients: [],
      ingredient_exclusions: [],
      diet: "omnivore",
    },
    evidence_id: null,
    evidence_revision_id: REVISION,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 2,
    planner_revisions: 1,
    usage: { inputTokens: 11, outputTokens: 7 },
    ...overrides,
  };
}

function noPlan(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return chatCandidate({
    status: "limit",
    plan: null,
    budget: null,
    request: null,
    evidence_id: null,
    evidence_revision_id: null,
    ...overrides,
  });
}

describe("nutrition transport", () => {
  it("accepts a grocery result without nutrition", () => {
    const parsed = parseJob(job());
    expect(parsed.result?.nutrition).toBeUndefined();
  });

  it("accepts valid nutrition on grocery and chat results", () => {
    const payload = nutrition();
    const grocery = parseJob(job({ result: jobResult({ nutrition: payload }) }));
    expect(grocery.result?.nutrition).toEqual(payload);
    const chat = parseChatResult(chatCandidate({ nutrition: payload }));
    expect(chat.nutrition).toEqual(payload);
    expect(chat.nutrition).not.toBe(payload);
  });

  it("accepts nutrition beside a Spoonacular overlay", () => {
    const parsed = parseJob(
      job({
        result: jobResult({
          supermarket_estimate: { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE },
          nutrition: nutrition(),
        }),
      }),
    );
    expect(parsed.result?.supermarket_estimate).toBeUndefined();
    expect(parsed.result?.nutrition?.meals).toHaveLength(1);
  });

  it("accepts unavailable nutrition with a null total and empty meals", () => {
    const payload = unavailable();
    expect(parseJob(job({ result: jobResult({ nutrition: payload }) })).result?.nutrition).toEqual(
      payload,
    );
    expect(parseChatResult(chatCandidate({ nutrition: payload })).nutrition).toEqual(payload);
  });

  it("accepts one to three meals and one to eight servings", () => {
    const meals = [
      meal({ recipe_id: "bean_tacos", servings: 1 }),
      meal({ recipe_id: "lentil_soup", servings: 8 }),
      meal({ recipe_id: "overnight_oats", servings: 3 }),
    ];
    const parsed = parseJob(job({ result: jobResult({ nutrition: nutrition({ meals }) }) }));
    expect(parsed.result?.nutrition?.meals).toHaveLength(3);
  });

  it("rejects nutrition that is null, undefined, or the wrong shape", () => {
    expect(() => parseJob(job({ result: jobResult({ nutrition: null }) }))).toThrow(SHAPE_ERROR);
    expect(() => parseJob(job({ result: jobResult({ nutrition: undefined }) }))).toThrow(SHAPE_ERROR);
    expect(() => parseJob(job({ result: jobResult({ nutrition: [] }) }))).toThrow(SHAPE_ERROR);
    expect(() => parseChatResult(chatCandidate({ nutrition: null }))).toThrow(SHAPE_ERROR);
  });

  it("rejects invalid notices and mismatched meal lists", () => {
    expect(() =>
      parseJob(job({ result: jobResult({ nutrition: nutrition({ notice: "USDA facts" }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({ result: jobResult({ nutrition: nutrition({ portion_notice: "one egg = 50 g" }) }) }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ nutrition: nutrition({ total: null }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ nutrition: nutrition({ meals: [] }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            nutrition: nutrition({
              meals: [
                meal(),
                meal({ recipe_id: "lentil_soup" }),
                meal({ recipe_id: "overnight_oats" }),
                meal({ recipe_id: "chickpea_curry" }),
              ],
            }),
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
  });

  it("rejects negative, nonfinite, fractional, and boolean macros", () => {
    const badMacros: unknown[] = [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, true, false, "200"];
    for (const bad of badMacros) {
      expect(() =>
        parseJob(
          job({
            result: jobResult({ nutrition: nutrition({ total: { ...macros(), energy_kcal: bad } }) }),
          }),
        ),
      ).toThrow(SHAPE_ERROR);
      expect(() =>
        parseChatResult(
          chatCandidate({
            nutrition: nutrition({ meals: [meal({ per_serving: { ...macros(), protein_mg: bad } })] }),
          }),
        ),
      ).toThrow(SHAPE_ERROR);
    }
  });

  it("rejects empty recipe ids and servings outside 1-8", () => {
    expect(() =>
      parseJob(job({ result: jobResult({ nutrition: nutrition({ meals: [meal({ recipe_id: "" })] }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ nutrition: nutrition({ meals: [meal({ servings: 0 })] }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ nutrition: nutrition({ meals: [meal({ servings: 9 })] }) }) })),
    ).toThrow(SHAPE_ERROR);
  });

  it("rejects nutrition on a null chat plan and keeps older no-plan results", () => {
    const older = parseChatResult(noPlan());
    expect(older.plan).toBeNull();
    expect(older.nutrition).toBeUndefined();
    expect(() => parseChatResult(noPlan({ nutrition: nutrition() }))).toThrow(SHAPE_ERROR);
    expect(() => parseChatResult(noPlan({ nutrition: unavailable() }))).toThrow(SHAPE_ERROR);
  });

  it("does not share the cloned chat nutrition object with the input", () => {
    const payload = nutrition() as unknown as MealPlanNutrition;
    const input = chatCandidate({ nutrition: payload });
    const parsed = parseChatResult(input);
    if (parsed.nutrition === undefined) {
      throw new Error("expected nutrition");
    }
    const first = parsed.nutrition.meals[0];
    if (first === undefined) {
      throw new Error("expected a meal");
    }
    first.servings = 8;
    parsed.nutrition.meals.push({
      recipe_id: "lentil_soup",
      servings: 1,
      per_serving: macros(),
      total: macros(),
    });
    expect((input.nutrition as MealPlanNutrition).meals).toHaveLength(1);
    expect((input.nutrition as MealPlanNutrition).meals[0]?.servings).toBe(2);
  });
});
