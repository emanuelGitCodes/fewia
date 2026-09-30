/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { describe, expect, it } from "vitest";
import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  type CatalogItem,
  type MacroTotals,
  type MealPlanNutrition,
} from "./apiTypes";
import { Nutrition } from "./Nutrition";

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function macros(overrides: Partial<MacroTotals> = {}): MacroTotals {
  return {
    energy_kcal: 450,
    protein_mg: 12345,
    carbohydrate_mg: 2000,
    fat_mg: 1000,
    ...overrides,
  };
}

function nutrition(overrides: Partial<MealPlanNutrition> = {}): MealPlanNutrition {
  return {
    notice: NUTRITION_NOTICE,
    portion_notice: NUTRITION_PORTION_NOTICE,
    total: macros(),
    meals: [
      {
        recipe_id: "bean_tacos",
        servings: 2,
        per_serving: macros({
          energy_kcal: 225,
          protein_mg: 6172,
          carbohydrate_mg: 1000,
          fat_mg: 500,
        }),
        total: macros(),
      },
    ],
    ...overrides,
  };
}

const RECIPES: CatalogItem[] = [{ id: "bean_tacos", name: "Bean tacos" }];

function mount(
  props: { nutrition?: MealPlanNutrition; recipes?: CatalogItem[] } = {},
): ReactTestRenderer {
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(
      createElement(Nutrition, {
        nutrition: props.nutrition ?? nutrition(),
        recipes: props.recipes ?? RECIPES,
      }),
    );
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return renderer;
}

describe("Nutrition", () => {
  it("renders the total row, per-meal rows, and grams conversion", () => {
    const renderer = mount();
    const text = childText(renderer.root);
    expect(text).toContain("Estimated nutrition");
    expect(text).toContain("Plan total");
    expect(text).toContain("450 kcal");
    expect(text).toContain("12.3 g");
    expect(text).toContain("Bean tacos");
    expect(text).toContain("2 servings");
    expect(text).toContain("Per serving");
    expect(text).toContain("Meal total");
    renderer.unmount();
  });

  it("renders a singular serving label for one serving", () => {
    const renderer = mount({
      nutrition: nutrition({
        meals: [
          {
            recipe_id: "bean_tacos",
            servings: 1,
            per_serving: macros({
              energy_kcal: 225,
              protein_mg: 6172,
              carbohydrate_mg: 1000,
              fat_mg: 500,
            }),
            total: macros(),
          },
        ],
      }),
    });
    const text = childText(renderer.root);
    expect(text).toContain("1 serving");
    expect(text).not.toContain("1 servings");
    renderer.unmount();
  });

  it("renders both notices as text", () => {
    const renderer = mount();
    const text = childText(renderer.root);
    expect(text).toContain(NUTRITION_NOTICE);
    expect(text).toContain(NUTRITION_PORTION_NOTICE);
    renderer.unmount();
  });

  it("omits the total row when total is null", () => {
    const renderer = mount({ nutrition: nutrition({ total: null }) });
    const text = childText(renderer.root);
    expect(text).toContain("Estimated nutrition");
    expect(text).toContain("Bean tacos");
    expect(text).not.toContain("Plan total");
    renderer.unmount();
  });

  it("falls back to recipe_id when recipes has no match", () => {
    const renderer = mount({ recipes: [] });
    const text = childText(renderer.root);
    expect(text).toContain("bean_tacos");
    expect(text).not.toContain("Bean tacos");
    renderer.unmount();
  });
});
