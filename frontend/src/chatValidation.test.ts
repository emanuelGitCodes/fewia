/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  NUTRITION_NOTICE, SHAPE_ERROR, SPOONACULAR_COST_NOTICE,
  type MacroTotals, type MealPlanNutrition, type MealRequest,
} from "./apiTypes";
import { budget, line, mealPlanNutrition, plan, sampleNutrition } from "../tests/apiFixtures";
import { parseChatJob, parseChatResult } from "./chatValidation";

const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

function nutritionFor(meals: MealRequest[]): MealPlanNutrition {
  const perServing = sampleNutrition().meals[0].per_serving;
  const scale = (servings: number): MacroTotals => ({
    energy_kcal: perServing.energy_kcal * servings,
    protein_mg: perServing.protein_mg * servings,
    carbohydrate_mg: perServing.carbohydrate_mg * servings,
    fat_mg: perServing.fat_mg * servings,
  });
  return sampleNutrition({
    total: scale(meals.reduce((total, meal) => total + meal.servings, 0)),
    meals: meals.map((meal) => ({
      ...meal, per_serving: { ...perServing }, total: scale(meal.servings),
    })),
  });
}

function request(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    budget_period: "2026-09-01",
    plan_cap_cents: null,
    pantry_ingredients: [],
    ingredient_exclusions: [],
    diet: "omnivore",
    ...overrides,
  };
}

function trace(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    tool: "select_meals",
    outcome: "success",
    tool_use_id: "tool-1",
    sequence: 1,
    revision_index: 1,
    ...overrides,
  };
}

function candidate(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    status: "planned",
    answer: "Bean tacos fit the budget.",
    plan: plan(),
    budget: budget(),
    request: request(),
    evidence_id: null,
    evidence_revision_id: REVISION,
    meal_nutrition: mealPlanNutrition(),
    spending_source: "fixture",
    tool_trace: [trace()],
    model_turns: 2,
    planner_revisions: 1,
    usage: { inputTokens: 11, outputTokens: 7 },
    ...overrides,
  };
}

function noPlan(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return candidate({
    status: "limit",
    plan: null,
    budget: null,
    request: null,
    evidence_id: null,
    evidence_revision_id: null,
    meal_nutrition: null,
    ...overrides,
  });
}

function expectShapeError(value: unknown): void {
  expect(() => parseChatResult(value)).toThrow(SHAPE_ERROR);
  try {
    parseChatResult(value);
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(SHAPE_ERROR);
  }
}

