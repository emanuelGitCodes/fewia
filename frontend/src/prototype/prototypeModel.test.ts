/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import {
  ESTIMATE_NOTICE,
  PANTRY_IDS,
  RECIPES,
  SERVING_ERROR,
} from "./prototypeData";
import {
  atHomeNames,
  groceryCost,
  groceryLines,
  initialState,
  mealFits,
  packageCount,
  shiftServings,
  shoppingLines,
  toggleChecked,
  togglePantry,
  withBudgetInput,
  withRecipe,
  type PrototypeState,
} from "./prototypeModel";

function costOf(state: PrototypeState): number {
  return groceryCost(groceryLines(state));
}

function pantryAll(state: PrototypeState): PrototypeState {
  return PANTRY_IDS.reduce(
    (current, id) => (current.pantry.includes(id) ? current : togglePantry(current, id)),
    state,
  );
}

describe("packageCount", () => {
  it("uses whole packages and the bean-taco boundary", () => {
    expect(packageCount(360, 425)).toBe(1);
    expect(packageCount(480, 425)).toBe(2);
    expect(packageCount(0, 425)).toBe(0);
  });
});

describe("grocery cost", () => {
  it("prices the initial taco plan at 806 cents", () => {
    expect(costOf(initialState())).toBe(806);
    expect(ESTIMATE_NOTICE).toBe(SAMPLE_ESTIMATE_NOTICE);
  });

  it("adds one olive oil package when oil leaves the pantry", () => {
    const next = togglePantry(initialState(), "olive_oil");
    expect(costOf(next) - costOf(initialState())).toBe(599);
    expect(costOf(next)).toBe(1405);
  });

  it("crosses the black bean package at four taco servings", () => {
    const three = shiftServings(initialState(), 1);
    const four = shiftServings(three, 1);
    expect(three.servings).toBe(3);
    expect(four.servings).toBe(4);
    expect(costOf(three)).toBe(806);
    expect(costOf(four)).toBe(935);
    const beans = groceryLines(four).find((line) => line.ingredientId === "black_beans");
    expect(beans?.packages).toBe(2);
  });

  it("returns zero cost when every ingredient is at home", () => {
    const state = pantryAll(initialState());
    expect(costOf(state)).toBe(0);
    expect(shoppingLines(groceryLines(state))).toEqual([]);
    expect(RECIPES.bean_tacos.nutrition.energyKcal).toBe(379);
  });

  it("changes cost when the meal changes", () => {
    expect(costOf(withRecipe(initialState(), "egg_fried_rice"))).toBe(1164);
    expect(costOf(withRecipe(initialState(), "chickpea_curry"))).toBe(1044);
  });
});

describe("servings and pantry", () => {
  it("keeps servings inside 1 to 8 and reports the bound", () => {
    let state = initialState();
    for (let step = 0; step < 8; step += 1) {
      state = shiftServings(state, -1);
    }
    expect(state.servings).toBe(1);
    expect(state.servingsError).toBe(SERVING_ERROR);
    state = shiftServings(state, 1);
    expect(state.servings).toBe(2);
    expect(state.servingsError).toBeNull();
    for (let step = 0; step < 10; step += 1) {
      state = shiftServings(state, 1);
    }
    expect(state.servings).toBe(8);
    expect(state.servingsError).toBe(SERVING_ERROR);
  });

  it("lists at-home names for the current meal only", () => {
    expect(atHomeNames(initialState())).toEqual(["olive oil", "salt", "ground cumin"]);
    expect(atHomeNames(withRecipe(initialState(), "egg_fried_rice"))).toEqual(["olive oil"]);
  });

  it("clears the shopping checklist when meal, servings, or pantry change", () => {
    const marked = toggleChecked(initialState(), "black_beans");
    expect(marked.checked).toEqual(["black_beans"]);
    expect(withRecipe(marked, "egg_fried_rice").checked).toEqual([]);
    expect(shiftServings(marked, 1).checked).toEqual([]);
    expect(togglePantry(marked, "onion").checked).toEqual([]);
    expect(toggleChecked(marked, "black_beans").checked).toEqual([]);
  });
});

describe("budget", () => {
  it("keeps the last valid cap when the input is invalid", () => {
    const invalid = withBudgetInput(initialState(), "12.345");
    expect(invalid.budgetCents).toBe(4000);
    expect(invalid.budgetInput).toBe("12.345");
    expect(invalid.budgetError).toBe(
      "Enter a non-negative dollar amount with at most two decimal places.",
    );
    expect(mealFits(806, invalid.budgetCents)).toBe(true);
  });

  it("accepts zero and reports a meal that does not fit", () => {
    const zero = withBudgetInput(initialState(), "0");
    expect(zero.budgetCents).toBe(0);
    expect(zero.budgetError).toBeNull();
    expect(mealFits(806, zero.budgetCents)).toBe(false);
    const below = withBudgetInput(initialState(), "5");
    expect(below.budgetCents).toBe(500);
    expect(mealFits(806, below.budgetCents)).toBe(false);
    expect(mealFits(0, 0)).toBe(true);
  });
});
