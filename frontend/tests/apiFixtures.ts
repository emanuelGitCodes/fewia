import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  SAMPLE_ESTIMATE_NOTICE,
  type MealPlanNutrition,
} from "../src/apiTypes";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;

export function sampleNutrition(
  overrides: Partial<MealPlanNutrition> = {},
): MealPlanNutrition {
  return {
    notice: NUTRITION_NOTICE,
    portion_notice: NUTRITION_PORTION_NOTICE,
    total: {
      energy_kcal: 200,
      protein_mg: 2000,
      carbohydrate_mg: 4000,
      fat_mg: 1000,
    },
    meals: [
      {
        recipe_id: "bean_tacos",
        servings: 2,
        per_serving: {
          energy_kcal: 100,
          protein_mg: 1000,
          carbohydrate_mg: 2000,
          fat_mg: 500,
        },
        total: {
          energy_kcal: 200,
          protein_mg: 2000,
          carbohydrate_mg: 4000,
          fat_mg: 1000,
        },
      },
    ],
    ...overrides,
  };
}

export function mealPlanNutrition(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return { ...sampleNutrition(), ...overrides };
}

export function line(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ingredient_id: "black_beans",
    name: "black beans",
    unit: "g",
    quantity: 425,
    packages: 1,
    cost_cents: 129,
    from_pantry: false,
    ...overrides,
  };
}

export function plan(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    lines: [line()],
    total_cents: 129,
    accepted: true,
    warnings: [],
    catalog_version: "sample-prices-v1",
    notice: NOTICE,
    ...overrides,
  };
}

export function budget(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    available_cents: 5000,
    pending_cents: 200,
    stale: false,
    warnings: [],
    ...overrides,
  };
}

export function jobResult(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    plan: plan(),
    budget: budget(),
    spending_source: "fixture",
    meal_nutrition: mealPlanNutrition(),
    ...overrides,
  };
}

export function job(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "job-1",
    status: "succeeded",
    result: jobResult(),
    error_code: null,
    ...overrides,
  };
}

export function config(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    budget_period: "2026-09-01",
    source: "fixture",
    posted_cents: 1200,
    pending_cents: -50,
    notice: NOTICE,
    recipes: [{ id: "bean_tacos", name: "Bean tacos" }],
    ingredients: [{ id: "black_beans", name: "black beans" }],
    ...overrides,
  };
}

export function manualConfig(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return config({ source: "manual", ...overrides });
}

export function manualJobResult(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return jobResult({ spending_source: "manual", ...overrides });
}