describe("parseChatResult", () => {
  it("accepts a planned result with budget, request, and a 64-hex revision", () => {
    const parsed = parseChatResult(candidate());
    expect(parsed.status).toBe("planned");
    expect(parsed.plan?.accepted).toBe(true);
    expect(parsed.budget?.available_cents).toBe(5000);
    expect(parsed.request?.meals).toHaveLength(1);
    expect(parsed.evidence_revision_id).toBe(REVISION);
    expect(parsed.spending_source).toBe("fixture");
  });

  it("accepts needs_revision only when accepted is false", () => {
    const parsed = parseChatResult(
      candidate({
        status: "needs_revision",
        plan: plan({ accepted: false, warnings: ["Over the remaining budget"] }),
      }),
    );
    expect(parsed.status).toBe("needs_revision");
    expect(parsed.plan?.accepted).toBe(false);
    expectShapeError(candidate({ status: "needs_revision" }));
    expectShapeError(candidate({ plan: plan({ accepted: false }) }));
  });

  it("accepts clarification with an incomplete plan or with no candidate", () => {
    const incomplete = parseChatResult(
      candidate({
        status: "clarification",
        plan: plan({
          lines: [line({ cost_cents: null })],
          total_cents: null,
          accepted: false,
          warnings: ["Missing sample price"],
        }),
      }),
    );
    expect(incomplete.plan?.total_cents).toBeNull();
    expect(incomplete.plan?.accepted).toBe(false);
    const none = parseChatResult(noPlan({ status: "clarification" }));
    expect(none.plan).toBeNull();
    expect(none.budget).toBeNull();
    expect(none.request).toBeNull();
    expect(none.evidence_id).toBeNull();
    expect(none.evidence_revision_id).toBeNull();
  });

  it("accepts limit and incomplete only when the candidate is null", () => {
    expect(parseChatResult(noPlan({ status: "limit" })).plan).toBeNull();
    expect(parseChatResult(noPlan({ status: "incomplete" })).plan).toBeNull();
    expectShapeError(candidate({ status: "limit" }));
    expectShapeError(candidate({ status: "incomplete" }));
  });

  it("accepts spending_source manual and rejects an unknown source", () => {
    expect(parseChatResult(candidate({ spending_source: "manual" })).spending_source).toBe("manual");
    expectShapeError(candidate({ spending_source: "unknown" }));
  });

  it("rejects malformed candidates, IDs, sources, usage, and traces", () => {
    expectShapeError(candidate({ status: "unknown" }));
    expectShapeError(candidate({ answer: "" }));
    expectShapeError(candidate({ evidence_revision_id: "ABCDEF" + "a".repeat(58) }));
    expectShapeError(candidate({ evidence_revision_id: "a".repeat(63) }));
    expectShapeError(candidate({ evidence_id: "" }));
    expectShapeError(candidate({ spending_source: "bedrock" }));
    expectShapeError(candidate({ usage: { inputTokens: -1, outputTokens: 0 } }));
    expectShapeError(candidate({ usage: { inputTokens: 1.5, outputTokens: 1 } }));
    expectShapeError(candidate({ tool_trace: [trace({ outcome: "ok" })] }));
    expectShapeError(candidate({ tool_trace: [trace({ tool_use_id: "x".repeat(65) })] }));
    expectShapeError(candidate({ tool_trace: [trace({ sequence: 0 })] }));
    expectShapeError(candidate({ tool_trace: [trace({ revision_index: 4 })] }));
    expectShapeError(candidate({ tool_trace: Array.from({ length: 25 }, () => trace()) }));
  });

  it("rejects booleans and unsafe integers in numeric fields", () => {
    expectShapeError(candidate({ model_turns: true }));
    expectShapeError(candidate({ planner_revisions: false }));
    expectShapeError(candidate({ model_turns: 1.5 }));
    expectShapeError(candidate({ model_turns: Number.MAX_SAFE_INTEGER + 1 }));
    expectShapeError(candidate({ usage: { inputTokens: true, outputTokens: 1 } }));
    expectShapeError(candidate({
      request: request({ meals: [{ recipe_id: "bean_tacos", servings: true }] }),
      meal_nutrition: null,
    }));
    expectShapeError(candidate({ plan: plan({ accepted: 1 }) }));
    expectShapeError(candidate({ budget: budget({ stale: 1 }) }));
  });

  it("copies valid cache counts and omits absent fields and unknown metadata", () => {
    const usage = {
      inputTokens: 11, outputTokens: 7, cacheReadInputTokens: 0, cacheWriteInputTokens: 9,
    };
    const input = candidate({ usage: { ...usage, reasoningContent: "hidden", totalTokens: 18 } });
    const parsed = parseChatResult(input);
    expect(parsed.usage).toEqual(usage);
    expect(parsed.usage).not.toBe(input.usage);
    if (parsed.usage !== null) {
      parsed.usage.cacheWriteInputTokens = 99;
    }
    expect((input.usage as typeof usage).cacheWriteInputTokens).toBe(9);
    expect(parseChatResult(candidate()).usage).toEqual({ inputTokens: 11, outputTokens: 7 });
    expect(parseChatResult(candidate({ usage: null })).usage).toBeNull();
  });

  it.each(["cacheReadInputTokens", "cacheWriteInputTokens"] as const)(
    "omits invalid optional %s without fabricating zero", (key) => {
      const other = key === "cacheReadInputTokens" ? "cacheWriteInputTokens" : "cacheReadInputTokens";
      for (const invalid of [undefined, null, true, false, -1, 1.5, "1", NaN, Infinity,
        Number.MAX_SAFE_INTEGER + 1, {}, []]) {
        const usage = { inputTokens: 11, outputTokens: 7, [key]: invalid, [other]: 0 };
        expect(parseChatResult(candidate({ usage })).usage).toEqual({
          inputTokens: 11, outputTokens: 7, [other]: 0,
        });
      }
    },
  );

  it("accepts three meals and eight servings and rejects those limits", () => {
    const meals = [
      { recipe_id: "bean_tacos", servings: 8 },
      { recipe_id: "lentil_soup", servings: 1 },
      { recipe_id: "overnight_oats", servings: 8 },
    ];
    const parsed = parseChatResult(candidate({
      request: request({ meals }), meal_nutrition: nutritionFor(meals),
    }));
    expect(parsed.request?.meals).toHaveLength(3);
    expect(parsed.request?.meals[0]?.servings).toBe(8);
    expectShapeError(candidate({ request: request({ meals: [] }), meal_nutrition: null }));
    expectShapeError(
      candidate({
        request: request({ meals: [...meals, { recipe_id: "chickpea_curry", servings: 1 }] }),
        meal_nutrition: null,
      }),
    );
    expectShapeError(
      candidate({
        request: request({ meals: [{ recipe_id: "bean_tacos", servings: 0 }] }),
        meal_nutrition: null,
      }),
    );
    expectShapeError(
      candidate({
        request: request({ meals: [{ recipe_id: "bean_tacos", servings: 9 }] }),
        meal_nutrition: null,
      }),
    );
  });

  it.each<[string, MealRequest[]]>([
    ["recipe ID", [{ recipe_id: "bean_tacos", servings: 2 }, { recipe_id: "overnight_oats", servings: 1 }]],
    ["servings", [{ recipe_id: "bean_tacos", servings: 2 }, { recipe_id: "lentil_soup", servings: 2 }]],
    ["missing entry", [{ recipe_id: "bean_tacos", servings: 2 }]],
    ["extra entry", [
      { recipe_id: "bean_tacos", servings: 2 }, { recipe_id: "lentil_soup", servings: 1 },
      { recipe_id: "overnight_oats", servings: 1 },
    ]],
    ["duplicate entry", [{ recipe_id: "bean_tacos", servings: 2 }, { recipe_id: "bean_tacos", servings: 2 }]],
  ])("rejects nutrition with a mismatched %s", (_name, meals) => {
    expectShapeError(candidate({
      request: request({ meals: [
        { recipe_id: "bean_tacos", servings: 2 }, { recipe_id: "lentil_soup", servings: 1 },
      ] }),
      meal_nutrition: nutritionFor(meals),
    }));
  });

  it("accepts reordered nutrition and compares recipe and servings as pairs", () => {
    const meals = [
      { recipe_id: "bean_tacos", servings: 2 },
      { recipe_id: "lentil_soup", servings: 1 },
      { recipe_id: "bean_tacos", servings: 4 },
    ];
    const nutrition = nutritionFor([...meals].reverse());
    expect(parseChatResult(candidate({
      request: request({ meals }), meal_nutrition: nutrition,
    })).meal_nutrition).toEqual(nutrition);
    expectShapeError(candidate({
      request: request({ meals }), meal_nutrition: nutritionFor([
        { recipe_id: "bean_tacos", servings: 1 },
        { recipe_id: "lentil_soup", servings: 2 },
        { recipe_id: "bean_tacos", servings: 4 },
      ]),
    }));
  });

  it("preserves the multiplicity of repeated requested meals", () => {
    const bean = { recipe_id: "bean_tacos", servings: 2 };
    const lentil = { recipe_id: "lentil_soup", servings: 1 };
    const retained = candidate({ request: request({ meals: [bean, bean, lentil] }) });
    const nutrition = nutritionFor([bean, lentil, bean]);
    expect(parseChatResult({ ...retained, meal_nutrition: nutrition }).meal_nutrition).toEqual(nutrition);
    expectShapeError({ ...retained, meal_nutrition: nutritionFor([bean, lentil, lentil]) });
  });

  it.each(["absent", "null", "unavailable"])("keeps %s nutrition compatible with requested meals", (mode) => {
    const unavailable = mealPlanNutrition({ total: null, meals: [] });
    const input = candidate({
      request: request({ meals: [
        { recipe_id: "lentil_soup", servings: 8 }, { recipe_id: "overnight_oats", servings: 1 },
      ] }),
      meal_nutrition: mode === "unavailable" ? unavailable : null,
    });
    if (mode === "absent") {
      delete input.meal_nutrition;
    }
    const parsed = parseChatResult(input);
    expect(parsed.meal_nutrition).toEqual(mode === "unavailable" ? unavailable : null);
    expect(parsed.plan?.accepted).toBe(true);
  });

  it("rejects unavailable nutrition with meal entries and available nutrition without them", () => {
    expectShapeError(candidate({ meal_nutrition: mealPlanNutrition({ total: null }) }));
    expectShapeError(candidate({ meal_nutrition: mealPlanNutrition({ meals: [] }) }));
  });

  it("does not copy unknown role or raw reasoning fields", () => {
    const parsed = parseChatResult(
      candidate({
        role: "assistant",
        raw_reasoning: "hidden chain",
        tool_trace: [
          trace({
            role: "tool",
            raw_reasoning: "scratch",
            arguments: { meal: 1 },
          }),
        ],
      }),
    );
    expect("role" in parsed).toBe(false);
    expect("raw_reasoning" in parsed).toBe(false);
    expect("role" in parsed.tool_trace[0]).toBe(false);
    expect("raw_reasoning" in parsed.tool_trace[0]).toBe(false);
    expect("arguments" in parsed.tool_trace[0]).toBe(false);
  });

  it("throws the static SHAPE_ERROR and does not echo payload text", () => {
    expect.assertions(2);
    try {
      parseChatResult(candidate({ evidence_revision_id: "not-a-revision-id" }));
    } catch (error) {
      expect((error as Error).message).toBe(SHAPE_ERROR);
      expect((error as Error).message).not.toContain("not-a-revision-id");
    }
  });

  it("deep-copies nested fields and does not mutate the input", () => {
    const input = candidate({
      plan: plan({ warnings: ["Keep"] }),
      tool_trace: [trace()],
    });
    const parsed = parseChatResult(input);
    parsed.plan?.warnings.push("Changed");
    parsed.tool_trace[0].tool = "mutated";
    if (parsed.usage !== null) {
      parsed.usage.inputTokens = 99;
    }
    parsed.request?.meals.push({ recipe_id: "lentil_soup", servings: 1 });
    expect((input.plan as { warnings: string[] }).warnings).toEqual(["Keep"]);
    expect((input.tool_trace as { tool: string }[])[0]?.tool).toBe("select_meals");
    expect((input.usage as { inputTokens: number }).inputTokens).toBe(11);
    expect((input.request as { meals: unknown[] }).meals).toHaveLength(1);
  });

  it("normalizes omitted nutrition on retained candidates and keeps dropped candidates null", () => {
    const retained = parseChatResult(candidate());
    expect(retained.meal_nutrition?.notice).toBe(NUTRITION_NOTICE);
    expect(retained.meal_nutrition?.total?.energy_kcal).toBe(200);
    const omitted = candidate();
    delete omitted.meal_nutrition;
    const parsedOmit = parseChatResult(omitted);
    expect(parsedOmit.meal_nutrition).toBeNull();
    expect(parsedOmit.plan?.accepted).toBe(true);
    parsedOmit.plan?.warnings.push("Changed");
    expect((omitted.plan as { warnings: string[] }).warnings).toEqual([]);
    expect(parseChatResult(candidate({ meal_nutrition: null })).meal_nutrition).toBeNull();
    expect(parseChatResult(noPlan()).meal_nutrition).toBeNull();
    const droppedOmit = noPlan();
    delete droppedOmit.meal_nutrition;
    expect(parseChatResult(droppedOmit).meal_nutrition).toBeNull();
    expect(
      parseChatResult(candidate({ meal_nutrition: mealPlanNutrition({ total: null, meals: [] }) }))
        .meal_nutrition?.total,
    ).toBeNull();
    expectShapeError(noPlan({ meal_nutrition: mealPlanNutrition() }));
    expectShapeError(candidate({ meal_nutrition: mealPlanNutrition({ notice: "wrong" }) }));
    expectShapeError(
      candidate({
        meal_nutrition: mealPlanNutrition({
          total: { energy_kcal: 1.5, protein_mg: 0, carbohydrate_mg: 0, fat_mg: 0 },
        }),
      }),
    );
  });

  it("copies supermarket_estimate when present and omits it when absent", () => {
    const overlay = {
      total_cents: 1299,
      notice: SPOONACULAR_COST_NOTICE,
      lines: [{ ingredient_id: "black_beans", cents: 199 }],
    };
    const parsed = parseChatResult(candidate({ supermarket_estimate: overlay }));
    expect(parsed.supermarket_estimate).toEqual(overlay);
    const omitted = parseChatResult(candidate());
    expect("supermarket_estimate" in omitted).toBe(false);
  });

  it("deep-copies meal_nutrition and does not mutate the input", () => {
    const input = candidate();
    const parsed = parseChatResult(input);
    if (parsed.meal_nutrition === null || parsed.meal_nutrition.total === null) {
      throw new Error("expected cloned nutrition");
    }
    parsed.meal_nutrition.total.energy_kcal = 1;
    parsed.meal_nutrition.meals[0].recipe_id = "mutated";
    expect((input.meal_nutrition as { total: { energy_kcal: number } }).total.energy_kcal).toBe(200);
    expect((input.meal_nutrition as { meals: { recipe_id: string }[] }).meals[0]?.recipe_id).toBe(
      "bean_tacos",
    );
  });
});

describe("parseChatJob", () => {
  it("accepts a succeeded job with a valid planned result", () => {
    const parsed = parseChatJob({
      id: "job-1",
      status: "succeeded",
      result: candidate(),
      error_code: null,
    });
    expect(Object.keys(parsed)).toEqual(["id", "status", "result", "error_code"]);
    expect(parsed.result?.status).toBe("planned");
  });

  it("accepts a pending job with a null result and rejects a succeeded null result", () => {
    const parsed = parseChatJob({
      id: "job-2",
      status: "queued",
      result: null,
      error_code: null,
    });
    expect(parsed.result).toBeNull();
    expect(() =>
      parseChatJob({ id: "job-3", status: "succeeded", result: null, error_code: null }),
    ).toThrow(SHAPE_ERROR);
  });
});
