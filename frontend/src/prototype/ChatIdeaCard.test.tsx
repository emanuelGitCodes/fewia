/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatDollars } from "../money";
import { ChatIdeaCard } from "./ChatIdeaCard";
import { addMeal, initialPlanState, previewAdd, type PlanState } from "./planModel";

afterEach(cleanup);

function renderCard(state: PlanState, recipeId = "chickpea_curry", servings = 2) {
  const onToggle = vi.fn();
  const view = render(
    <ChatIdeaCard recipeId={recipeId} servings={servings} state={state} onToggle={onToggle} />,
  );
  return { ...view, onToggle };
}

describe("ChatIdeaCard", () => {
  it("renders nothing for an unknown recipe", () => {
    const { container } = renderCard(initialPlanState(), "nope");
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an inherited object key", () => {
    const { container } = renderCard(initialPlanState(), "constructor");
    expect(container.firstChild).toBeNull();
  });

  it("still offers Remove when the plan is full and holds the meal", () => {
    let state = initialPlanState();
    state = addMeal(state, "egg_fried_rice");
    state = addMeal(state, "lentil_soup");
    const { onToggle } = renderCard(state, "lentil_soup");
    const button = screen.getByRole("button", { name: "Remove Lentil soup from plan" });
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(screen.queryByText("Remove a meal to add this one.")).toBeNull();
    act(() => {
      fireEvent.click(button);
    });
    expect(onToggle).toHaveBeenCalledWith("lentil_soup", 2, true);
  });

  it("shows and passes on the plan's servings for a planned meal, not the prop", () => {
    const state = addMeal(initialPlanState(), "chickpea_curry", 4);
    const { onToggle } = renderCard(state, "chickpea_curry", 2);
    expect(screen.getByText(/^4 servings · /)).toBeTruthy();
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Remove Chickpea curry from plan" }));
    });
    expect(onToggle).toHaveBeenCalledWith("chickpea_curry", 4, true);
  });

  it("clamps the servings for a meal that is not planned", () => {
    const { onToggle } = renderCard(initialPlanState(), "chickpea_curry", 20);
    expect(screen.getByText(/^8 servings · /)).toBeTruthy();
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /^Add Chickpea curry, 8 servings/ }));
    });
    expect(onToggle).toHaveBeenCalledWith("chickpea_curry", 8, false);
  });

  it("gives two cards for the same meal distinct ids", () => {
    const state = initialPlanState();
    const { container } = render(
      <>
        <ChatIdeaCard recipeId="chickpea_curry" servings={2} state={state} onToggle={vi.fn()} />
        <ChatIdeaCard recipeId="chickpea_curry" servings={2} state={state} onToggle={vi.fn()} />
      </>,
    );
    const ids = [...container.querySelectorAll("h3")].map((heading) => heading.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });

  it("shows the facts, the price change, and the fit line for a new meal", () => {
    const state = initialPlanState();
    const delta = formatDollars(previewAdd(state, "chickpea_curry", 2).deltaCents);
    renderCard(state);
    expect(screen.getByRole("heading", { name: "Chickpea curry" })).toBeTruthy();
    expect(screen.getByText(/^2 servings · .+ g protein each$/)).toBeTruthy();
    expect(screen.getByText(`+${delta}`)).toBeTruthy();
    expect(screen.getByText(/left under the \$40\.00 plan cap\./)).toBeTruthy();
    const button = screen.getByRole("button", {
      name: `Add Chickpea curry, 2 servings, plus ${delta}, to plan`,
    });
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(button.textContent).toBe("Add to plan");
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("names shared ingredients when the plan already buys them", () => {
    renderCard(addMeal(initialPlanState(), "egg_fried_rice"));
    expect(screen.getByText(/^Shares .+ with your plan\.$/)).toBeTruthy();
  });

  it("calls onToggle with the recipe, servings, and current state", () => {
    const { onToggle } = renderCard(initialPlanState(), "chickpea_curry", 3);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /^Add Chickpea curry, 3 servings/ }));
    });
    expect(onToggle).toHaveBeenCalledWith("chickpea_curry", 3, false);
  });

  it("shows the selected style and a remove name when the meal is in the plan", () => {
    const state = addMeal(initialPlanState(), "chickpea_curry");
    const { onToggle, container } = renderCard(state);
    const button = screen.getByRole("button", { name: "Remove Chickpea curry from plan" });
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(button.textContent).toBe("In your plan");
    expect(container.querySelector(".tonight-idea-card.is-selected")).not.toBeNull();
    act(() => {
      fireEvent.click(button);
    });
    expect(onToggle).toHaveBeenCalledWith("chickpea_curry", 2, true);
  });

  it("uses the error style over the cap and keeps the button enabled", () => {
    const state = { ...initialPlanState(), budgetCents: 1000 };
    const { container } = renderCard(state);
    const over = container.querySelector(".tonight-idea-over");
    expect(over?.textContent).toMatch(/over the \$10\.00 plan cap\./);
    const button = screen.getByRole("button", { name: /^Add Chickpea curry/ });
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("does not use the error style under the cap", () => {
    const { container } = renderCard(initialPlanState());
    expect(container.querySelector(".tonight-idea-over")).toBeNull();
  });

  it("disables the button and explains when the plan is full", () => {
    let state = initialPlanState();
    state = addMeal(state, "egg_fried_rice");
    state = addMeal(state, "lentil_soup");
    const { onToggle, container } = renderCard(state);
    const button = screen.getByRole("button", { name: "Plan has 3 meals" });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Remove a meal to add this one.")).toBeTruthy();
    expect(container.querySelector(".tonight-idea-delta")).toBeNull();
    expect(screen.queryByText(/^[+−]\$/)).toBeNull();
    expect(screen.queryByText(/plan cap/)).toBeNull();
    act(() => {
      fireEvent.click(button);
    });
    expect(onToggle).not.toHaveBeenCalled();
  });
});
