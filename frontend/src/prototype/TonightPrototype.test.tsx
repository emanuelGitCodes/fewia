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
    click("See shopping list");
    expect(mainText()).toContain("Nothing to buy. Every ingredient is marked at home.");
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
    click("Budget");
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    expect(
      within(screen.getByRole("navigation", { name: "Prototype sections" })).getByRole("button", {
        name: "Budget",
      }).getAttribute("aria-current"),
    ).toBe("page");
    act(() => {
      fireEvent.change(input, { target: { value: "12.345" } });
    });
    expect(mainText()).toContain(AMOUNT_ERROR);
    expect(mainText()).toContain("This plan fits the $40.00 plan cap.");
    act(() => {
      fireEvent.change(input, { target: { value: "0" } });
    });
    expect(mainText()).toContain("This plan is over the $0.00 plan cap.");
    act(() => {
      fireEvent.change(input, { target: { value: "5" } });
    });
    expect(mainText()).toContain("This plan is over the $5.00 plan cap.");
    expect(mainText()).toContain(SAMPLE_ESTIMATE_NOTICE);
  });

  it("checks shopping items without changing cost and clears stale checks", () => {
    mount();
    click("See shopping list");
    expect(mainText()).toContain("Total $8.06");
    const salsa = screen.getByLabelText(/salsa/) as HTMLInputElement;
    const onion = screen.getByLabelText(/onion/) as HTMLInputElement;
    act(() => {
      fireEvent.click(salsa);
      fireEvent.click(onion);
    });
    expect(salsa.checked).toBe(true);
    expect(onion.checked).toBe(true);
    expect(mainText()).toContain("Total $8.06");
    click("Back to plan");
    click("Egg fried rice");
    click("See shopping list");
    expect((screen.getByLabelText(/salsa/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/onion/) as HTMLInputElement).checked).toBe(true);
    click("Back to plan");
    // Tacos at 8 servings plus rice at 8 servings need 480 g of onion, two packages.
    clickTimes("Increase servings for Bean tacos", 6);
    clickTimes("Increase servings for Egg fried rice", 6);
    click("See shopping list");
    expect((screen.getByLabelText(/salsa/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/onion/) as HTMLInputElement).checked).toBe(false);
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
    click("Budget");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Budget" }));
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
    click("Plan");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your plan" }));
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
    canvas.scrollTop = 48;
    click("See shopping list");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Shopping list" }));
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
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
    expect(nav.getByRole("button", { name: "Budget" }).hasAttribute("aria-current")).toBe(false);
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
      "1 meal, 2 servings. Groceries to buy $8.06. Whole packages · Sample estimate.",
    );
    click("Egg fried rice");
    expect(statusText()).toBe(
      "2 meals, 4 servings. Groceries to buy $18.41. Whole packages · Sample estimate.",
    );
    click("Egg fried rice");
    expect(statusText()).toBe(
      "1 meal, 2 servings. Groceries to buy $8.06. Whole packages · Sample estimate.",
    );
    click("Increase servings for Bean tacos");
    expect(statusText()).toBe(
      "1 meal, 3 servings. Groceries to buy $8.06. Whole packages · Sample estimate.",
    );
    click("Increase servings for Bean tacos");
    expect(statusText()).toBe(
      "1 meal, 4 servings. Groceries to buy $9.35. Whole packages · Sample estimate.",
    );
  });

  it("keeps the estimate status still when a serving bound is rejected", () => {
    mount();
    click("Decrease servings for Bean tacos");
    const boundText =
      "1 meal, 1 serving. Groceries to buy $8.06. Whole packages · Sample estimate.";
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

  it("keeps an invalid plan cap linked after leaving Budget", () => {
    mount();
    click("Budget");
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    act(() => {
      fireEvent.change(input, { target: { value: "12.345" } });
    });
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("budget-error");
    expect(textOf(screen.getByRole("alert"))).toBe(AMOUNT_ERROR);
    click("Plan");
    click("Budget");
    const returned = screen.getByLabelText("Plan cap") as HTMLInputElement;
    expect(returned.value).toBe("12.345");
    expect(returned.getAttribute("aria-invalid")).toBe("true");
    expect(returned.getAttribute("aria-describedby")).toBe("budget-error");
    expect(textOf(screen.getByRole("alert"))).toBe(AMOUNT_ERROR);
    expect(returned.getAttribute("aria-describedby")).toBe(screen.getByRole("alert").id);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Budget" }));
  });
});
