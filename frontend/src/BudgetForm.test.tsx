/** @vitest-environment node */

import { createElement, useState } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryConfig } from "./apiTypes";
import { BudgetForm, buildRequest, initialForm, type FormState } from "./BudgetForm";

const config: GroceryConfig = {
  budget_period: "2026-09-01",
  source: "fixture",
  posted_cents: 1200,
  pending_cents: -50,
  notice: SAMPLE_ESTIMATE_NOTICE,
  recipes: [
    { id: "bean_tacos", name: "Bean tacos" },
    { id: "lentil_soup", name: "Lentil soup" },
  ],
  ingredients: [{ id: "black_beans", name: "black beans" }],
};

function childText(node: ReactTestInstance): string {
  return node.children
    .map((child) => (typeof child === "string" ? child : childText(child)))
    .join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) {
    throw new Error(`missing button ${name}`);
  }
  return match;
}

function recipeCount(renderer: ReactTestRenderer): number {
  return renderer.root.findAll(
    (node) => typeof node.props.id === "string" && node.props.id.startsWith("recipe-"),
  ).length;
}

function click(root: ReactTestInstance, name: string): void {
  const handler = buttonNamed(root, name).props.onClick as (() => void) | undefined;
  handler?.();
}

function Host(props: { disabled: boolean }): JSX.Element {
  const [value, setValue] = useState(initialForm());
  return createElement(BudgetForm, {
    config,
    value,
    onChange: setValue,
    disabled: props.disabled,
  });
}

function mount(disabled = false): ReactTestRenderer {
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(createElement(Host, { disabled }));
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return renderer;
}

describe("initialForm", () => {
  it("returns a fresh default request", () => {
    const first = initialForm();
    const second = initialForm();
    expect(first).not.toBe(second);
    expect(first.meals).not.toBe(second.meals);
    expect(first).toEqual({
      monthly: "300",
      cap: "40",
      diet: "omnivore",
      pantry: [],
      exclusions: [],
      meals: [{ recipe_id: "bean_tacos", servings: 2 }],
    });
  });
});

describe("buildRequest", () => {
  it("builds the exact job body from the default form", () => {
    expect(buildRequest(config, initialForm())).toEqual({
      monthly_limit_cents: 30000,
      request: {
        meals: [{ recipe_id: "bean_tacos", servings: 2 }],
        diet: "omnivore",
        budget_period: "2026-09-01",
        plan_cap_cents: 4000,
        pantry_ingredients: [],
        ingredient_exclusions: [],
      },
    });
  });

  it("copies arrays and uses the server budget period", () => {
    const state: FormState = {
      ...initialForm(),
      pantry: ["black_beans"],
      exclusions: ["black_beans"],
    };
    const pantry = state.pantry;
    const exclusions = state.exclusions;
    const meals = state.meals;
    const other = { ...config, budget_period: "2026-08-01" };
    const body = buildRequest(other, state);
    expect(body.request.budget_period).toBe("2026-08-01");
    expect(body.request.pantry_ingredients).toEqual(["black_beans"]);
    expect(body.request.ingredient_exclusions).toEqual(["black_beans"]);
    expect(body.request.pantry_ingredients).not.toBe(pantry);
    expect(body.request.ingredient_exclusions).not.toBe(exclusions);
    expect(body.request.meals).not.toBe(meals);
    pantry.push("salt");
    exclusions.push("salt");
    meals.push({ recipe_id: "lentil_soup", servings: 1 });
    expect(body.request.pantry_ingredients).toEqual(["black_beans"]);
    expect(body.request.ingredient_exclusions).toEqual(["black_beans"]);
    expect(body.request.meals).toEqual([{ recipe_id: "bean_tacos", servings: 2 }]);
  });

  it("accepts one to three meals and one to eight servings", () => {
    const one = { ...initialForm(), meals: [{ recipe_id: "bean_tacos", servings: 1 }] };
    const eight = { ...initialForm(), meals: [{ recipe_id: "lentil_soup", servings: 8 }] };
    const three: FormState = {
      ...initialForm(),
      meals: [
        { recipe_id: "bean_tacos", servings: 1 },
        { recipe_id: "lentil_soup", servings: 8 },
        { recipe_id: "bean_tacos", servings: 2 },
      ],
    };
    expect(buildRequest(config, one).request.meals).toHaveLength(1);
    expect(buildRequest(config, eight).request.meals[0]?.servings).toBe(8);
    expect(buildRequest(config, three).request.meals).toHaveLength(3);
    expect(buildRequest(config, { ...initialForm(), cap: "" }).request.plan_cap_cents).toBeNull();
  });

  it("rejects meal and serving bounds and unknown recipes", () => {
    expect(() => buildRequest(config, { ...initialForm(), meals: [] })).toThrow();
    expect(() =>
      buildRequest(config, {
        ...initialForm(),
        meals: [
          { recipe_id: "bean_tacos", servings: 2 },
          { recipe_id: "bean_tacos", servings: 2 },
          { recipe_id: "bean_tacos", servings: 2 },
          { recipe_id: "bean_tacos", servings: 2 },
        ],
      }),
    ).toThrow();
    expect(() =>
      buildRequest(config, { ...initialForm(), meals: [{ recipe_id: "bean_tacos", servings: 0 }] }),
    ).toThrow();
    expect(() =>
      buildRequest(config, { ...initialForm(), meals: [{ recipe_id: "bean_tacos", servings: 9 }] }),
    ).toThrow();
    expect(() =>
      buildRequest(config, { ...initialForm(), meals: [{ recipe_id: "bean_tacos", servings: 1.5 }] }),
    ).toThrow();
    expect(() =>
      buildRequest(config, { ...initialForm(), meals: [{ recipe_id: "unknown", servings: 2 }] }),
    ).toThrow();
    expect(() => buildRequest(config, { ...initialForm(), monthly: "" })).toThrow();
    expect(() => buildRequest(config, { ...initialForm(), monthly: "-1" })).toThrow();
  });
});

