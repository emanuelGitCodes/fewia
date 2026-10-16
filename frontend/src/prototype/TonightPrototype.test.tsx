/** @vitest-environment jsdom */

import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import {
  INITIAL_PANTRY,
  PANTRY_IDS,
  SERVING_ERROR,
  requireIngredient,
} from "./prototypeData";
import { TonightPrototype } from "./TonightPrototype";

const AMOUNT_ERROR = "Enter a non-negative dollar amount with at most two decimal places.";
const FIT_INITIAL = "$31.94 left under the $40.00 plan cap.";
const TACO_MACROS = "379 kcal · 14.5 g protein · 55.8 g carbs · 12.3 g fat per serving";
const RICE_MACROS = "590 kcal · 22.4 g protein · 76.7 g carbs · 20.6 g fat per serving";

function textOf(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

function click(name: string): void {
  act(() => {
    fireEvent.click(buttonNamed(name));
  });
}

function clickTimes(name: string, count: number): void {
  for (let step = 0; step < count; step += 1) {
    click(name);
  }
}

function mount(): HTMLElement {
  return render(createElement(TonightPrototype)).container;
}

function card(meal: string): HTMLElement {
  return screen.getByRole("article", { name: meal });
}

function mainText(): string {
  return textOf(screen.getByRole("main"));
}

function statusText(): string {
  const statuses = screen.getAllByRole("status");
  expect(statuses).toHaveLength(1);
  return textOf(statuses[0]);
}

function summaryText(): string {
  return textOf(screen.getByRole("region", { name: "Plan summary" }));
}

function shoppingSection(): HTMLElement {
  return screen.getByRole("region", { name: "Shopping list" });
}

function navButtons(): HTMLElement[] {
  return within(screen.getByRole("navigation", { name: "Prototype sections" })).getAllByRole("button");
}

function pantryBox(id: string): HTMLInputElement {
  return screen.getByLabelText(requireIngredient(id).name) as HTMLInputElement;
}

function checkRemainingPantry(): void {
  for (const id of PANTRY_IDS) {
    const box = pantryBox(id);
    if (!box.checked) {
      fireEvent.click(box);
    }
  }
}

function clearMealPantry(): void {
  for (const id of INITIAL_PANTRY) {
    const box = pantryBox(id);
    if (box.checked) {
      fireEvent.click(box);
    }
  }
}

beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TonightPrototype", () => {
  it("renders the initial taco plan at $8.06", () => {
    const root = mount();
    const text = textOf(root);
    expect(text).toContain("FEWIA");
    expect(text).toContain("Demo data");
    expect(screen.getByRole("heading", { name: "Your plan" })).toBeTruthy();
    expect(text).toContain("Groceries to buy");
    expect(text).toContain("$8.06");
    expect(text).toContain("Whole packages");
    expect(text).toContain(SAMPLE_ESTIMATE_NOTICE);
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(textOf(card("Bean tacos"))).toContain("2 servings");
    expect(textOf(card("Bean tacos"))).toContain(TACO_MACROS);
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("true");
    expect(textOf(buttonNamed("3 at home, Edit pantry"))).toMatch(/3 at home/);
    expect(screen.getByRole("link", { name: "Existing app" }).getAttribute("href")).toBe("/");
  });

  it("adds Egg fried rice as a second card at $18.41", () => {
    mount();
    click("Egg fried rice");
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(textOf(card("Bean tacos"))).toContain("2 servings");
    expect(textOf(card("Egg fried rice"))).toContain("2 servings");
    expect(textOf(card("Egg fried rice"))).toContain(RICE_MACROS);
    expect(mainText()).toContain("$18.41");
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("true");
  });

  it("adds all three meals at 2 servings for $24.68", () => {
    mount();
    click("Egg fried rice");
    click("Chickpea curry");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(mainText()).toContain("$24.68");
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed("Chickpea curry").getAttribute("aria-pressed")).toBe("true");
  });

  it("shows an empty plan at $0.00 after every meal is removed", () => {
    mount();
    click("Egg fried rice");
    click("Remove Bean tacos");
    expect(screen.queryByRole("article", { name: "Bean tacos" })).toBeNull();
    expect(screen.getAllByRole("article")).toHaveLength(1);
    click("Remove Egg fried rice");
    expect(screen.queryAllByRole("article")).toHaveLength(0);
    expect(mainText()).toContain("Add a meal to start your plan.");
    expect(mainText()).toContain("$0.00");
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("false");
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("false");
  });

  it("removes a planned meal with the picker toggle", () => {
    mount();
    click("Egg fried rice");
    click("Bean tacos");
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("article", { name: "Bean tacos" })).toBeNull();
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("true");
    expect(mainText()).toContain("$11.64");
  });

  it("moves focus to the plan heading after the card button removes a meal", () => {
    mount();
    click("Remove Bean tacos");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your plan" }));
  });

  it("moves focus to the plan heading after the picker removes a meal", () => {
    mount();
    click("Egg fried rice");
    click("Bean tacos");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your plan" }));
  });

  it("keeps focus on the picker button after the picker adds a meal", () => {
    mount();
    const button = buttonNamed("Egg fried rice");
    button.focus();
    click("Egg fried rice");
    expect(document.activeElement).toBe(button);
  });

  it("adds $5.99 when olive oil leaves the pantry", () => {
    mount();
    click("3 at home, Edit pantry");
    act(() => {
      fireEvent.click(screen.getByLabelText("olive oil"));
    });
    click("Back to plan");
    expect(mainText()).toContain("$14.05");
  });

  it("crosses the taco bean package at four servings", () => {
    mount();
    click("Increase servings for Bean tacos");
    expect(mainText()).toContain("$8.06");
    click("Increase servings for Bean tacos");
    expect(textOf(card("Bean tacos"))).toContain("4 servings");
    expect(mainText()).toContain("$9.35");
  });

  it("keeps nutrition when every ingredient is at home", () => {
    mount();
    click("Pantry");
    act(() => {
      checkRemainingPantry();
    });
    click("Plan");
    expect(mainText()).toContain("$0.00");
    expect(textOf(card("Bean tacos"))).toContain(TACO_MACROS);
    expect(textOf(shoppingSection())).toContain("Nothing to buy. Every ingredient is marked at home.");
  });

  it("shows a serving bound message at 1 and 8", () => {
    mount();
    click("Increase servings for Bean tacos");
    click("Decrease servings for Bean tacos");
    click("Decrease servings for Bean tacos");
    expect(textOf(card("Bean tacos"))).toContain("1 serving");
    expect(screen.queryByRole("alert")).toBeNull();
    click("Decrease servings for Bean tacos");
    expect(textOf(within(card("Bean tacos")).getByRole("alert"))).toBe(SERVING_ERROR);
    expect(textOf(card("Bean tacos"))).toContain("1 serving");
    clickTimes("Increase servings for Bean tacos", 8);
    expect(textOf(card("Bean tacos"))).toContain("8 servings");
    expect(textOf(within(card("Bean tacos")).getByRole("alert"))).toBe(SERVING_ERROR);
  });

  it("keeps a serving bound message inside its own card", () => {
    mount();
    click("Egg fried rice");
    clickTimes("Decrease servings for Egg fried rice", 2);
    expect(within(card("Egg fried rice")).getByRole("alert")).toBeTruthy();
    expect(within(card("Bean tacos")).queryByRole("alert")).toBeNull();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(textOf(card("Bean tacos"))).toContain("2 servings");
  });

  it("edits the plan cap without replacing the last valid budget", () => {
    mount();
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    expect(
      within(screen.getByRole("navigation", { name: "Prototype sections" })).getByRole("button", {
        name: "Plan",
      }).getAttribute("aria-current"),
    ).toBe("page");
    expect(summaryText()).toContain(FIT_INITIAL);
    act(() => {
      fireEvent.change(input, { target: { value: "12.345" } });
    });
    expect(mainText()).toContain(AMOUNT_ERROR);
    expect(summaryText()).toContain(FIT_INITIAL);
    act(() => {
      fireEvent.change(input, { target: { value: "0" } });
    });
    expect(summaryText()).toContain("$8.06 over the $0.00 plan cap.");
    act(() => {
      fireEvent.change(input, { target: { value: "5" } });
    });
    expect(summaryText()).toContain("$3.06 over the $5.00 plan cap.");
    expect(mainText()).toContain(SAMPLE_ESTIMATE_NOTICE);
  });

  it("checks shopping items without changing cost and clears stale checks", () => {
    mount();
    expect(summaryText()).toContain("$8.06");
    const shopBox = (name: RegExp) =>
      within(shoppingSection()).getByLabelText(name) as HTMLInputElement;
    const salsa = shopBox(/salsa/);
    const onion = shopBox(/onion/);
    act(() => {
      fireEvent.click(salsa);
      fireEvent.click(onion);
    });
    expect(salsa.checked).toBe(true);
    expect(onion.checked).toBe(true);
    expect(summaryText()).toContain("$8.06");
    expect(summaryText()).toContain(FIT_INITIAL);
    click("Egg fried rice");
    expect(shopBox(/salsa/).checked).toBe(true);
    expect(shopBox(/onion/).checked).toBe(true);
    // Tacos at 8 servings plus rice at 8 servings need 480 g of onion, two packages.
    clickTimes("Increase servings for Bean tacos", 6);
    clickTimes("Increase servings for Egg fried rice", 6);
    expect(shopBox(/salsa/).checked).toBe(true);
    expect(shopBox(/onion/).checked).toBe(false);
    expect(
      within(screen.getByRole("navigation", { name: "Prototype sections" })).getByRole("button", {
        name: "Plan",
      }).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("moves focus with the view and keeps budget typing", () => {
    const root = mount();
    const canvas = root.querySelector(".tonight-canvas");
    if (!(canvas instanceof HTMLElement)) {
      throw new Error("Missing tonight canvas");
    }
    const planHeading = screen.getByRole("heading", { name: "Your plan" });
    expect(document.activeElement).not.toBe(planHeading);
    canvas.scrollTop = 48;
    click("Pantry");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Pantry" }));
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
    const oil = screen.getByLabelText("olive oil");
    act(() => {
      oil.focus();
      fireEvent.click(oil);
    });
    expect(document.activeElement).toBe(oil);
    canvas.scrollTop = 48;
    click("Plan");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your plan" }));
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    act(() => {
      input.focus();
      fireEvent.change(input, { target: { value: "12" } });
    });
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("12");
    act(() => {
      fireEvent.change(input, { target: { value: "12.5" } });
    });
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("12.5");
  });

  it("includes pantry status and edit action in the control name", () => {
    mount();
    const withItems = buttonNamed("3 at home, Edit pantry");
    expect(textOf(withItems)).toContain("3 at home");
    expect(withItems.getAttribute("aria-label")).toBe("3 at home, Edit pantry");
    click("3 at home, Edit pantry");
    act(() => {
      clearMealPantry();
    });
    click("Back to plan");
    const empty = buttonNamed("None marked, Edit pantry");
    expect(textOf(empty)).toContain("None marked");
    expect(empty.getAttribute("aria-label")).toBe("None marked, Edit pantry");
  });

  it("exposes selected meal and current section as semantic state", () => {
    mount();
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("false");
    expect(buttonNamed("Chickpea curry").getAttribute("aria-pressed")).toBe("false");
    const nav = within(screen.getByRole("navigation", { name: "Prototype sections" }));
    expect(nav.getByRole("button", { name: "Plan" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Pantry" }).hasAttribute("aria-current")).toBe(false);
    expect(navButtons().map((button) => textOf(button))).toEqual(["Plan", "Pantry"]);
    click("Chickpea curry");
    expect(buttonNamed("Chickpea curry").getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("false");
    click("Pantry");
    expect(nav.getByRole("button", { name: "Pantry" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Plan" }).hasAttribute("aria-current")).toBe(false);
  });

  it("keeps one Plan estimate status for recipe and serving changes", () => {
    mount();
    expect(statusText()).toBe(
      "1 meal, 2 servings. Groceries to buy $8.06. $31.94 left under the $40.00 plan cap. Whole packages · Sample estimate.",
    );
    click("Egg fried rice");
    expect(statusText()).toBe(
      "2 meals, 4 servings. Groceries to buy $18.41. $21.59 left under the $40.00 plan cap. Whole packages · Sample estimate.",
    );
    click("Egg fried rice");
    expect(statusText()).toBe(
      "1 meal, 2 servings. Groceries to buy $8.06. $31.94 left under the $40.00 plan cap. Whole packages · Sample estimate.",
    );
    click("Increase servings for Bean tacos");
    expect(statusText()).toBe(
      "1 meal, 3 servings. Groceries to buy $8.06. $31.94 left under the $40.00 plan cap. Whole packages · Sample estimate.",
    );
    click("Increase servings for Bean tacos");
    expect(statusText()).toBe(
      "1 meal, 4 servings. Groceries to buy $9.35. $30.65 left under the $40.00 plan cap. Whole packages · Sample estimate.",
    );
  });

  it("keeps the estimate status still when a serving bound is rejected", () => {
    mount();
    click("Decrease servings for Bean tacos");
    const boundText =
      "1 meal, 1 serving. Groceries to buy $8.06. $31.94 left under the $40.00 plan cap. Whole packages · Sample estimate.";
    expect(statusText()).toBe(boundText);
    click("Decrease servings for Bean tacos");
    expect(statusText()).toBe(boundText);
    expect(textOf(screen.getByRole("alert"))).toBe(SERVING_ERROR);
    expect(textOf(card("Bean tacos"))).toContain("1 serving");
  });

  it("clears a rejected serving alert after leaving Plan", () => {
    mount();
    clickTimes("Increase servings for Bean tacos", 6);
    expect(textOf(card("Bean tacos"))).toContain("8 servings");
    click("Increase servings for Bean tacos");
    expect(textOf(screen.getByRole("alert"))).toBe(SERVING_ERROR);
    click("Plan");
    expect(textOf(screen.getByRole("alert"))).toBe(SERVING_ERROR);
    expect(textOf(card("Bean tacos"))).toContain("8 servings");
    click("Pantry");
    click("Plan");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(textOf(card("Bean tacos"))).toContain("8 servings");
    expect(mainText()).not.toContain(SERVING_ERROR);
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your plan" }));
  });

  it("shows the fit line and plan total nutrition", () => {
    mount();
    const fit = screen.getByText(FIT_INITIAL);
    expect(fit.getAttribute("role")).toBeNull();
    const total = within(screen.getByRole("region", { name: "Plan summary" }));
    const expected: ReadonlyArray<readonly [string, string]> = [
      ["758", "kcal"],
      ["29", "g protein"],
      ["111.6", "g carbs"],
      ["24.6", "g fat"],
    ];
    for (const [value, label] of expected) {
      expect(textOf(total.getByText(value).parentElement as HTMLElement)).toBe(`${value}${label}`);
    }
    expect(total.getByText("Demo estimates")).toBeTruthy();
  });

  it("shows the lines that each ingredient is used in", () => {
    mount();
    click("Egg fried rice");
    expect(
      screen.getByText("1 package · $1.29 · Used in Bean tacos, Egg fried rice"),
    ).toBeTruthy();
  });

  it("has exactly one status element on the Plan page", () => {
    mount();
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByText(FIT_INITIAL).getAttribute("role")).toBeNull();
  });

  it("reports an empty plan in the status and the shopping list", () => {
    mount();
    click("Remove Bean tacos");
    expect(statusText()).toBe(
      "0 meals, 0 servings. Groceries to buy $0.00. $40.00 left under the $40.00 plan cap. Whole packages · Sample estimate.",
    );
    expect(textOf(shoppingSection())).toContain("Nothing to buy. Every ingredient is marked at home.");
  });

  it("lists the at-home ingredient names", () => {
    mount();
    const names = within(shoppingSection()).getByText("ground cumin, olive oil, salt");
    expect(textOf(names)).not.toContain("salsa");
  });

  it("shows the Plan total heading in the summary", () => {
    mount();
    expect(
      within(screen.getByRole("region", { name: "Plan summary" })).getByRole("heading", {
        name: "Plan total",
      }),
    ).toBeTruthy();
  });

  it("starts olive oil, salt, and ground cumin checked on the tacos card", () => {
    mount();
    const tacos = within(card("Bean tacos"));
    for (const name of ["olive oil", "salt", "ground cumin"]) {
      expect((tacos.getByLabelText(new RegExp(`^${name}`)) as HTMLInputElement).checked).toBe(true);
    }
    expect((tacos.getByLabelText(/^salsa/) as HTMLInputElement).checked).toBe(false);
    expect(textOf(tacos.getByText(/^black beans/).closest("label") as HTMLElement)).toContain("240 g");
    expect(textOf(tacos.getByText(/^corn tortillas/).closest("label") as HTMLElement)).toContain("× 4");
  });

  it("moves onion off the shopping list when checked on a card", () => {
    mount();
    click("Egg fried rice");
    expect(mainText()).toContain("$18.41");
    act(() => {
      fireEvent.click(within(card("Bean tacos")).getByText(/^Ingredients/));
    });
    const onion = within(card("Bean tacos")).getByLabelText(/^onion/) as HTMLInputElement;
    expect(onion.checked).toBe(false);
    act(() => {
      fireEvent.click(onion);
    });
    expect(onion.checked).toBe(true);
    expect(within(shoppingSection()).queryByLabelText(/onion/)).toBeNull();
    expect((within(card("Egg fried rice")).getByLabelText(/^onion/) as HTMLInputElement).checked).toBe(
      true,
    );
    expect(summaryText()).toContain("$17.12");
  });

  it("adds olive oil to the shopping list when unchecked on a card", () => {
    mount();
    const oil = within(card("Bean tacos")).getByLabelText(/^olive oil/) as HTMLInputElement;
    expect(within(shoppingSection()).queryByLabelText(/olive oil/)).toBeNull();
    act(() => {
      fireEvent.click(oil);
    });
    expect(oil.checked).toBe(false);
    expect(within(shoppingSection()).getByLabelText(/olive oil/)).toBeTruthy();
    expect(summaryText()).toContain("$14.05");
    expect(mainText()).toContain("$14.05");
  });

  it("keeps focus on the card checkbox after a toggle", () => {
    mount();
    const oil = within(card("Bean tacos")).getByLabelText(/^olive oil/) as HTMLInputElement;
    act(() => {
      oil.focus();
      fireEvent.click(oil);
    });
    expect(document.activeElement).toBe(oil);
  });

  it("reads $0.00 left when the cost equals the cap", () => {
    mount();
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: "8.06" } });
    });
    expect(summaryText()).toContain("$0.00 left under the $8.06 plan cap.");
    expect(screen.getByText("$0.00 left under the $8.06 plan cap.")).toBeTruthy();
  });

  it("keeps an invalid plan cap linked after visiting Pantry", () => {
    mount();
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: "12.345" } });
    });
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("budget-error");
    expect(textOf(screen.getByRole("alert"))).toBe(AMOUNT_ERROR);
    click("Pantry");
    click("Plan");
    const returned = screen.getByLabelText("Plan cap") as HTMLInputElement;
    expect(returned.value).toBe("12.345");
    expect(returned.getAttribute("aria-invalid")).toBe("true");
    expect(returned.getAttribute("aria-describedby")).toBe("budget-error");
    expect(textOf(screen.getByRole("alert"))).toBe(AMOUNT_ERROR);
    expect(returned.getAttribute("aria-describedby")).toBe(screen.getByRole("alert").id);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your plan" }));
  });
});
