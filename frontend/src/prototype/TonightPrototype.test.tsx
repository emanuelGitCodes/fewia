/** @vitest-environment jsdom */

import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import { INITIAL_PANTRY, PANTRY_IDS, SERVING_ERROR } from "./prototypeData";
import { TonightPrototype } from "./TonightPrototype";

function textOf(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

function mount(): HTMLElement {
  return render(createElement(TonightPrototype)).container;
}

function pantryBox(id: string): HTMLInputElement {
  const box = document.getElementById(`pantry-${id}`);
  if (!(box instanceof HTMLInputElement)) {
    throw new Error(`Missing pantry control: ${id}`);
  }
  return box;
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
    expect(text).toContain("What sounds good?");
    expect(text).toContain("$8.06");
    expect(text).toContain("Whole packages");
    expect(text).toContain(SAMPLE_ESTIMATE_NOTICE);
    expect(text).toContain("Demo estimates");
    expect(text).toContain("379");
    expect(text).toContain("14.5 g");
    expect(text).toContain("55.8 g");
    expect(text).toContain("13.7 g");
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("img", { name: "Bean tacos" })).toBeTruthy();
    expect(textOf(buttonNamed("3 at home, Edit pantry"))).toMatch(/3 at home/);
    expect(screen.getByRole("link", { name: "Existing app" }).getAttribute("href")).toBe("/");
  });

  it("adds $5.99 when olive oil leaves the pantry", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("3 at home, Edit pantry"));
    });
    act(() => {
      fireEvent.click(screen.getByLabelText("olive oil"));
    });
    act(() => {
      fireEvent.click(buttonNamed("Back to tonight"));
    });
    expect(textOf(screen.getByRole("main"))).toContain("$14.05");
  });

  it("crosses the taco bean package at four servings", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("Increase servings"));
    });
    expect(textOf(screen.getByRole("main"))).toContain("$8.06");
    act(() => {
      fireEvent.click(buttonNamed("Increase servings"));
    });
    expect(textOf(screen.getByRole("main"))).toContain("4 servings");
    expect(textOf(screen.getByRole("main"))).toContain("$9.35");
  });

  it("keeps nutrition when every ingredient is at home", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("Pantry"));
    });
    act(() => {
      checkRemainingPantry();
    });
    act(() => {
      fireEvent.click(buttonNamed("Tonight"));
    });
    const main = textOf(screen.getByRole("main"));
    expect(main).toContain("$0.00");
    expect(main).toContain("379");
    expect(main).toContain("14.5 g");
    act(() => {
      fireEvent.click(buttonNamed("See shopping list"));
    });
    expect(textOf(screen.getByRole("main"))).toContain(
      "Nothing to buy. Every ingredient is marked at home.",
    );
  });

  it("shows a serving bound message at 1 and 8", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("Decrease servings"));
    });
    expect(textOf(screen.getByRole("main"))).toContain("1 serving");
    act(() => {
      fireEvent.click(buttonNamed("Decrease servings"));
    });
    expect(textOf(screen.getByRole("main"))).toContain(SERVING_ERROR);
    expect(textOf(screen.getByRole("main"))).toContain("1 serving");
    for (let step = 0; step < 8; step += 1) {
      act(() => {
        fireEvent.click(buttonNamed("Increase servings"));
      });
    }
    expect(textOf(screen.getByRole("main"))).toContain("8 servings");
    expect(textOf(screen.getByRole("main"))).toContain(SERVING_ERROR);
  });

  it("switches meal photo, cost, and nutrition together", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("Egg fried rice"));
    });
    const rice = textOf(screen.getByRole("main"));
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("img", { name: "Egg fried rice" })).toBeTruthy();
    expect(rice).toContain("$11.64");
    expect(rice).toContain("520");
    expect(rice).toContain("21 g");
    expect(rice).toContain("63 g");
    expect(rice).toContain("20 g");
    act(() => {
      fireEvent.click(buttonNamed("Chickpea curry"));
    });
    const curry = textOf(screen.getByRole("main"));
    expect(screen.getByRole("img", { name: "Chickpea curry" })).toBeTruthy();
    expect(curry).toContain("$10.44");
    expect(curry).toContain("610");
    expect(curry).toContain("18 g");
    expect(curry).toContain("78 g");
    expect(curry).toContain("25 g");
  });

  it("edits the plan cap without replacing the last valid budget", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("Budget"));
    });
    const input = screen.getByLabelText("Plan cap") as HTMLInputElement;
    expect(screen.getByRole("navigation", { name: "Prototype sections" })
      .querySelector('[aria-current="page"]')?.textContent).toContain("Budget");
    act(() => {
      fireEvent.change(input, { target: { value: "12.345" } });
    });
    const invalid = textOf(screen.getByRole("main"));
    expect(invalid).toContain("Enter a non-negative dollar amount with at most two decimal places.");
    expect(invalid).toContain("This meal fits the $40.00 plan cap.");
    act(() => {
      fireEvent.change(input, { target: { value: "0" } });
    });
    expect(textOf(screen.getByRole("main"))).toContain("This meal is over the $0.00 plan cap.");
    act(() => {
      fireEvent.change(input, { target: { value: "5" } });
    });
    expect(textOf(screen.getByRole("main"))).toContain("This meal is over the $5.00 plan cap.");
    expect(textOf(screen.getByRole("main"))).toContain(SAMPLE_ESTIMATE_NOTICE);
  });

  it("checks shopping items without changing cost and clears stale checks", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("See shopping list"));
    });
    const list = screen.getByRole("main");
    expect(textOf(list)).toContain("Total $8.06");
    const beans = screen.getByLabelText(/black beans/);
    act(() => {
      fireEvent.click(beans);
    });
    expect((beans as HTMLInputElement).checked).toBe(true);
    expect(textOf(screen.getByRole("main"))).toContain("Total $8.06");
    act(() => {
      fireEvent.click(buttonNamed("Back to tonight"));
    });
    act(() => {
      fireEvent.click(buttonNamed("Increase servings"));
    });
    act(() => {
      fireEvent.click(buttonNamed("See shopping list"));
    });
    expect((screen.getByLabelText(/black beans/) as HTMLInputElement).checked).toBe(false);
    expect(
      within(screen.getByRole("navigation", { name: "Prototype sections" })).getByRole("button", {
        name: "Tonight",
      }).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("moves focus with the view and keeps budget typing", () => {
    const root = mount();
    const canvas = root.querySelector(".tonight-canvas");
    if (!(canvas instanceof HTMLElement)) {
      throw new Error("Missing tonight canvas");
    }
    const tonightHeading = screen.getByRole("heading", { name: "What sounds good?" });
    expect(document.activeElement).not.toBe(tonightHeading);
    canvas.scrollTop = 48;
    act(() => {
      fireEvent.click(buttonNamed("Pantry"));
    });
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Pantry" }));
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
    const oil = screen.getByLabelText("olive oil");
    act(() => {
      oil.focus();
      fireEvent.click(oil);
    });
    expect(document.activeElement).toBe(oil);
    act(() => {
      fireEvent.click(buttonNamed("Budget"));
    });
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
    act(() => {
      fireEvent.click(buttonNamed("Tonight"));
    });
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "What sounds good?" }),
    );
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
    canvas.scrollTop = 48;
    act(() => {
      fireEvent.click(buttonNamed("See shopping list"));
    });
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Shopping list" }),
    );
    expect(canvas.scrollTop).toBe(0);
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 0);
  });

  it("includes pantry status and edit action in the control name", () => {
    mount();
    const withItems = buttonNamed("3 at home, Edit pantry");
    expect(textOf(withItems)).toContain("3 at home");
    expect(withItems.getAttribute("aria-label")).toBe("3 at home, Edit pantry");
    act(() => {
      fireEvent.click(withItems);
    });
    act(() => {
      clearMealPantry();
    });
    act(() => {
      fireEvent.click(buttonNamed("Back to tonight"));
    });
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
    expect(nav.getByRole("button", { name: "Tonight" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Pantry" }).hasAttribute("aria-current")).toBe(false);
    expect(nav.getByRole("button", { name: "Budget" }).hasAttribute("aria-current")).toBe(false);
    act(() => {
      fireEvent.click(buttonNamed("Chickpea curry"));
    });
    expect(buttonNamed("Chickpea curry").getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed("Bean tacos").getAttribute("aria-pressed")).toBe("false");
    expect(buttonNamed("Egg fried rice").getAttribute("aria-pressed")).toBe("false");
    act(() => {
      fireEvent.click(buttonNamed("Pantry"));
    });
    expect(nav.getByRole("button", { name: "Pantry" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Tonight" }).hasAttribute("aria-current")).toBe(false);
  });
});
