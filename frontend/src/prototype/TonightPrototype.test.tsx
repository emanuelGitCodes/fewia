/** @vitest-environment jsdom */

import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import {
  INGREDIENTS,
  INITIAL_PANTRY,
  PANTRY_IDS,
  RECIPES,
  RECIPE_ORDER,
  SERVING_ERROR,
  requireIngredient,
} from "./prototypeData";
import type { ChatJob, ChatJobCreate, ChatResult } from "../chatTypes";
import { useChatJob } from "../useChatJob";
import { useProviderCapabilities } from "../useProviderCapabilities";
import { TonightPrototype } from "./TonightPrototype";

vi.mock("../useChatJob", () => ({ useChatJob: vi.fn() }));
vi.mock("../useProviderCapabilities", () => ({ useProviderCapabilities: vi.fn() }));

const jobState: {
  job: ChatJob | null;
  submit: ReturnType<typeof vi.fn<(body: ChatJobCreate) => Promise<void>>>;
} = { job: null, submit: vi.fn(async (_body: ChatJobCreate) => undefined) };

function setChatConfigured(configured: boolean): void {
  vi.mocked(useProviderCapabilities).mockReturnValue({
    capabilities: {
      chat_configured: configured,
      plaid_configured: false,
      instacart_configured: false,
      spending_source: "manual",
    },
    pending: false,
    error: null,
    retry: vi.fn(),
  });
}

function plannedChatJob(): ChatJob {
  const result = {
    status: "planned",
    answer: "Chickpea curry fits your plan.",
    plan: null,
    budget: null,
    request: {
      meals: [{ recipe_id: "chickpea_curry", servings: 2 }],
      budget_period: "2026-09-01",
      plan_cap_cents: null,
      pantry_ingredients: [],
      ingredient_exclusions: [],
      diet: "omnivore",
    },
    meal_nutrition: null,
    evidence_id: null,
    evidence_revision_id: null,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 1,
    planner_revisions: 0,
    usage: null,
  } as ChatResult;
  return { id: "job-1", status: "succeeded", result, error_code: null };
}

const AMOUNT_ERROR = "Enter a non-negative dollar amount with at most two decimal places.";
const FIT_INITIAL = "$31.94 left under the $40.00 plan cap.";
const TACO_MACROS = "379 kcal · 14.5 g protein · 55.8 g carbs · 12.3 g fat per serving";
const RICE_MACROS = "590 kcal · 22.4 g protein · 76.7 g carbs · 20.6 g fat per serving";

function textOf(node: HTMLElement): string {
  return node.textContent ?? "";
}

// A picker tile's accessible name is the recipe name plus its diet labels, so
// a bare recipe name matches the start of the name.
function pickerName(name: string): string | RegExp {
  const isRecipe = RECIPE_ORDER.some((id) => RECIPES[id].name === name);
  return isRecipe ? new RegExp(`^${name}`) : name;
}

function buttonNamed(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name: pickerName(name) }) as HTMLButtonElement;
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

// The Ask FEWIA aside has its own status region, so plan statuses are read inside main.
function planStatuses(): HTMLElement[] {
  return within(screen.getByRole("main")).getAllByRole("status");
}

function statusText(): string {
  const statuses = planStatuses();
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

const originalLocalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => {
      data.clear();
    },
    getItem: (key: string) => data.get(key) ?? null,
    key: (index: number) => [...data.keys()][index] ?? null,
    removeItem: (key: string) => {
      data.delete(key);
    },
    setItem: (key: string, value: string) => {
      data.set(key, String(value));
    },
  };
}