describe("BudgetForm", () => {
  it("renders unique labels, diet names, and type=button controls", () => {
    const renderer = mount();
    const labels = renderer.root.findAllByType("label");
    const fors = labels.map((node) => node.props.htmlFor);
    const texts = labels.map(childText);
    expect(new Set(fors).size).toBe(fors.length);
    expect(texts).toEqual(
      expect.arrayContaining([
        "Monthly limit",
        "Plan cap (optional)",
        "Recipe 1",
        "Servings 1",
        "Diet",
        "Pantry black beans",
        "Exclude black beans",
      ]),
    );
    const diet = renderer.root.findByProps({ id: "diet" });
    expect(diet.findAllByType("option").map(childText)).toEqual([
      "No preference",
      "Vegetarian",
      "Vegan",
    ]);
    for (const button of renderer.root.findAllByType("button")) {
      expect(button.props.type).toBe("button");
    }
    expect(renderer.root.findAllByType("details").every((node) => node.props.open !== true)).toBe(
      true,
    );
    renderer.unmount();
  });

  it("bounds add and remove and disables the fieldset while pending", () => {
    const renderer = mount();
    expect(buttonNamed(renderer.root, "Remove meal 1").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Add meal").props.disabled).toBe(false);
    act(() => {
      click(renderer.root, "Add meal");
    });
    act(() => {
      click(renderer.root, "Add meal");
    });
    expect(recipeCount(renderer)).toBe(3);
    expect(buttonNamed(renderer.root, "Add meal").props.disabled).toBe(true);
    act(() => {
      click(renderer.root, "Add meal");
    });
    expect(recipeCount(renderer)).toBe(3);
    act(() => {
      click(renderer.root, "Remove meal 3");
    });
    act(() => {
      click(renderer.root, "Remove meal 2");
    });
    expect(recipeCount(renderer)).toBe(1);
    expect(buttonNamed(renderer.root, "Remove meal 1").props.disabled).toBe(true);
    renderer.unmount();
    const pending = mount(true);
    expect(pending.root.findByType("fieldset").props.disabled).toBe(true);
    pending.unmount();
  });
});
