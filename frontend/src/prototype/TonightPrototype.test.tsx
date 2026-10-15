/** @vitest-environment jsdom */

import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import { PANTRY_IDS, SERVING_ERROR } from "./prototypeData";
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

function checkRemainingPantry(): void {
  for (const id of PANTRY_IDS) {
    const box = document.getElementById(`pantry-${id}`);
    if (!(box instanceof HTMLInputElement)) {
      throw new Error(`Missing pantry control: ${id}`);
    }
    if (!box.checked) {
      fireEvent.click(box);
    }
  }
}

afterEach(cleanup);

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
    expect(screen.getByRole("link", { name: "Existing app" }).getAttribute("href")).toBe("/");
  });

  it("adds $5.99 when olive oil leaves the pantry", () => {
    mount();
    act(() => {
      fireEvent.click(buttonNamed("Edit pantry"));
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
});