beforeEach(() => {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    writable: true,
    value: memoryStorage(),
  });
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  jobState.job = null;
  jobState.submit = vi.fn(async (_body: ChatJobCreate) => undefined);
  vi.mocked(useChatJob).mockImplementation(() => ({
    job: jobState.job,
    error: null,
    pending: false,
    submit: jobState.submit,
    clear: () => {
      jobState.job = null;
    },
  }));
  setChatConfigured(true);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  if (originalLocalStorage === undefined) {
    Reflect.deleteProperty(window, "localStorage");
  } else {
    Object.defineProperty(window, "localStorage", originalLocalStorage);
  }
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

  it("adds all three meals at 2 servings for $22.19", () => {
    mount();
    click("Egg fried rice");
    click("Chickpea curry");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    // Curry powder is a pantry item in the backend catalog, so it costs nothing.
    expect(mainText()).toContain("$22.19");
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
    expect(planStatuses()).toHaveLength(1);
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

  it("has exactly one plan status element and one chat status element", () => {
    mount();
    expect(planStatuses()).toHaveLength(1);
    expect(screen.getAllByRole("status")).toHaveLength(2);
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

  it("pins a hidden total bar that follows the plan", () => {
    mount();
    const bar = screen.getByText(`$8.06 · ${FIT_INITIAL}`);
    expect(bar.getAttribute("aria-hidden")).toBe("true");
    click("Egg fried rice");
    const updated = screen.getByText("$18.41 · $21.59 left under the $40.00 plan cap.");
    expect(updated.getAttribute("aria-hidden")).toBe("true");
    expect(updated.getAttribute("role")).toBeNull();
    expect(planStatuses()).toHaveLength(1);
  });

  describe("pinned bar height", () => {
    const PROPERTY = "--tonight-pinned-height";
    const original = Object.getOwnPropertyDescriptor(globalThis, "ResizeObserver");

    function restoreObserver(): void {
      if (original === undefined) {
        Reflect.deleteProperty(globalThis, "ResizeObserver");
      } else {
        Object.defineProperty(globalThis, "ResizeObserver", original);
      }
    }

    function canvasOf(root: HTMLElement): HTMLElement {
      const canvas = root.querySelector(".tonight-canvas");
      if (!(canvas instanceof HTMLElement)) {
        throw new Error("Missing tonight canvas");
      }
      return canvas;
    }

    afterEach(restoreObserver);

    it("sets the property, observes the pinned bar, and cleans up on unmount", () => {
      interface Instance {
        callback: ResizeObserverCallback;
        observed: Element[];
        disconnects: number;
      }
      const instances: Instance[] = [];
      class StubObserver {
        private readonly instance: Instance;
        constructor(callback: ResizeObserverCallback) {
          this.instance = { callback, observed: [], disconnects: 0 };
          instances.push(this.instance);
        }
        observe(target: Element): void {
          this.instance.observed.push(target);
        }
        unobserve(): void {}
        disconnect(): void {
          this.instance.disconnects += 1;
        }
      }
      Object.defineProperty(globalThis, "ResizeObserver", {
        value: StubObserver,
        configurable: true,
        writable: true,
      });
      const view = render(createElement(TonightPrototype));
      const canvas = canvasOf(view.container);
      const pinned = view.container.querySelector(".tonight-pinned");
      expect(pinned).not.toBeNull();
      expect(canvas.style.getPropertyValue(PROPERTY)).toBe("0px");
      const pinnedInstances = instances.filter((i) => i.observed.includes(pinned as Element));
      expect(pinnedInstances).toHaveLength(1);
      const instance = pinnedInstances[0];
      expect(instance.observed).toEqual([pinned]);
      Object.defineProperty(pinned, "offsetHeight", { value: 56, configurable: true });
      act(() => {
        instance.callback([], {} as ResizeObserver);
      });
      expect(canvas.style.getPropertyValue(PROPERTY)).toBe("56px");
      view.unmount();
      expect(instance.disconnects).toBe(1);
      expect(canvas.style.getPropertyValue(PROPERTY)).toBe("");
    });

    it("renders and sets the property once without ResizeObserver", () => {
      Reflect.deleteProperty(globalThis, "ResizeObserver");
      const view = render(createElement(TonightPrototype));
      expect(screen.getByRole("heading", { name: "Your plan" })).toBeTruthy();
      expect(canvasOf(view.container).style.getPropertyValue(PROPERTY)).toBe("0px");
    });
  });

  describe("Find a meal filter", () => {
    function filterInput(): HTMLInputElement {
      return screen.getByLabelText("Find a meal") as HTMLInputElement;
    }

    function typeFilter(value: string): void {
      act(() => {
        fireEvent.change(filterInput(), { target: { value } });
      });
    }

    function tileNames(): string[] {
      const group = screen.queryByRole("group", { name: "Meal choices" });
      if (group === null) {
        return [];
      }
      return within(group)
        .getAllByRole("button")
        .map((button) => button.querySelector(".tonight-meal > span")?.textContent ?? "");
    }

    const riceMeals = RECIPE_ORDER.filter(
      (id) =>
        RECIPES[id].name.toLowerCase().includes("rice") ||
        RECIPES[id].ingredients.some(([ingredientId]) =>
          INGREDIENTS[ingredientId].name.toLowerCase().includes("rice"),
        ),
    ).map((id) => RECIPES[id].name);

    it("starts with forty tiles", () => {
      mount();
      expect(tileNames()).toEqual(RECIPE_ORDER.map((id) => RECIPES[id].name));
      expect(within(screen.getByRole("group", { name: "Meal choices" })).getAllByRole("button")).toHaveLength(40);
    });

    it("narrows to the rice meals for rice, in any case", () => {
      mount();
      typeFilter("rice");
      expect(riceMeals).toContain("Egg fried rice");
      expect(riceMeals.length).toBeLessThan(40);
      expect(tileNames()).toEqual(riceMeals);
      typeFilter("RICE");
      expect(tileNames()).toEqual(riceMeals);
    });

    it("matches diet labels", () => {
      mount();
      typeFilter("vegan");
      const vegan = RECIPE_ORDER.filter((id) => RECIPES[id].diets.includes("vegan")).map(
        (id) => RECIPES[id].name,
      );
      expect(vegan).toContain("Bean tacos");
      expect(vegan).not.toContain("Egg fried rice");
      expect(tileNames()).toEqual(vegan);
    });

    it("shows a keto note, links it to the filter and removes it for other queries", () => {
      mount();
      expect(document.getElementById("meal-filter-note")).toBeNull();
      expect(filterInput().getAttribute("aria-describedby")).toBeNull();
      typeFilter("keto");
      const note = document.getElementById("meal-filter-note");
      expect(note?.textContent).toBe(
        "No meal in this catalog is keto. These meals have 30 g of carbs or less per serving.",
      );
      expect(filterInput().getAttribute("aria-describedby")).toBe("meal-filter-note");
      expect(tileNames()).toHaveLength(8);
      typeFilter("rice");
      expect(document.getElementById("meal-filter-note")).toBeNull();
      expect(filterInput().getAttribute("aria-describedby")).toBeNull();
    });

    it("lists the chicken meals for meat and shows a label on a chicken meal", () => {
      mount();
      typeFilter("meat");
      expect(tileNames()).toHaveLength(12);
      expect(document.getElementById("meal-filter-note")?.textContent).toBe(
        "No meal is strictly carnivore. These meals include chicken.",
      );
      expect(textOf(buttonNamed("Chicken curry"))).toContain(
        "Chicken · High protein · Gluten-free ingredients",
      );
    });

    it("shows the diets on a plan card and the meal photo on its tile", () => {
      mount();
      click("Vegetable stir fry");
      expect(textOf(card("Vegetable stir fry"))).toContain("Vegan");
      expect(textOf(card("Vegetable stir fry"))).toContain("Vegetarian");
      expect(
        buttonNamed("Vegetable stir fry").querySelector("img")?.getAttribute("src"),
      ).toBe("/prototype/vegetable-stir-fry.webp");
    });

    it("shows a message and no tiles when nothing matches", () => {
      mount();
      typeFilter("zzz");
      expect(screen.getByText("No meals match.")).toBeTruthy();
      expect(tileNames()).toEqual([]);
    });

    it("restores all forty tiles when cleared", () => {
      mount();
      typeFilter("zzz");
      typeFilter("");
      expect(screen.queryByText("No meals match.")).toBeNull();
      expect(tileNames()).toHaveLength(40);
    });

    it("announces an empty result in the one status and drops it when cleared", () => {
      mount();
      typeFilter("zzz");
      expect(statusText().startsWith("No meals match. ")).toBe(true);
      expect(statusText()).toBe(
        "No meals match. 1 meal, 2 servings. Groceries to buy $8.06. $31.94 left under the $40.00 plan cap. Whole packages · Sample estimate.",
      );
      typeFilter("");
      expect(statusText()).not.toContain("No meals match.");
    });

    it("keeps one status element while the filter matches nothing", () => {
      mount();
      typeFilter("zzz");
      expect(planStatuses()).toHaveLength(1);
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
    });

    it("keeps the card and total of a planned meal whose tile is hidden", () => {
      mount();
      typeFilter("rice");
      expect(screen.queryByRole("button", { name: /^Bean tacos/ })).toBeNull();
      expect(textOf(card("Bean tacos"))).toContain("2 servings");
      expect(summaryText()).toContain("$8.06");
      expect(statusText()).toContain("Groceries to buy $8.06.");
    });
  });

  it("labels the at-home group in the shopping list before the pantry row", () => {
    mount();
    const section = shoppingSection();
    const label = within(section).getByText("Already at home");
    const row = within(section).getByRole("button", { name: "3 at home, Edit pantry" });
    expect(label.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("places the picker and cards in main and the summary and list in side", () => {
    const root = mount();
    const main = root.querySelector(".tonight-plan-main");
    const side = root.querySelector(".tonight-plan-side");
    if (!(main instanceof HTMLElement) || !(side instanceof HTMLElement)) {
      throw new Error("Missing plan layout wrappers");
    }
    expect(within(main).getByLabelText("Find a meal")).toBeTruthy();
    expect(within(main).getByRole("group", { name: "Meal choices" })).toBeTruthy();
    expect(within(main).getByRole("article", { name: "Bean tacos" })).toBeTruthy();
    expect(within(main).queryByRole("region", { name: "Plan summary" })).toBeNull();
    expect(within(main).queryByRole("region", { name: "Shopping list" })).toBeNull();
    expect(within(side).getByRole("region", { name: "Plan summary" })).toBe(
      screen.getByRole("region", { name: "Plan summary" }),
    );
    expect(within(side).getByRole("region", { name: "Shopping list" })).toBe(shoppingSection());
    expect(within(side).queryByRole("article")).toBeNull();
    expect(within(side).queryByLabelText("Find a meal")).toBeNull();
  });

  it("keeps the estimate notice outside the grid that holds main and side", () => {
    const root = mount();
    const main = root.querySelector(".tonight-plan-main");
    const side = root.querySelector(".tonight-plan-side");
    const grid = root.querySelector(".tonight-plan-grid");
    if (!(main instanceof HTMLElement) || !(side instanceof HTMLElement) || !(grid instanceof HTMLElement)) {
      throw new Error("Missing plan layout wrappers");
    }
    expect(main.parentElement).toBe(grid);
    expect(side.parentElement).toBe(grid);
    const notice = screen.getByText(/^Estimated from the demo price catalog/);
    expect(grid.contains(notice)).toBe(false);
    expect(grid.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  describe("an ingredient without a sample price", () => {
    const beans = requireIngredient("black_beans");
    const original = beans.priceCents;

    beforeEach(() => {
      beans.priceCents = null;
    });

    afterEach(() => {
      beans.priceCents = original;
    });

    it("shows no price, marks the total incomplete, and says the fit is unknown", () => {
      mount();
      const line = within(shoppingSection()).getByLabelText(/black beans/);
      const meta = textOf(line.closest("label") as HTMLElement);
      expect(meta).toContain("No sample price");
      expect(meta).not.toContain("$0.00");
      expect(summaryText()).toContain("(incomplete)");
      expect(mainText()).toContain("Some ingredients have no sample price, so the total is incomplete.");
      const unknown = "Some prices are missing, so the fit under the $40.00 plan cap is unknown.";
      expect(screen.getByText(unknown)).toBeTruthy();
      expect(summaryText()).not.toContain("left under");
      expect(statusText()).toContain(unknown);
      expect(statusText()).toContain("(incomplete)");
    });
  });
});

describe("meal carousel arrows", () => {
  function metrics(scrollWidth: number, clientWidth: number, scrollLeft: number): HTMLElement {
    mount();
    const el = screen.getByRole("group", { name: "Meal choices" });
    Object.defineProperty(el, "scrollWidth", { configurable: true, value: scrollWidth });
    Object.defineProperty(el, "clientWidth", { configurable: true, value: clientWidth });
    Object.defineProperty(el, "scrollLeft", { configurable: true, writable: true, value: scrollLeft });
    act(() => {
      fireEvent.scroll(el);
    });
    return el;
  }

  function prev(): HTMLButtonElement {
    return screen.getByRole("button", { name: "Show previous meals" }) as HTMLButtonElement;
  }

  function next(): HTMLButtonElement {
    return screen.getByRole("button", { name: "Show next meals" }) as HTMLButtonElement;
  }

  it("disables previous and enables next at the start", () => {
    metrics(1000, 400, 0);
    expect(prev().disabled).toBe(true);
    expect(next().disabled).toBe(false);
  });

  it("moves forward and enables previous when next is clicked", () => {
    const el = metrics(1000, 400, 0);
    act(() => {
      fireEvent.click(next());
    });
    expect(el.scrollLeft).toBeGreaterThan(0);
    expect(prev().disabled).toBe(false);
  });

  it("disables next at the right end", () => {
    metrics(1000, 400, 600);
    expect(prev().disabled).toBe(false);
    expect(next().disabled).toBe(true);
  });

  it("disables both when nothing overflows", () => {
    const el = metrics(1000, 400, 0);
    expect(next().disabled).toBe(false);
    Object.defineProperty(el, "scrollWidth", { configurable: true, value: 400 });
    act(() => {
      fireEvent.scroll(el);
    });
    expect(prev().disabled).toBe(true);
    expect(next().disabled).toBe(true);
  });

  describe("resize observer", () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, "ResizeObserver");

    afterEach(() => {
      if (original === undefined) {
        Reflect.deleteProperty(globalThis, "ResizeObserver");
      } else {
        Object.defineProperty(globalThis, "ResizeObserver", original);
      }
    });

    it("re-measures on resize and disconnects on unmount", () => {
      interface Instance {
        callback: ResizeObserverCallback;
        observed: Element[];
        disconnects: number;
      }
      const instances: Instance[] = [];
      class StubObserver {
        private readonly instance: Instance;
        constructor(callback: ResizeObserverCallback) {
          this.instance = { callback, observed: [], disconnects: 0 };
          instances.push(this.instance);
        }
        observe(target: Element): void {
          this.instance.observed.push(target);
        }
        unobserve(): void {}
        disconnect(): void {
          this.instance.disconnects += 1;
        }
      }
      Object.defineProperty(globalThis, "ResizeObserver", {
        value: StubObserver,
        configurable: true,
        writable: true,
      });
      const view = render(createElement(TonightPrototype));
      const el = screen.getByRole("group", { name: "Meal choices" });
      expect(el.classList.contains("tonight-meals")).toBe(true);
      const meals = instances.filter((i) => i.observed.includes(el));
      expect(meals).toHaveLength(1);
      const instance = meals[0];
      expect(next().disabled).toBe(true);
      Object.defineProperty(el, "scrollWidth", { configurable: true, value: 1000 });
      Object.defineProperty(el, "clientWidth", { configurable: true, value: 400 });
      act(() => {
        instance.callback([], {} as ResizeObserver);
      });
      expect(next().disabled).toBe(false);
      view.unmount();
      expect(instance.disconnects).toBe(1);
    });
  });

  describe("reduced motion", () => {
    const originalMatchMedia = Object.getOwnPropertyDescriptor(window, "matchMedia");

    afterEach(() => {
      if (originalMatchMedia === undefined) {
        Reflect.deleteProperty(window, "matchMedia");
      } else {
        Object.defineProperty(window, "matchMedia", originalMatchMedia);
      }
    });

    function stubMatchMedia(reduce: boolean): void {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: (query: string) => ({
          matches: reduce && query === "(prefers-reduced-motion: reduce)",
          media: query,
        }),
      });
    }

    function clickNext(): ReturnType<typeof vi.fn> {
      const el = metrics(1000, 400, 0);
      const scrollBy = vi.fn((options: ScrollToOptions) => {
        el.scrollLeft += options.left ?? 0;
      });
      Object.defineProperty(el, "scrollBy", { configurable: true, value: scrollBy });
      act(() => {
        fireEvent.click(next());
      });
      return scrollBy;
    }

    it("scrolls instantly when reduced motion is preferred", () => {
      stubMatchMedia(true);
      const scrollBy = clickNext();
      expect(scrollBy).toHaveBeenCalledTimes(1);
      expect(scrollBy).toHaveBeenCalledWith({ left: 320, behavior: "auto" });
    });

    it("scrolls smoothly otherwise", () => {
      stubMatchMedia(false);
      const scrollBy = clickNext();
      expect(scrollBy).toHaveBeenCalledTimes(1);
      expect(scrollBy).toHaveBeenCalledWith({ left: 320, behavior: "smooth" });
    });
  });

  it("removes both buttons when no meal matches", () => {
    metrics(1000, 400, 0);
    act(() => {
      fireEvent.change(screen.getByLabelText("Find a meal"), { target: { value: "zzz" } });
    });
    expect(screen.queryByRole("button", { name: "Show previous meals" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Show next meals" })).toBeNull();
  });
});

describe("Ask FEWIA on the prototype", () => {
  async function ask(text: string): Promise<void> {
    const input = screen.getByLabelText("Ask for a meal");
    fireEvent.change(input, { target: { value: text } });
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter" });
    });
  }

  it("places the aside after main and before the footer", () => {
    mount();
    const aside = screen.getByRole("complementary", { name: "Ask FEWIA" });
    const main = screen.getByRole("main");
    const footer = screen.getByRole("contentinfo");
    expect(main.compareDocumentPosition(aside) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(aside.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(main).queryByRole("complementary")).toBeNull();
  });

  it("shows one line and keeps the plan working when chat is off", () => {
    setChatConfigured(false);
    mount();
    expect(screen.getByText("Ask FEWIA is off. The plan still works.")).toBeTruthy();
    click("Egg fried rice");
    expect(summaryText()).toContain("$18.41");
  });

  it("adds a chat idea to the plan, changes the total, and removes it again", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = plannedChatJob();
    });
    mount();
    const before = summaryText();
    expect(before).toContain("$8.06");
    await ask("Something with chickpeas");
    expect(jobState.submit).toHaveBeenCalledTimes(1);
    expect(jobState.submit.mock.calls[0]?.[0].message).toMatch(
      /^My current plan: Bean tacos, 2 servings\. Pantry: .+ Plan cap: \$40\.00\.\n\nSomething with chickpeas$/,
    );
    const add = screen.getByRole("button", { name: /^Add Chickpea curry, 2 servings/ });
    expect(add.getAttribute("aria-pressed")).toBe("false");
    act(() => {
      fireEvent.click(add);
    });
    expect(within(screen.getByRole("main")).getByRole("article", { name: "Chickpea curry" })).toBeTruthy();
    expect(summaryText()).not.toBe(before);
    const remove = screen.getByRole("button", { name: "Remove Chickpea curry from plan" });
    expect(remove.getAttribute("aria-pressed")).toBe("true");
    act(() => {
      fireEvent.click(remove);
    });
    expect(summaryText()).toBe(before);
  });

  it("shows the stored Kroger store in the panel, passes its id to the chat, and removes it", () => {
    window.localStorage.setItem(
      "fewia.krogerStore.v1",
      JSON.stringify({ locationId: "01400943", name: "Main Street" }),
    );
    try {
      mount();
      expect(screen.getByText("Kroger store: Main Street")).toBeTruthy();
      expect(vi.mocked(useChatJob)).toHaveBeenCalledWith("01400943");
      click("Remove");
      expect(screen.getByRole("button", { name: "Choose a Kroger store for live prices" })).toBeTruthy();
      expect(window.localStorage.getItem("fewia.krogerStore.v1")).toBeNull();
    } finally {
      window.localStorage.clear();
    }
  });

  it("shows the chat on the Pantry page and keeps the draft across views", () => {
    mount();
    fireEvent.change(screen.getByLabelText("Ask for a meal"), { target: { value: "Draft" } });
    click("Pantry");
    expect(screen.getByRole("complementary", { name: "Ask FEWIA" })).toBeTruthy();
    expect((screen.getByLabelText("Ask for a meal") as HTMLTextAreaElement).value).toBe("Draft");
    click("Plan");
    expect((screen.getByLabelText("Ask for a meal") as HTMLTextAreaElement).value).toBe("Draft");
  });
});

describe("Ask FEWIA dock and sheet", () => {
  const originalMatchMedia = Object.getOwnPropertyDescriptor(window, "matchMedia");

  afterEach(() => {
    if (originalMatchMedia === undefined) {
      Reflect.deleteProperty(window, "matchMedia");
    } else {
      Object.defineProperty(window, "matchMedia", originalMatchMedia);
    }
  });

  function stubWidth(width: number): void {
    const limits: Record<string, number> = {
      "(max-width: 1179px)": 1179,
      "(max-width: 719px)": 719,
    };
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (query: string) => ({ matches: width <= (limits[query] ?? -1), media: query }),
    });
  }

  function dock(): HTMLElement {
    return screen.getByRole("button", { name: "Ask FEWIA for a meal idea" });
  }

  function aside(): HTMLElement {
    return screen.getByRole("complementary", { name: "Ask FEWIA" });
  }

  function openSheet(): void {
    act(() => {
      fireEvent.click(dock());
    });
  }

  async function askWhile(text: string): Promise<void> {
    const input = screen.getByLabelText("Ask for a meal");
    fireEvent.change(input, { target: { value: text } });
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter" });
    });
  }

  it("opens and closes the sheet from the dock and returns focus to the dock", () => {
    stubWidth(900);
    const root = mount();
    expect(dock().getAttribute("aria-expanded")).toBe("false");
    expect(dock().getAttribute("aria-controls")).toBe(aside().id);
    expect(root.querySelector(".is-ask-open")).toBeNull();
    openSheet();
    expect(dock().getAttribute("aria-expanded")).toBe("true");
    expect(root.querySelector(".is-ask-open")).not.toBeNull();
    expect(document.activeElement).toBe(screen.getByLabelText("Ask for a meal"));
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Hide chat" }));
    });
    expect(dock().getAttribute("aria-expanded")).toBe("false");
    expect(root.querySelector(".is-ask-open")).toBeNull();
    expect(document.activeElement).toBe(dock());
  });

  it("scrolls the pinned total to the top of the canvas when the sheet opens below 720 px", () => {
    stubWidth(375);
    const root = mount();
    const canvas = root.querySelector(".tonight-canvas");
    const pinned = root.querySelector(".tonight-pinned");
    if (!(canvas instanceof HTMLElement) || !(pinned instanceof HTMLElement)) {
      throw new Error("Missing canvas or pinned bar.");
    }
    canvas.scrollTop = 0;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ top: 10 } as DOMRect);
    vi.spyOn(pinned, "getBoundingClientRect").mockReturnValue({ top: 130 } as DOMRect);
    openSheet();
    expect(canvas.scrollTop).toBe(120);
  });

  it("does not scroll the canvas when the sheet opens from 720 px", () => {
    stubWidth(900);
    const root = mount();
    const canvas = root.querySelector(".tonight-canvas");
    const pinned = root.querySelector(".tonight-pinned");
    if (!(canvas instanceof HTMLElement) || !(pinned instanceof HTMLElement)) {
      throw new Error("Missing canvas or pinned bar.");
    }
    vi.spyOn(pinned, "getBoundingClientRect").mockReturnValue({ top: 130 } as DOMRect);
    openSheet();
    expect(canvas.scrollTop).toBe(0);
  });

  it("closes the sheet on Escape and returns focus to the dock", () => {
    stubWidth(375);
    mount();
    openSheet();
    const input = screen.getByLabelText("Ask for a meal");
    expect(document.activeElement).toBe(input);
    act(() => {
      fireEvent.keyDown(input, { key: "Escape" });
    });
    expect(dock().getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(dock());
  });

  it("makes the whole plan inert below 720 px while the sheet is open", () => {
    stubWidth(375);
    const root = mount();
    const header = root.querySelector("header");
    const footer = root.querySelector("footer");
    const main = screen.getByRole("main");
    expect(header?.hasAttribute("inert")).toBe(false);
    openSheet();
    expect(header?.hasAttribute("inert")).toBe(true);
    expect(main.hasAttribute("inert")).toBe(true);
    expect(footer?.hasAttribute("inert")).toBe(true);
    expect(aside().hasAttribute("inert")).toBe(false);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Hide chat" }));
    });
    expect(header?.hasAttribute("inert")).toBe(false);
    expect(main.hasAttribute("inert")).toBe(false);
    expect(footer?.hasAttribute("inert")).toBe(false);
  });

  it("makes only the meals column inert from 720 to 1179 px", () => {
    stubWidth(900);
    const root = mount();
    const meals = root.querySelector(".tonight-plan-main");
    const side = root.querySelector(".tonight-plan-side");
    openSheet();
    expect(meals?.hasAttribute("inert")).toBe(true);
    expect(side?.hasAttribute("inert")).toBe(false);
    expect(screen.getByRole("main").hasAttribute("inert")).toBe(false);
    expect(screen.getByRole("region", { name: "Plan summary" })).toBeTruthy();
    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(meals?.hasAttribute("inert")).toBe(false);
  });

  it("shows 1 new reply when a reply arrives while closed and clears it on open", async () => {
    stubWidth(900);
    jobState.submit.mockImplementation(async () => {
      jobState.job = plannedChatJob();
    });
    mount();
    expect(screen.queryByText("1 new reply")).toBeNull();
    await askWhile("Something with chickpeas");
    expect(screen.getByText("1 new reply")).toBeTruthy();
    openSheet();
    expect(screen.queryByText("1 new reply")).toBeNull();
  });

  it("does not flag a reply that arrives while the sheet is open", async () => {
    stubWidth(900);
    jobState.submit.mockImplementation(async () => {
      jobState.job = plannedChatJob();
    });
    mount();
    openSheet();
    await askWhile("Something with chickpeas");
    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(screen.queryByText("1 new reply")).toBeNull();
  });

  it("shows the panel on the Pantry view and closes the sheet when the nav changes view", () => {
    stubWidth(900);
    mount();
    openSheet();
    click("Pantry");
    expect(dock().getAttribute("aria-expanded")).toBe("false");
    expect(aside()).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Pantry" }));
    openSheet();
    expect(document.activeElement).toBe(screen.getByLabelText("Ask for a meal"));
    expect(screen.getByRole("main").hasAttribute("inert")).toBe(true);
  });

  it("does not reopen the sheet after widening past 1180 px and narrowing back", () => {
    const limits: Record<string, number> = {
      "(max-width: 1179px)": 1179,
      "(max-width: 719px)": 719,
    };
    let width = 900;
    const listeners = new Set<() => void>();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (query: string) => ({
        get matches() {
          return width <= (limits[query] ?? -1);
        },
        media: query,
        addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
        removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
      }),
    });
    const resize = (next: number): void => {
      width = next;
      act(() => {
        listeners.forEach((listener) => {
          listener();
        });
      });
    };
    mount();
    openSheet();
    expect(dock().getAttribute("aria-expanded")).toBe("true");
    resize(1280);
    expect(screen.queryByRole("button", { name: "Ask FEWIA for a meal idea" })).toBeNull();
    resize(900);
    expect(dock().getAttribute("aria-expanded")).toBe("false");
    expect(document.querySelector("[inert]")).toBeNull();
  });

  it("has no dock bar and no inert content from 1180 px", () => {
    stubWidth(1280);
    const root = mount();
    expect(screen.queryByRole("button", { name: "Ask FEWIA for a meal idea" })).toBeNull();
    expect(aside()).toBeTruthy();
    expect(root.querySelector("[inert]")).toBeNull();
    expect(screen.getByRole("region", { name: "Plan summary" })).toBeTruthy();
  });
});
