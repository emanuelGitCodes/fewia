/** @vitest-environment jsdom */

import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  type CatalogItem,
  type MacroTotals,
  type MealPlanNutrition,
} from "./apiTypes";
import { Nutrition } from "./Nutrition";

function renderedText(node: HTMLElement): string {
  return node.textContent ?? "";
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
): RenderResult {
  return render(
    createElement(Nutrition, {
      nutrition: props.nutrition ?? nutrition(),
      recipes: props.recipes ?? RECIPES,
    }),
  );
}

afterEach(cleanup);

describe("Nutrition", () => {
  it("renders the total row, per-meal rows, and grams conversion", () => {
    const rendered = mount();
    const text = renderedText(rendered.container);
    expect(screen.getByText("Estimated nutrition").textContent).toContain("Estimated nutrition");
    expect(text).toContain("Plan total");
    expect(text).toContain("450 kcal");
    expect(text).toContain("12.3 g");
    expect(text).toContain("Bean tacos");
    expect(text).toContain("2 servings");
    expect(text).toContain("Per serving");
    expect(text).toContain("Meal total");
    rendered.unmount();
  });

  it("renders a singular serving label for one serving", () => {
    const rendered = mount({
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
    const text = renderedText(rendered.container);
    expect(text).toContain("1 serving");
    expect(text).not.toContain("1 servings");
    rendered.unmount();
  });

  it("renders both notices as text", () => {
    const rendered = mount();
    expect(screen.getByText(NUTRITION_NOTICE).textContent).toContain(NUTRITION_NOTICE);
    expect(screen.getByText(NUTRITION_PORTION_NOTICE).textContent).toContain(NUTRITION_PORTION_NOTICE);
    rendered.unmount();
  });

  it("omits the total row when total is null", () => {
    const rendered = mount({ nutrition: nutrition({ total: null }) });
    const text = renderedText(rendered.container);
    expect(screen.getByText("Estimated nutrition").textContent).toContain("Estimated nutrition");
    expect(text).toContain("Bean tacos");
    expect(text).not.toContain("Plan total");
    rendered.unmount();
  });

  it("falls back to recipe_id when recipes has no match", () => {
    const rendered = mount({ recipes: [] });
    const text = renderedText(rendered.container);
    expect(text).toContain("bean_tacos");
    expect(text).not.toContain("Bean tacos");
    rendered.unmount();
  });
});
