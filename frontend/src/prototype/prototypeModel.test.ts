/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  DIET_LABELS,
  INGREDIENTS,
  INITIAL_PANTRY,
  RECIPES,
  RECIPE_ORDER,
  type Diet,
} from "./prototypeData";
import { formatMacro, packageCount, withBudgetInput } from "./prototypeModel";

const AMOUNT_ERROR = "Enter a non-negative dollar amount with at most two decimal places.";

function budgetOf(budgetInput: string, budgetCents: number) {
  return { budgetInput, budgetCents, budgetError: null as string | null };
}

describe("packageCount", () => {
  it("uses whole packages and the bean-taco boundary", () => {
    expect(packageCount(360, 425)).toBe(1);
    expect(packageCount(480, 425)).toBe(2);
    expect(packageCount(0, 425)).toBe(0);
  });
});

describe("withBudgetInput", () => {
  it("keeps the last valid cap when the input is invalid", () => {
    const invalid = withBudgetInput(budgetOf("40", 4000), "12.345");
    expect(invalid.budgetCents).toBe(4000);
    expect(invalid.budgetInput).toBe("12.345");
    expect(invalid.budgetError).toBe(AMOUNT_ERROR);
  });

  it("accepts zero and a valid amount and clears the error", () => {
    const failed = withBudgetInput(budgetOf("40", 4000), "abc");
    expect(failed.budgetError).toBe(AMOUNT_ERROR);
    const zero = withBudgetInput(failed, "0");
    expect(zero).toMatchObject({ budgetInput: "0", budgetCents: 0, budgetError: null });
    const five = withBudgetInput(zero, "5");
    expect(five).toMatchObject({ budgetInput: "5", budgetCents: 500, budgetError: null });
  });
});

describe("formatMacro", () => {
  it("shows whole numbers plainly and others with one decimal", () => {
    expect(formatMacro(379)).toBe("379");
    expect(formatMacro(14.5)).toBe("14.5");
    expect(formatMacro(12.34)).toBe("12.3");
  });
});

describe("prototype recipes", () => {
  it("lists forty unique recipe ids that all have entries", () => {
    expect(RECIPE_ORDER).toHaveLength(40);
    expect(new Set(RECIPE_ORDER).size).toBe(40);
    for (const id of RECIPE_ORDER) {
      expect(RECIPES[id]).toBeDefined();
    }
  });

  it("uses only catalog ingredients", () => {
    for (const id of RECIPE_ORDER) {
      for (const [ingredientId] of RECIPES[id].ingredients) {
        expect(INGREDIENTS[ingredientId]).toBeDefined();
      }
    }
  });

  it("covers both diets and lists vegan recipes as vegetarian too", () => {
    for (const diet of Object.keys(DIET_LABELS) as Diet[]) {
      expect(RECIPE_ORDER.some((id) => RECIPES[id].diets.includes(diet))).toBe(true);
    }
    for (const id of RECIPE_ORDER) {
      if (RECIPES[id].diets.includes("vegan")) {
        expect(RECIPES[id].diets).toContain("vegetarian");
      }
    }
  });

  it("uses integer-cent prices and the pantry flags for the initial pantry", () => {
    for (const item of Object.values(INGREDIENTS)) {
      expect(item.priceCents === null || Number.isInteger(item.priceCents)).toBe(true);
    }
    expect(INITIAL_PANTRY).toEqual(
      Object.values(INGREDIENTS)
        .filter((item) => item.isPantry)
        .map((item) => item.id),
    );
  });

  it("keeps photos for three recipes only", () => {
    const withPhoto = RECIPE_ORDER.filter((id) => RECIPES[id].image !== null).sort();
    expect(withPhoto).toEqual(["bean_tacos", "chickpea_curry", "egg_fried_rice"]);
    expect(RECIPES.bean_tacos.image).toBe("/prototype/bean-tacos.webp");
  });
});
