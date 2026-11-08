/** @vitest-environment jsdom */

import { createElement, useState, type JSX } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryConfig } from "./apiTypes";
import { AmountValidationError, BudgetForm, buildRequest, initialForm, type FormState } from "./BudgetForm";

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
  it.each([
    ["monthly", "Monthly limit"],
    ["cap", "Plan cap"],
  ] as const)("identifies the invalid %s amount without changing parser rules", (field, label) => {
    for (const value of ["-1", "$40", "1,000", "1.234", "01", "90071992547410"]) {
      try {
        buildRequest(config, { ...initialForm(), [field]: value });
        throw new Error("expected amount validation failure");
      } catch (caught) {
        expect(caught).toBeInstanceOf(AmountValidationError);
        expect((caught as AmountValidationError).field).toBe(field);
        expect((caught as Error).message).toBe(
          `${label}: Enter a non-negative dollar amount with at most two decimal places.`,
        );
      }
    }
    expect(buildRequest(config, { ...initialForm(), [field]: " 40.50 " })).toMatchObject(
      field === "monthly" ? { monthly_limit_cents: 4050 } : { request: { plan_cap_cents: 4050 } },
    );
  });

  it("keeps meal, recipe, serving, monthly, and cap validation order", () => {
    const invalid = { ...initialForm(), monthly: "bad", cap: "bad" };
    expect(() => buildRequest(config, { ...invalid, meals: [] })).toThrow("Choose 1 to 3 meals.");
    expect(() => buildRequest(config, { ...invalid, meals: [{ recipe_id: "unknown", servings: 9 }] }))
      .toThrow("Choose a recipe from the catalog.");
    expect(() => buildRequest(config, { ...invalid, meals: [{ recipe_id: "bean_tacos", servings: 9 }] }))
      .toThrow("Each meal uses 1 to 8 servings.");
    expect(() => buildRequest(config, invalid)).toThrow(/^Monthly limit:/);
    expect(() => buildRequest(config, { ...invalid, monthly: "100" })).toThrow(/^Plan cap:/);
  });
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
  it("associates visible amount guidance and only the invalid field with its error", () => {
    const props = { config, value: initialForm(), onChange: () => undefined, disabled: false };
    const capMessage = "Plan cap: Enter a non-negative dollar amount with at most two decimal places.";
    const monthlyMessage = "Monthly limit: Enter a non-negative dollar amount with at most two decimal places.";
    const rendered = render(createElement(BudgetForm, {
      ...props, validation: { field: "cap", message: capMessage },
    }));
    const monthly = screen.getByLabelText("Monthly limit");
    const cap = screen.getByLabelText("Plan cap (optional)");
    const hint = rendered.container.querySelector("#amount-format");
    expect(hint?.textContent).toContain("100 or 40.50");
    expect(hint?.textContent).toContain("Leave the plan cap blank");
    expect(monthly.getAttribute("aria-describedby")).toBe("amount-format");
    expect(monthly.hasAttribute("aria-invalid")).toBe(false);
    expect(monthly.getAttribute("aria-required")).toBe("true");
    expect(monthly.hasAttribute("required")).toBe(false);
    expect(cap.hasAttribute("aria-required")).toBe(false);
    expect(cap.getAttribute("aria-describedby")).toBe("amount-format form-error");
    expect(cap.getAttribute("aria-invalid")).toBe("true");
    expect(cap.nextElementSibling).toBe(screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toBe(capMessage);
    expect(screen.getByRole("alert").id).toBe("form-error");
    rendered.rerender(createElement(BudgetForm, {
      ...props, validation: { field: "monthly", message: monthlyMessage },
    }));
    expect(monthly.getAttribute("aria-describedby")).toBe("amount-format form-error");
    expect(monthly.getAttribute("aria-invalid")).toBe("true");
    expect(cap.getAttribute("aria-describedby")).toBe("amount-format");
    expect(cap.hasAttribute("aria-invalid")).toBe(false);
    expect(monthly.nextElementSibling).toBe(screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toBe(monthlyMessage);
    expect(rendered.container.querySelectorAll("#form-error")).toHaveLength(1);
    rendered.rerender(createElement(BudgetForm, props));
    expect(screen.queryByRole("alert")).toBeNull();
    for (const input of [monthly, cap]) {
      expect(input.getAttribute("aria-describedby")).toBe("amount-format");
      expect(input.hasAttribute("aria-invalid")).toBe(false);
    }
  });

  it.each(["monthly", "cap"] as const)("omits the %s error association without a message", (field) => {
    render(createElement(BudgetForm, {
      config, value: initialForm(), onChange: () => undefined, disabled: false,
      validation: { field, message: "" },
    }));
    expect(screen.queryByRole("alert")).toBeNull();
    for (const label of ["Monthly limit", "Plan cap (optional)"]) {
      const input = screen.getByLabelText(label);
      expect(input.getAttribute("aria-describedby")).toBe("amount-format");
      expect(input.hasAttribute("aria-invalid")).toBe(false);
    }
  });

  it("focuses each added recipe after commit, including the last allowed row", () => {
    const rendered = mount();
    const add = buttonNamed(rendered.container, "Add meal");
    for (const row of [2, 3]) {
      add.focus();
      click(rendered.container, "Add meal");
      expect(document.activeElement).toBe(screen.getByLabelText(`Recipe ${row}`));
    }
    expect(add.disabled).toBe(true);
  });

  it("focuses the following recipe or the preceding recipe after removal and keeps row data", () => {
    const rendered = mount();
    click(rendered.container, "Add meal");
    click(rendered.container, "Add meal");
    fireEvent.change(screen.getByLabelText("Recipe 3"), { target: { value: "lentil_soup" } });
    fireEvent.change(screen.getByLabelText("Servings 3"), { target: { value: "8" } });
    buttonNamed(rendered.container, "Remove meal 2").focus();
    click(rendered.container, "Remove meal 2");
    expect(document.activeElement).toBe(screen.getByLabelText("Recipe 2"));
    expect((screen.getByLabelText("Recipe 2") as HTMLSelectElement).value).toBe("lentil_soup");
    expect((screen.getByLabelText("Servings 2") as HTMLSelectElement).value).toBe("8");
    buttonNamed(rendered.container, "Remove meal 2").focus();
    click(rendered.container, "Remove meal 2");
    expect(document.activeElement).toBe(screen.getByLabelText("Recipe 1"));
    expect(buttonNamed(rendered.container, "Remove meal 1").disabled).toBe(true);
  });

  it("does not move focus for form changes outside explicit row actions", () => {
    mount();
    const monthly = screen.getByLabelText("Monthly limit");
    monthly.focus();
    fireEvent.change(monthly, { target: { value: "200" } });
    expect(document.activeElement).toBe(monthly);
    const recipe = screen.getByLabelText("Recipe 1");
    recipe.focus();
    fireEvent.change(recipe, { target: { value: "lentil_soup" } });
    expect(document.activeElement).toBe(recipe);
  });
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
