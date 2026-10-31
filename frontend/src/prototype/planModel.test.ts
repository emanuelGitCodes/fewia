/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { INGREDIENTS, RECIPES, SERVING_ERROR, requireIngredient } from "./prototypeData";
import {
  addMeal,
  budgetGap,
  initialPlanState,
  planCost,
  planIncomplete,
  planLines,
  planNutrition,
  previewAdd,
  removeMeal,
  retainChecks,
  shiftMealServings,
  togglePlanChecked,
  togglePlanPantry,
  withPlanBudgetInput,
  withPlanView,
  withProposalSnapshot,
  withSnapshot,
  type PlanState,
  type PlannedMeal,
} from "./planModel";

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
    // Curry powder is a pantry item in the backend catalog, so it costs nothing.
    expect(planCost(planLines(state))).toBe(1542);
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
    expect(planCost(lines)).toBe(2219);
    expect(lineOf(state, "curry_powder")).toMatchObject({ fromPantry: true, costCents: 0 });
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

describe("an ingredient without a sample price", () => {
  it("shows no price for the line and marks the total incomplete", () => {
    const salsa = requireIngredient("salsa");
    INGREDIENTS.salsa = { ...salsa, priceCents: null };
    try {
      const lines = planLines(initialPlanState());
      const line = lines.find((l) => l.ingredientId === "salsa");
      expect(line).toMatchObject({ packages: 1, costCents: 0, unpriced: true });
      expect(planCost(lines)).toBe(806 - 249);
      expect(planIncomplete(lines)).toBe(true);
    } finally {
      INGREDIENTS.salsa = salsa;
    }
    expect(planIncomplete(planLines(initialPlanState()))).toBe(false);
  });

  it("does not mark a pantry line incomplete", () => {
    const salsa = requireIngredient("salsa");
    INGREDIENTS.salsa = { ...salsa, priceCents: null };
    try {
      const state = togglePlanPantry(initialPlanState(), "salsa");
      expect(planIncomplete(planLines(state))).toBe(false);
    } finally {
      INGREDIENTS.salsa = salsa;
    }
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

describe("addMeal servings and unknown recipes", () => {
  it("clamps servings into 1 to 8", () => {
    expect(addMeal(initialPlanState(), "egg_fried_rice", 0).meals[1]?.servings).toBe(1);
    expect(addMeal(initialPlanState(), "egg_fried_rice", 99).meals[1]?.servings).toBe(8);
    expect(addMeal(initialPlanState(), "egg_fried_rice", 5).meals[1]?.servings).toBe(5);
  });

  it("ignores an unknown recipe", () => {
    const state = initialPlanState();
    expect(addMeal(state, "nope")).toBe(state);
    expect(addMeal(state, "constructor")).toBe(state);
  });
});

describe("previewAdd", () => {
  it("matches add and remove prices after shared-package rounding and pantry changes", () => {
    for (const pantry of [[], ["rice", "onion", "salt"]]) {
      const state = {
        ...planOf([{ recipeId: "egg_fried_rice", servings: 8 }]),
        pantry,
        checked: ["rice"],
      };
      for (const servings of [0, 2, 8, 20, Number.NaN]) {
        const preview = previewAdd(state, "chickpea_curry", servings);
        const added = addMeal(state, "chickpea_curry", servings);
        expect(preview.lines).toEqual(planLines(added));
        expect(preview.deltaCents).toBe(planCost(planLines(added)) - planCost(planLines(state)));
        const removal = previewAdd(added, "chickpea_curry", 1);
        expect(removal.lines).toEqual(planLines(added));
        expect(removal.deltaCents).toBe(
          planCost(planLines(added)) - planCost(planLines(removeMeal(added, "chickpea_curry"))),
        );
        expect(state.checked).toEqual(["rice"]);
      }
    }
  });

  it("matches incomplete prices without caching mutable catalog entries", () => {
    const rice = requireIngredient("rice");
    const state = planOf([CURRY]);
    const priced = previewAdd(state, "egg_fried_rice", 2);
    INGREDIENTS.rice = { ...rice, priceCents: null };
    try {
      const preview = previewAdd(state, "egg_fried_rice", 2);
      const added = addMeal(state, "egg_fried_rice", 2);
      expect(preview.lines).toEqual(planLines(added));
      expect(planIncomplete(preview.lines)).toBe(true);
      expect(preview.deltaCents).toBe(planCost(planLines(added)) - planCost(planLines(state)));
      const pantry = togglePlanPantry(state, "rice");
      expect(planIncomplete(previewAdd(pantry, "egg_fried_rice", 2).lines)).toBe(false);
    } finally {
      INGREDIENTS.rice = rice;
    }
    expect(previewAdd(state, "egg_fried_rice", 2)).toEqual(priced);
  });

  it("prices a normal add like a real addMeal", () => {
    const state = initialPlanState();
    const preview = previewAdd(state, "chickpea_curry", 2);
    const real = planCost(planLines(addMeal(state, "chickpea_curry", 2))) - planCost(planLines(state));
    expect(preview).toMatchObject({ inPlan: false, blocked: null, servings: 2 });
    expect(preview.deltaCents).toBe(real);
    expect(preview.lines).toEqual(planLines(addMeal(state, "chickpea_curry", 2)));
  });

  it("blocks an unknown recipe without throwing", () => {
    const state = initialPlanState();
    const preview = previewAdd(state, "nope", 2);
    expect(preview).toMatchObject({ blocked: "unknown_recipe", deltaCents: 0, inPlan: false });
    expect(preview.lines).toEqual(planLines(state));
    expect(preview.sharedIngredientNames).toEqual([]);
  });

  it("reports the saving of a meal already in the plan", () => {
    const state = planOf([TACOS, RICE]);
    const preview = previewAdd(state, "egg_fried_rice", 2);
    const without = planCost(planLines(planOf([TACOS])));
    expect(preview).toMatchObject({ inPlan: true, blocked: null, sharedIngredientNames: [] });
    expect(preview.deltaCents).toBe(planCost(planLines(state)) - without);
    expect(preview.lines).toEqual(planLines(state));
  });

  it("reports the plan's own servings for a planned meal", () => {
    const state = planOf([TACOS, { recipeId: "egg_fried_rice", servings: 5 }]);
    expect(previewAdd(state, "egg_fried_rice", 2).servings).toBe(5);
  });

  it("reports the servings addMeal would use for a new meal", () => {
    const state = initialPlanState();
    expect(previewAdd(state, "chickpea_curry", 20).servings).toBe(8);
    expect(previewAdd(state, "chickpea_curry", 0).servings).toBe(1);
    expect(previewAdd(state, "chickpea_curry", Number.NaN).servings).toBe(2);
    const added = addMeal(state, "chickpea_curry", 20).meals.find((m) => m.recipeId === "chickpea_curry");
    expect(added?.servings).toBe(8);
  });

  it("reports a planned meal in a full plan as in the plan", () => {
    const state = planOf([TACOS, RICE, CURRY]);
    expect(previewAdd(state, "chickpea_curry", 2)).toMatchObject({ inPlan: true, blocked: null });
  });

  it("blocks a new meal when the plan is full", () => {
    const state = planOf([TACOS, RICE, CURRY]);
    const preview = previewAdd(state, "lentil_soup", 2);
    expect(preview).toMatchObject({ inPlan: false, blocked: "plan_full", deltaCents: 0 });
    expect(preview.lines).toEqual(planLines(state));
  });

  it("names ingredients the plan already buys, in recipe order", () => {
    const preview = previewAdd(planOf([RICE]), "chickpea_curry", 2);
    const names = preview.sharedIngredientNames;
    const rice = requireIngredient("rice").name;
    const garlic = requireIngredient("garlic").name;
    expect(names).toContain(rice);
    expect(names).toContain(garlic);
    const recipeOrder = RECIPES.chickpea_curry.ingredients.map(([id]) => requireIngredient(id).name);
    expect(names.map((n) => recipeOrder.indexOf(n))).toEqual(
      names.map((n) => recipeOrder.indexOf(n)).sort((a, b) => a - b),
    );
  });

  it("leaves out pantry ingredients from shared names", () => {
    const preview = previewAdd(initialPlanState(), "egg_fried_rice", 2);
    for (const id of initialPlanState().pantry) {
      expect(preview.sharedIngredientNames).not.toContain(requireIngredient(id).name);
    }
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

describe("withSnapshot", () => {
  const snapshot = {
    meals: [{ recipe_id: "egg_fried_rice", servings: 3 }],
    pantry_ingredient_ids: ["salsa"],
    plan_cap_cents: 2550,
  };

  it("sets meals, pantry, and cap input and keeps the view", () => {
    const state = { ...initialPlanState(), view: "pantry" as const };
    const next = withSnapshot(state, snapshot);
    expect(next.meals).toEqual([{ recipeId: "egg_fried_rice", servings: 3 }]);
    expect(next.pantry).toEqual(["salsa"]);
    expect(next).toMatchObject({
      view: "pantry", budgetCents: 2550, budgetInput: "25.50", budgetError: null,
    });
  });

  it("keeps the cap on null and keeps checks only for lines still present", () => {
    const state = {
      ...togglePlanChecked(togglePlanChecked(initialPlanState(), "salsa"), "onion"),
    };
    const next = withSnapshot(state, { ...snapshot, pantry_ingredient_ids: [], plan_cap_cents: null });
    expect(next.budgetCents).toBe(state.budgetCents);
    expect(next.budgetInput).toBe(state.budgetInput);
    const present = planLines(next).map((line) => line.ingredientId);
    expect(next.checked.every((id) => present.includes(id))).toBe(true);
    expect(next.checked).not.toContain("salsa");
  });
});

describe("withProposalSnapshot", () => {
  it.each(["25.50", "12.345", ""])("preserves the current budget metadata for draft %j", (draft) => {
    const state = {
      ...withPlanBudgetInput(withPlanBudgetInput(initialPlanState(), "17"), draft),
      view: "pantry" as const,
      servingsError: { recipeId: "bean_tacos", message: SERVING_ERROR },
      checked: ["salsa", "onion"],
    };
    const next = withProposalSnapshot(state, {
      meals: [{ recipe_id: "egg_fried_rice", servings: 3 }],
      pantry_ingredient_ids: ["rice"], plan_cap_cents: 4000,
    });
    expect(next).toMatchObject({
      budgetInput: state.budgetInput, budgetCents: state.budgetCents, budgetError: state.budgetError,
      view: "pantry", servingsError: null,
      meals: [{ recipeId: "egg_fried_rice", servings: 3 }], pantry: ["rice"], checked: ["onion"],
    });
    expect(state.checked).toEqual(["salsa", "onion"]);
  });

  it("keeps an invalid draft when the proposal cap is null", () => {
    const state = withPlanBudgetInput(initialPlanState(), "12.345");
    const snapshot = {
      meals: [{ recipe_id: "bean_tacos", servings: 3 }],
      pantry_ingredient_ids: state.pantry, plan_cap_cents: null,
    };
    expect(withProposalSnapshot(state, snapshot)).toEqual({ ...state, meals: [{ recipeId: "bean_tacos", servings: 3 }] });
    expect(snapshot.plan_cap_cents).toBeNull();
  });
});

describe("budget input", () => {
  it("updates the plan budget", () => {
    expect(withPlanBudgetInput(initialPlanState(), "25")).toMatchObject({
      budgetCents: 2500,
      budgetError: null,
    });
  });

  it("sets budgetError and keeps budgetCents for an invalid amount", () => {
    const next = withPlanBudgetInput(initialPlanState(), "12.345");
    expect(next.budgetCents).toBe(4000);
    expect(next.budgetInput).toBe("12.345");
    expect(next.budgetError).not.toBeNull();
  });
});

describe("unchanged state", () => {
  it("returns the same object when removing an unplanned recipe", () => {
    const state = initialPlanState();
    expect(removeMeal(state, "egg_fried_rice")).toBe(state);
  });

  it("returns the same object for the current view", () => {
    const state = initialPlanState();
    expect(withPlanView(state, "plan")).toBe(state);
  });

  it("reports zero nutrition for an empty plan", () => {
    expect(planNutrition(planOf([]))).toEqual({
      energyKcal: 0,
      proteinG: 0,
      carbsG: 0,
      fatG: 0,
    });
  });
});
