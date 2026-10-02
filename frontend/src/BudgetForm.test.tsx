/** @vitest-environment jsdom */

import { createElement, useState, type JSX } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryConfig } from "./apiTypes";
import { BudgetForm, buildRequest, initialForm, type FormState } from "./BudgetForm";

const config: GroceryConfig = {
  budget_period: "2026-09-01",
  source: "fixture",
  catalog_version: "sample-prices-v1",
  posted_cents: 1200,
  pending_cents: -50,
  spending_refreshed_at: "2026-09-07T16:00:00Z",
  notice: SAMPLE_ESTIMATE_NOTICE,
  recipes: [
    { id: "bean_tacos", name: "Bean tacos" },
    { id: "lentil_soup", name: "Lentil soup" },
  ],
  ingredients: [{ id: "black_beans", name: "black beans" }],
};

function renderedText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(root: HTMLElement, name: string): HTMLButtonElement {
  return within(root).getByRole("button", { name }) as HTMLButtonElement;
}

function recipeCount(rendered: RenderResult): number {
  return within(rendered.container).getAllByLabelText(/^Recipe \d+$/).length;
}

function click(root: HTMLElement, name: string): void {
  fireEvent.click(buttonNamed(root, name));
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

function mount(disabled = false): RenderResult {
  return render(createElement(Host, { disabled }));
}

afterEach(cleanup);

describe("initialForm", () => {
  it("returns a fresh default request", () => {
    const first = initialForm();
    const second = initialForm();
    expect(first).not.toBe(second);
    expect(first.meals).not.toBe(second.meals);
    expect(first).toEqual({
      monthly: "100",
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
      monthly_limit_cents: 10000,
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
    const rendered = mount();
    const controls = screen.getAllByLabelText(/.+/);
    const labels = controls.flatMap((control) =>
      Array.from((control as HTMLInputElement | HTMLSelectElement).labels ?? []),
    );
    const fors = labels.map((node) => node.htmlFor);
    const texts = labels.map(renderedText);
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
    const diet = screen.getByRole("combobox", { name: "Diet" });
    expect(within(diet).getAllByRole("option").map(renderedText)).toEqual([
      "No preference",
      "Vegetarian",
      "Vegan",
    ]);
    for (const button of within(rendered.container).queryAllByRole("button")) {
      expect((button as HTMLButtonElement).type).toBe("button");
    }
    const details = screen.getAllByText(/.+/, { selector: "summary" }).map(
      (summary) => summary.closest("details") as HTMLDetailsElement,
    );
    expect(details.every((node) => !node.open)).toBe(true);
    rendered.unmount();
  });

  it("bounds add and remove and disables the fieldset while pending", () => {
    const rendered = mount();
    expect(buttonNamed(rendered.container, "Remove meal 1").disabled).toBe(true);
    expect(buttonNamed(rendered.container, "Add meal").disabled).toBe(false);
    click(rendered.container, "Add meal");
    click(rendered.container, "Add meal");
    expect(recipeCount(rendered)).toBe(3);
    expect(buttonNamed(rendered.container, "Add meal").disabled).toBe(true);
    click(rendered.container, "Add meal");
    expect(recipeCount(rendered)).toBe(3);
    click(rendered.container, "Remove meal 3");
    click(rendered.container, "Remove meal 2");
    expect(recipeCount(rendered)).toBe(1);
    expect(buttonNamed(rendered.container, "Remove meal 1").disabled).toBe(true);
    rendered.unmount();
    const pending = mount(true);
    const fieldset = within(pending.container).getByLabelText("Monthly limit").closest("fieldset");
    expect((fieldset as HTMLFieldSetElement).disabled).toBe(true);
    pending.unmount();
  });
});
