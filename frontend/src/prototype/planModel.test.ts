/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SERVING_ERROR } from "./prototypeData";
import {
  addMeal,
  budgetGap,
  initialPlanState,
  planCost,
  planLines,
  planNutrition,
  removeMeal,
  retainChecks,
  shiftMealServings,
  togglePlanChecked,
  togglePlanPantry,
  withPlanBudgetInput,
  withPlanView,
  type PlanState,
  type PlannedMeal,
} from "./planModel";
import { initialState, withBudgetInput } from "./prototypeModel";

function planOf(meals: PlannedMeal[]): PlanState {
  return { ...initialPlanState(), meals };
}

function lineOf(state: PlanState, id: string) {
  const line = planLines(state).find((l) => l.ingredientId === id);
  if (line === undefined) {
    throw new Error(`missing line ${id}`);
  }
  return line;
}

const TACOS = { recipeId: "bean_tacos", servings: 2 } as const;
const RICE = { recipeId: "egg_fried_rice", servings: 2 } as const;
const CURRY = { recipeId: "chickpea_curry", servings: 2 } as const;

describe("planLines", () => {
  it("prices the initial taco plan at 806 cents", () => {
    const lines = planLines(initialPlanState());
    expect(planCost(lines)).toBe(806);
    expect(lines.filter((l) => !l.fromPantry)).toHaveLength(4);
  });

  it("buys a shared package once across rice and curry", () => {
    const state = planOf([RICE, CURRY]);
    expect(planCost(planLines(state))).toBe(1791);
    const rice = lineOf(state, "rice");
    expect(rice.quantity).toBe(300);
    expect(rice.packages).toBe(1);
    expect(rice.usedIn).toEqual(["egg_fried_rice", "chickpea_curry"]);
    expect(lineOf(state, "onion")).toMatchObject({ quantity: 140, packages: 1 });
    expect(lineOf(state, "garlic")).toMatchObject({ quantity: 20, packages: 1 });
  });

  it("prices three meals and keeps first-appearance order", () => {
    const state = planOf([TACOS, RICE, CURRY]);
    const lines = planLines(state);
    expect(planCost(lines)).toBe(2468);
    expect(lineOf(state, "onion")).toMatchObject({ quantity: 200, packages: 1 });
    expect(lines.map((l) => l.ingredientId)).toEqual([
      "black_beans",
      "tortillas",
      "salsa",
      "onion",
      "cumin",
      "olive_oil",
      "salt",
      "eggs",
      "rice",
      "mixed_vegetables",
      "soy_sauce",
      "garlic",
      "chickpeas",
      "coconut_milk",
      "curry_powder",
    ]);
    expect(lineOf(state, "onion").usedIn).toEqual([
      "bean_tacos",
      "egg_fried_rice",
      "chickpea_curry",
    ]);
  });

  it("rounds the summed onion up to two packages at eight servings", () => {
    const state = planOf([
      { recipeId: "bean_tacos", servings: 8 },
      { recipeId: "egg_fried_rice", servings: 8 },
    ]);
    expect(lineOf(state, "onion")).toMatchObject({ quantity: 480, packages: 2 });
  });
});

describe("planNutrition", () => {
  it("sums per-serving values times servings", () => {
    expect(planNutrition(planOf([TACOS, RICE]))).toEqual({
      energyKcal: 1938,
      proteinG: 73.8,
      carbsG: 265,
      fatG: 65.8,
    });
  });
});

describe("budgetGap", () => {
  it("reports under, exactly at, and over the cap", () => {
    expect(budgetGap(800, 1000)).toEqual({ fits: true, gapCents: 200 });
    expect(budgetGap(1000, 1000)).toEqual({ fits: true, gapCents: 0 });
    expect(budgetGap(1250, 1000)).toEqual({ fits: false, gapCents: 250 });
  });
});

describe("meal list", () => {
  it("ignores a duplicate meal", () => {
    const state = initialPlanState();
    expect(addMeal(state, "bean_tacos")).toBe(state);
  });

  it("ignores a new meal at the cap", () => {
    const full = planOf([TACOS, TACOS, TACOS]);
    expect(addMeal(full, "egg_fried_rice")).toBe(full);
  });

  it("appends a meal with the initial servings", () => {
    const next = addMeal(initialPlanState(), "egg_fried_rice");
    expect(next.meals).toEqual([TACOS, RICE]);
  });

  it("allows an empty plan with no lines and zero cost", () => {
    const empty = removeMeal(initialPlanState(), "bean_tacos");
    expect(empty.meals).toEqual([]);
    expect(planLines(empty)).toEqual([]);
    expect(planCost(planLines(empty))).toBe(0);
  });
});

describe("shiftMealServings", () => {
  it("names the recipe when going below one or above eight", () => {
    const low = shiftMealServings(planOf([{ recipeId: "bean_tacos", servings: 1 }]), "bean_tacos", -1);
    expect(low.servingsError).toEqual({ recipeId: "bean_tacos", message: SERVING_ERROR });
    expect(low.meals[0]?.servings).toBe(1);
    const high = shiftMealServings(planOf([{ recipeId: "egg_fried_rice", servings: 8 }]), "egg_fried_rice", 1);
    expect(high.servingsError).toEqual({ recipeId: "egg_fried_rice", message: SERVING_ERROR });
    expect(high.meals[0]?.servings).toBe(8);
  });

  it("clears the error on success and on a view change", () => {
    const failed = shiftMealServings(planOf([{ recipeId: "bean_tacos", servings: 1 }]), "bean_tacos", -1);
    const ok = shiftMealServings(failed, "bean_tacos", 1);
    expect(ok.servingsError).toBeNull();
    expect(ok.meals[0]?.servings).toBe(2);
    expect(withPlanView(failed, "pantry").servingsError).toBeNull();
  });
});

describe("retainChecks", () => {
  it("keeps a salsa check when egg fried rice is added", () => {
    const state = togglePlanChecked(initialPlanState(), "salsa");
    expect(addMeal(state, "egg_fried_rice").checked).toEqual(["salsa"]);
  });

  it("drops an onion check when its packages change", () => {
    const state = {
      ...planOf([
        { recipeId: "bean_tacos", servings: 8 },
        { recipeId: "egg_fried_rice", servings: 7 },
      ]),
      checked: ["onion"],
    };
    expect(lineOf(state, "onion").packages).toBe(1);
    expect(shiftMealServings(state, "egg_fried_rice", 1).checked).toEqual([]);
  });

  it("drops a check when the item is marked at home", () => {
    const state = togglePlanChecked(initialPlanState(), "salsa");
    expect(togglePlanPantry(state, "salsa").checked).toEqual([]);
  });

  it("drops a check for an ingredient that left the plan", () => {
    const state = togglePlanChecked(initialPlanState(), "salsa");
    const next = removeMeal(state, "bean_tacos");
    expect(retainChecks(planLines(state), planLines(next), state.checked)).toEqual([]);
    expect(next.checked).toEqual([]);
  });
});

describe("budget input", () => {
  it("updates the plan budget", () => {
    expect(withPlanBudgetInput(initialPlanState(), "25")).toMatchObject({
      budgetCents: 2500,
      budgetError: null,
    });
  });

  it("still works on the single-meal state", () => {
    expect(withBudgetInput(initialState(), "25")).toMatchObject({
      budgetInput: "25",
      budgetCents: 2500,
      budgetError: null,
    });
  });
});
