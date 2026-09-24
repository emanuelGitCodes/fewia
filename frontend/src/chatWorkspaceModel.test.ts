/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryConfig } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import { initialForm, type FormState } from "./BudgetForm";
import type { ChatJob, ChatResult } from "./chatTypes";
import {
  chatBudgetFromForm,
  chatEstimateJob,
  configFingerprint,
  formFromChat,
} from "./chatWorkspaceModel";

const REVISION = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

const demoConfig: GroceryConfig = {
  budget_period: "2026-09-01",
  source: "fixture",
  catalog_version: "sample-prices-v1",
  posted_cents: 1200,
  pending_cents: -50,
  spending_refreshed_at: "2026-09-07T16:00:00Z",
  notice: SAMPLE_ESTIMATE_NOTICE,
  recipes: [{ id: "bean_tacos", name: "Bean tacos" }],
  ingredients: [{ id: "black_beans", name: "black beans" }],
};

function plannedResult(overrides: Partial<ChatResult> = {}): ChatResult {
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
    budget: {
      available_cents: 5000,
      pending_cents: 200,
      stale: false,
      warnings: [],
    },
    request: {
      meals: [{ recipe_id: "bean_tacos", servings: 2 }],
      budget_period: "2026-09-01",
      plan_cap_cents: null,
      pantry_ingredients: [],
      ingredient_exclusions: [],
      diet: "omnivore",
    },
    meal_nutrition: sampleNutrition(),
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

function succeededJob(result: ChatResult | null, status: ChatJob["status"] = "succeeded"): ChatJob {
  return { id: "job-1", status, result, error_code: null };
}

function noPlanResult(status: ChatResult["status"]): ChatResult {
  return plannedResult({
    status,
    plan: null,
    budget: null,
    request: null,
    meal_nutrition: null,
    evidence_id: null,
    evidence_revision_id: null,
  });
}

describe("chatBudgetFromForm", () => {
  it("parses a required monthly limit and an optional cap", () => {
    const form = { ...initialForm(), monthly: "300", cap: "40" };
    expect(chatBudgetFromForm(form)).toEqual({
      monthly_limit_cents: 30000,
      plan_cap_cents: 4000,
    });
    expect(chatBudgetFromForm({ ...form, cap: "" })).toEqual({
      monthly_limit_cents: 30000,
      plan_cap_cents: null,
    });
    expect(chatBudgetFromForm({ ...form, monthly: "17.03", cap: "0.01" })).toEqual({
      monthly_limit_cents: 1703,
      plan_cap_cents: 1,
    });
  });

  it("returns null for invalid monthly or cap input", () => {
    const form = initialForm();
    expect(chatBudgetFromForm({ ...form, monthly: "" })).toBeNull();
    expect(chatBudgetFromForm({ ...form, monthly: "1.001" })).toBeNull();
    expect(chatBudgetFromForm({ ...form, monthly: "$17.03" })).toBeNull();
    expect(chatBudgetFromForm({ ...form, cap: "1.001" })).toBeNull();
    expect(chatBudgetFromForm({ ...form, cap: "-1" })).toBeNull();
  });

  it("does not mutate the form", () => {
    const form = { ...initialForm(), monthly: "40", cap: "17.03" };
    const before = structuredClone(form);
    chatBudgetFromForm(form);
    form.monthly = "1";
    expect(before).toEqual({ ...initialForm(), monthly: "40", cap: "17.03" });
  });
});

describe("chatEstimateJob", () => {
  it("returns null when the job cannot display a plan", () => {
    expect(chatEstimateJob(null)).toBeNull();
    expect(chatEstimateJob(succeededJob(null, "queued"))).toBeNull();
    expect(chatEstimateJob(succeededJob(null, "running"))).toBeNull();
    expect(chatEstimateJob(succeededJob(null, "failed"))).toBeNull();
    expect(chatEstimateJob(succeededJob(noPlanResult("clarification")))).toBeNull();
    expect(chatEstimateJob(succeededJob(noPlanResult("limit")))).toBeNull();
    expect(chatEstimateJob(succeededJob(noPlanResult("incomplete")))).toBeNull();
    expect(chatEstimateJob({ ...succeededJob(plannedResult()), status: "failed" })).toBeNull();
  });

  it("copies a succeeded plan and budget and does not fabricate missing plans", () => {
    const source = succeededJob(plannedResult());
    const display = chatEstimateJob(source);
    expect(display).toEqual({
      id: "job-1",
      status: "succeeded",
      error_code: null,
      result: {
        plan: source.result?.plan,
        budget: source.result?.budget,
        spending_source: "fixture",
        meal_nutrition: source.result?.meal_nutrition,
      },
    });
    const clarification = plannedResult({
      status: "clarification",
      plan: {
        lines: [
          {
            ingredient_id: "black_beans",
            name: "black beans",
            unit: "g",
            quantity: 425,
            packages: 1,
            cost_cents: null,
            from_pantry: false,
          },
        ],
        total_cents: null,
        accepted: false,
        warnings: ["Missing sample price"],
        catalog_version: "sample-prices-v1",
        notice: SAMPLE_ESTIMATE_NOTICE,
      },
    });
    expect(chatEstimateJob(succeededJob(clarification))?.result?.plan?.total_cents).toBeNull();
  });

  it("does not share mutable plan or budget objects with the caller", () => {
    const source = succeededJob(plannedResult());
    const display = chatEstimateJob(source);
    const plan = source.result?.plan;
    const copied = display?.result?.plan;
    if (
      plan === undefined ||
      plan === null ||
      copied === undefined ||
      copied === null
    ) {
      throw new Error("expected a cloned plan");
    }
    plan.total_cents = 1;
    plan.warnings.push("mutated");
    copied.warnings.push("display");
    expect(display?.result?.plan?.total_cents).toBe(129);
    expect(display?.result?.plan?.warnings).toEqual(["display"]);
    expect(source.result?.plan?.warnings).toEqual(["mutated"]);
  });

  it("preserves nutrition, deep-copies it, and does not change budget acceptance", () => {
    const source = succeededJob(plannedResult());
    const display = chatEstimateJob(source);
    const original = source.result?.meal_nutrition;
    const copied = display?.result?.meal_nutrition;
    if (original == null || copied == null || original.total === null || copied.total === null) {
      throw new Error("expected cloned nutrition");
    }
    expect(display?.result?.plan.accepted).toBe(true);
    const legacySource = succeededJob(plannedResult({ meal_nutrition: null }));
    const legacy = chatEstimateJob(legacySource);
    expect(legacy?.result?.plan.accepted).toBe(true);
    expect(legacy?.result?.plan.total_cents).toBe(129);
    expect(legacy?.result?.meal_nutrition).toBeUndefined();
    legacySource.result?.plan?.warnings.push("mutated");
    expect(legacy?.result?.plan.warnings).toEqual([]);
    const unavailable = plannedResult({ meal_nutrition: sampleNutrition({ total: null, meals: [] }) });
    expect(chatEstimateJob(succeededJob(unavailable))?.result?.plan.accepted).toBe(true);
    expect(chatEstimateJob(succeededJob(unavailable))?.result?.meal_nutrition?.total).toBeNull();
    original.total.energy_kcal = 1;
    original.meals[0].recipe_id = "mutated";
    copied.meals[0].servings = 8;
    expect(display?.result?.meal_nutrition?.total?.energy_kcal).toBe(200);
    expect(display?.result?.meal_nutrition?.meals[0]?.recipe_id).toBe("bean_tacos");
    expect(source.result?.meal_nutrition?.meals[0]?.servings).toBe(2);
  });
});

describe("formFromChat", () => {
  it("copies meals, diet, pantry, and exclusions and preserves monthly", () => {
    const form: FormState = {
      ...initialForm(),
      monthly: "300",
      cap: "40",
    };
    const result = plannedResult({
      request: {
        meals: [
          { recipe_id: "lentil_soup", servings: 8 },
          { recipe_id: "chickpea_curry", servings: 1 },
          { recipe_id: "overnight_oats", servings: 3 },
        ],
        budget_period: "2026-09-01",
        plan_cap_cents: null,
        pantry_ingredients: ["black_beans"],
        ingredient_exclusions: ["chicken"],
        diet: "vegan",
      },
    });
    const next = formFromChat(form, result);
    expect(next.monthly).toBe("300");
    expect(next.cap).toBe("40");
    expect(next.diet).toBe("vegan");
    expect(next.meals).toEqual([
      { recipe_id: "lentil_soup", servings: 8 },
      { recipe_id: "chickpea_curry", servings: 1 },
      { recipe_id: "overnight_oats", servings: 3 },
    ]);
    expect(next.pantry).toEqual(["black_beans"]);
    expect(next.exclusions).toEqual(["chicken"]);
  });

  it("keeps the smaller non-null cap and formats exact cents", () => {
    const form = { ...initialForm(), monthly: "300", cap: "40" };
    const withCap = (planCapCents: number | null): ChatResult =>
      plannedResult({
        request: {
          meals: [{ recipe_id: "bean_tacos", servings: 2 }],
          budget_period: "2026-09-01",
          plan_cap_cents: planCapCents,
          pantry_ingredients: [],
          ingredient_exclusions: [],
          diet: "omnivore",
        },
      });
    expect(formFromChat(form, withCap(5000)).cap).toBe("40");
    expect(formFromChat(form, withCap(2000)).cap).toBe("20.00");
    expect(formFromChat(form, withCap(4000)).cap).toBe("40");
    expect(formFromChat(form, withCap(null)).cap).toBe("40");
    expect(formFromChat({ ...form, cap: "" }, withCap(1703)).cap).toBe("17.03");
    expect(formFromChat({ ...form, cap: "" }, withCap(1)).cap).toBe("0.01");
    expect(formFromChat({ ...form, cap: "" }, withCap(100000000)).cap).toBe("1000000.00");
    expect(formFromChat({ ...form, cap: "" }, withCap(null)).cap).toBe("");
  });

  it("leaves the form unchanged for a null request or invalid current budget", () => {
    const form = initialForm();
    const nullRequest = plannedResult({ request: null, plan: null, budget: null, status: "limit" });
    expect(formFromChat(form, nullRequest)).toBe(form);
    const invalidMonthly = { ...form, monthly: "1.001" };
    const invalidCap = { ...form, cap: "$1" };
    const valid = plannedResult();
    expect(formFromChat(invalidMonthly, valid)).toBe(invalidMonthly);
    expect(formFromChat(invalidCap, valid)).toBe(invalidCap);
  });

  it("does not mutate the form or the chat result", () => {
    const form: FormState = {
      ...initialForm(),
      pantry: ["salt"],
      meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    };
    const result = plannedResult({
      request: {
        meals: [{ recipe_id: "lentil_soup", servings: 4 }],
        budget_period: "2026-09-01",
        plan_cap_cents: 1703,
        pantry_ingredients: ["black_beans"],
        ingredient_exclusions: ["chicken"],
        diet: "vegetarian",
      },
    });
    const formBefore = structuredClone(form);
    const resultBefore = structuredClone(result);
    const next = formFromChat(form, result);
    next.monthly = "1";
    next.cap = "2";
    next.pantry.push("mutated");
    next.exclusions.push("mutated");
    next.meals[0] = { recipe_id: "overnight_oats", servings: 8 };
    result.request?.meals.push({ recipe_id: "chickpea_curry", servings: 1 });
    result.request?.pantry_ingredients.push("mutated");
    form.meals.push({ recipe_id: "overnight_oats", servings: 1 });
    expect(form.monthly).toBe(formBefore.monthly);
    expect(form.cap).toBe(formBefore.cap);
    expect(next.pantry).toEqual(["black_beans", "mutated"]);
    expect(result.request?.pantry_ingredients).toEqual(["black_beans", "mutated"]);
    expect(formBefore.pantry).toEqual(["salt"]);
    expect(resultBefore.request?.meals).toEqual([{ recipe_id: "lentil_soup", servings: 4 }]);
    expect(next.meals).toEqual([{ recipe_id: "overnight_oats", servings: 8 }]);
  });
});

describe("configFingerprint", () => {
  it("returns an empty fingerprint for a null config", () => {
    expect(configFingerprint(null)).toBe("");
  });

  it("changes when period, source, spending, catalog, or refresh time change", () => {
    const base = configFingerprint(demoConfig);
    expect(base).not.toBe("");
    expect(configFingerprint({ ...demoConfig, budget_period: "2026-10-01" })).not.toBe(base);
    expect(configFingerprint({ ...demoConfig, source: "plaid_sandbox" })).not.toBe(base);
    expect(configFingerprint({ ...demoConfig, posted_cents: 1201 })).not.toBe(base);
    expect(configFingerprint({ ...demoConfig, pending_cents: 0 })).not.toBe(base);
    expect(configFingerprint({ ...demoConfig, catalog_version: "sample-prices-v2" })).not.toBe(base);
    expect(
      configFingerprint({ ...demoConfig, spending_refreshed_at: "2026-09-08T16:00:00Z" }),
    ).not.toBe(base);
    expect(configFingerprint({ ...demoConfig, spending_refreshed_at: null })).not.toBe(base);
    expect(
      configFingerprint({
        ...demoConfig,
        notice: "other",
        recipes: [],
        ingredients: [],
      }),
    ).toBe(base);
  });
});
