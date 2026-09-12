/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { describe, expect, it } from "vitest";
import { Nutrition } from "./Nutrition";
import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  type MacroTotals,
  type MealPlanNutrition,
} from "./nutritionTypes";

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function macros(overrides: Partial<MacroTotals> = {}): MacroTotals {
  return {
    energy_kcal: 200,
    protein_mg: 10000,
    carbohydrate_mg: 30000,
    fat_mg: 8000,
    ...overrides,
  };
}

function payload(overrides: Partial<MealPlanNutrition> = {}): MealPlanNutrition {
  return {
    notice: NUTRITION_NOTICE,
    portion_notice: NUTRITION_PORTION_NOTICE,
    total: macros({ energy_kcal: 400, protein_mg: 20000, carbohydrate_mg: 60000, fat_mg: 16000 }),
    meals: [
      {
        recipe_id: "bean_tacos",
        servings: 2,
        per_serving: macros(),
        total: macros({ energy_kcal: 400, protein_mg: 20000, carbohydrate_mg: 60000, fat_mg: 16000 }),
      },
    ],
    ...overrides,
  };
}

function mount(nutrition: MealPlanNutrition | undefined, dirty = false): ReactTestRenderer {
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(createElement(Nutrition, { nutrition, dirty }));
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return renderer;
}

describe("Nutrition", () => {
  it("labels all four macros and converts integer kcal and mg to g, including zero", () => {
    const renderer = mount(
      payload({
        total: macros({ energy_kcal: 0, protein_mg: 0, carbohydrate_mg: 0, fat_mg: 0 }),
        meals: [
          {
            recipe_id: "bean_tacos",
            servings: 1,
            per_serving: macros({ energy_kcal: 0, protein_mg: 0, carbohydrate_mg: 0, fat_mg: 0 }),
            total: macros({ energy_kcal: 0, protein_mg: 0, carbohydrate_mg: 0, fat_mg: 0 }),
          },
        ],
      }),
    );
    const text = childText(renderer.root);
    expect(text).toContain("Calories (kcal)");
    expect(text).toContain("Protein (g)");
    expect(text).toContain("Carbs (g)");
    expect(text).toContain("Fat (g)");
    expect(text).toContain("0 kcal");
    expect(text).toContain("0.0 g");
    expect(text).not.toContain("sodium");
    expect(text).not.toContain("iron");
    renderer.unmount();
    const values = mount(payload());
    const valued = childText(values.root);
    expect(valued).toContain("400 kcal");
    expect(valued).toContain("20.0 g");
    expect(valued).toContain("60.0 g");
    expect(valued).toContain("16.0 g");
    expect(valued).toContain("200 kcal");
    expect(valued).toContain("10.0 g");
    expect(valued).toContain("30.0 g");
    expect(valued).toContain("8.0 g");
    expect(valued).toContain("Bean Tacos");
    expect(valued).toContain("2 servings");
    expect(valued).toContain("Per serving");
    expect(valued).toContain("Total for selected plan");
    expect(valued).toContain(NUTRITION_NOTICE);
    expect(valued).toContain(NUTRITION_PORTION_NOTICE);
    expect(valued).toContain("Estimates use recipe ingredients.");
    expect(valued).toContain("Pantry ingredients are included.");
    expect(valued).toContain("USDA FoodData Central");
    expect(values.root.findByType("a").props.href).toBe("https://fdc.nal.usda.gov/");
    expect(valued).not.toContain("sodium");
    expect(valued).not.toContain("iron");
    values.unmount();
  });

  it("keeps mixed-plan totals apart from each meal per-serving value", () => {
    const renderer = mount(
      payload({
        total: macros({ energy_kcal: 900, protein_mg: 21000, carbohydrate_mg: 99000, fat_mg: 15000 }),
        meals: [
          {
            recipe_id: "bean_tacos",
            servings: 2,
            per_serving: macros({ energy_kcal: 200, protein_mg: 4000, carbohydrate_mg: 20000, fat_mg: 3000 }),
            total: macros({ energy_kcal: 400, protein_mg: 8000, carbohydrate_mg: 40000, fat_mg: 6000 }),
          },
          {
            recipe_id: "lentil_soup",
            servings: 3,
            per_serving: macros({ energy_kcal: 100, protein_mg: 3000, carbohydrate_mg: 13000, fat_mg: 2000 }),
            total: macros({ energy_kcal: 300, protein_mg: 9000, carbohydrate_mg: 39000, fat_mg: 6000 }),
          },
        ],
      }),
    );
    const text = childText(renderer.root);
    expect(text).toContain("900 kcal");
    expect(text).toContain("21.0 g");
    expect(text).toContain("99.0 g");
    expect(text).toContain("15.0 g");
    expect(text).toContain("200 kcal");
    expect(text).toContain("100 kcal");
    expect(text).toContain("4.0 g");
    expect(text).toContain("3.0 g");
    expect(text).toContain("Bean Tacos");
    expect(text).toContain("Lentil Soup");
    expect(text).toContain("2 servings");
    expect(text).toContain("3 servings");
    expect(text).not.toContain("180 kcal");
    expect(text.split("Per serving")).toHaveLength(3);
    expect(text).not.toContain("sodium");
    expect(text).not.toContain("iron");
    renderer.unmount();
  });

  it("shows rebuild copy when nutrition is missing", () => {
    const renderer = mount(undefined);
    const text = childText(renderer.root);
    expect(text).toContain("Estimated nutrition");
    expect(text).toContain("Rebuild this plan to see nutrition.");
    expect(text).not.toContain("Calories (kcal)");
    expect(text).not.toContain("0 kcal");
    expect(text).not.toContain("Nutrition is unavailable for this plan.");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("shows unavailable copy when the plan total is null", () => {
    const renderer = mount({
      notice: NUTRITION_NOTICE,
      portion_notice: NUTRITION_PORTION_NOTICE,
      total: null,
      meals: [],
    });
    const text = childText(renderer.root);
    expect(text).toContain("Nutrition is unavailable for this plan.");
    expect(text).not.toContain("Calories (kcal)");
    expect(text).not.toContain("0 kcal");
    expect(text).not.toContain("0.0 g");
    expect(text).not.toContain("Total for selected plan");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("labels dirty values as the last saved plan", () => {
    const renderer = mount(payload(), true);
    const text = childText(renderer.root);
    expect(text).toContain("Nutrition for previous plan");
    expect(text).toContain("These values belong to the last saved plan.");
    expect(text).toContain("400 kcal");
    expect(text).toContain("200 kcal");
    expect(renderer.root.findByType("h3").children).toEqual([
      "Nutrition for previous plan",
    ]);
    renderer.unmount();
    const missing = mount(undefined, true);
    expect(childText(missing.root)).toContain("Nutrition for previous plan");
    expect(childText(missing.root)).toContain("Rebuild this plan to see nutrition.");
    expect(childText(missing.root)).not.toContain("These values belong to the last saved plan.");
    missing.unmount();
  });
});
