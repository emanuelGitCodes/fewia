/** @vitest-environment jsdom */

import { createElement } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  HTTP_ERROR,
  SAMPLE_ESTIMATE_NOTICE,
  SPOONACULAR_COST_NOTICE,
  type CatalogItem,
  type GroceryJob,
  type PlanLine,
  type SupermarketEstimate,
} from "./apiTypes";
import { Estimate } from "./Estimate";
import { sampleNutrition } from "../tests/apiFixtures";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;

function renderedText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function line(overrides: Partial<PlanLine> = {}): PlanLine {
  return {
    ingredient_id: "black_beans",
    name: "black beans",
    unit: "g",
    quantity: 425,
    packages: 1,
    cost_cents: 129,
    from_pantry: false,
    ...overrides,
  };
}

function succeeded(overrides: {
  accepted?: boolean;
  total?: number | null;
  lines?: PlanLine[];
  source?: string;
  available?: number;
  pending?: number;
  planWarnings?: string[];
  budgetWarnings?: string[];
  supermarket_estimate?: SupermarketEstimate;
  omitNutrition?: boolean;
} = {}): GroceryJob {
  const lines = overrides.lines ?? [line(), line({ ingredient_id: "tortillas", name: "tortillas", unit: "ct", quantity: 8, packages: 1, cost_cents: 349 })];
  return {
    id: "job-1",
    status: "succeeded",
    error_code: null,
    result: {
      spending_source: overrides.source ?? "fixture",
      ...(overrides.omitNutrition === true ? {} : { meal_nutrition: sampleNutrition() }),
      budget: {
        available_cents: overrides.available ?? 5000,
        pending_cents: overrides.pending ?? 200,
        stale: false,
        warnings: overrides.budgetWarnings ?? ["Budget warning"],
      },
      plan: {
        lines,
        total_cents: overrides.total === undefined ? 478 : overrides.total,
        accepted: overrides.accepted ?? true,
        warnings: overrides.planWarnings ?? ["Plan warning"],
        catalog_version: "sample-prices-v1",
        notice: NOTICE,
      },
      ...(overrides.supermarket_estimate === undefined
        ? {}
        : { supermarket_estimate: overrides.supermarket_estimate }),
    },
  };
}

function mount(
  props: Partial<{
    job: GroceryJob | null;
    pending: boolean;
    dirty: boolean;
    pantry: string[];
    recipes: CatalogItem[];
    ingredients: CatalogItem[];
    onPantryToggle: (id: string) => void;
    onRebuild: () => void | Promise<void>;
    rebuildDisabled: boolean;
  }> = {},
): RenderResult {
  const rendered = render(
    createElement(Estimate, {
      job: props.job ?? null,
      pending: props.pending ?? false,
      dirty: props.dirty ?? false,
      pantry: props.pantry ?? [],
      recipes: props.recipes ?? [],
      ingredients: props.ingredients,
      onPantryToggle: props.onPantryToggle ?? ((): void => {}),
      onRebuild: props.onRebuild,
      rebuildDisabled: props.rebuildDisabled,
    }),
  );
  return rendered;
}

afterEach(cleanup);

describe("Estimate", () => {
  it("renders an empty state when no job is present", () => {
    const rendered = mount();
    expect(renderedText(rendered.container)).toContain("No grocery budget or meal plan is set yet.");
    expect(renderedText(rendered.container)).not.toContain("$");
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    rendered.unmount();
  });

  it("renders pending, queued, running, and failed without a completed result", () => {
    const pending = mount({ pending: true });
    expect(renderedText(pending.container)).toContain("The grocery request is in progress.");
    pending.unmount();
    const queued = mount({ job: { id: "job-1", status: "queued", result: null, error_code: null } });
    expect(renderedText(queued.container)).toContain("The grocery request is queued.");
    expect(renderedText(queued.container)).not.toContain(NOTICE);
    queued.unmount();
    const running = mount({ job: { id: "job-1", status: "running", result: null, error_code: null } });
    expect(renderedText(running.container)).toContain("The grocery request is running.");
    running.unmount();
    const failed = mount({
      job: { id: "job-1", status: "failed", result: succeeded().result, error_code: "tool" },
    });
    expect(renderedText(failed.container)).toContain("The grocery request failed.");
    expect(renderedText(failed.container)).not.toContain("$4.78");
    expect(renderedText(failed.container)).not.toContain(NOTICE);
    failed.unmount();
  });

  it("names the excluded ingredient on exclusion_reject", () => {
    const rendered = mount({
      job: {
        id: "job-1",
        status: "failed",
        result: null,
        error_code: "exclusion_reject",
        error_detail: { recipe_id: "vegetable_pasta", ingredient_id: "onion" },
      },
      recipes: [{ id: "vegetable_pasta", name: "vegetable pasta" }],
      ingredients: [{ id: "onion", name: "onion" }],
    });
    expect(renderedText(rendered.container)).toContain(
      "Vegetable pasta needs onion, which is excluded. Clear the onion exclusion or choose another meal, then rebuild.",
    );
    rendered.unmount();
  });

  it("asks to check and retry when the error is not exclusion_reject", () => {
    const rendered = mount({
      job: { id: "job-1", status: "failed", result: null, error_code: "handler_failed" },
    });
    expect(renderedText(rendered.container)).toContain(HTTP_ERROR);
    rendered.unmount();
  });

  it("shows the server total, notice, every row, and budget labels", () => {
    const rendered = mount({ job: succeeded() });
    const text = renderedText(rendered.container);
    expect(text).toContain("$4.78");
    expect(text).toContain("This estimate is within the plan budget.");
    expect(text).toContain("Available for this plan $50.00");
    expect(text).toContain("Pending $2.00");
    expect(text).toContain("Source Demo spending");
    expect(text).toContain("Needed 425 g");
    expect(text).toContain("Needed 8 ct");
    expect(text).toContain("1 package");
    expect(text).not.toContain("1 packages");
    expect(text).toContain("$1.29");
    expect(text).toContain("$3.49");
    expect(text).toContain("black beans");
    expect(text).toContain("tortillas");
    expect(text).toContain("Plan warning");
    expect(text).toContain("Budget warning");
    expect(text.split("Plan warning")).toHaveLength(2);
    expect(text.split("Budget warning")).toHaveLength(2);
    expect(text).toContain(NOTICE);
    expect((within(rendered.container).queryAllByRole("checkbox") as HTMLInputElement[])).toHaveLength(2);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(text.toLowerCase()).not.toMatch(/checkout/);
    expect(text).not.toContain("Average supermarket estimate");
    expect(text).not.toContain("Spoonacular");
    rendered.unmount();
  });

  it("shows catalog dollars and overlay dollars when present", () => {
    const rendered = mount({
      job: succeeded({
        supermarket_estimate: { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE, lines: [] },
      }),
    });
    const text = renderedText(rendered.container);
    expect(text).toContain("$4.78");
    expect(text).toContain("Average supermarket estimate");
    expect(text).toContain("$12.99");
    expect(text).toContain(SPOONACULAR_COST_NOTICE);
    expect(text).toContain(NOTICE);
    rendered.unmount();
  });

  it("omits overlay copy when the key is absent", () => {
    const rendered = mount({ job: succeeded() });
    const text = renderedText(rendered.container);
    expect(text).toContain("$4.78");
    expect(text).toContain(NOTICE);
    expect(text).not.toContain("Average supermarket estimate");
    expect(text).not.toContain("$12.99");
    expect(text).not.toContain(SPOONACULAR_COST_NOTICE);
    rendered.unmount();
  });

  it("labels incomplete and over-budget plans and a Plaid Sandbox source", () => {
    const incomplete = mount({
      job: succeeded({
        accepted: false,
        total: null,
        lines: [line({ cost_cents: null })],
        planWarnings: [],
        budgetWarnings: [],
      }),
    });
    expect(renderedText(incomplete.container)).toContain("This plan is incomplete.");
    expect(renderedText(incomplete.container)).toContain("Incomplete estimate");
    incomplete.unmount();
    const missingLine = mount({
      job: succeeded({
        accepted: true,
        total: 478,
        lines: [line({ cost_cents: null })],
        planWarnings: [],
        budgetWarnings: [],
      }),
    });
    expect(renderedText(missingLine.container)).toContain("This plan is incomplete.");
    expect(renderedText(missingLine.container)).not.toContain("This estimate is within the plan budget.");
    expect(renderedText(missingLine.container)).toContain("black beans");
    missingLine.unmount();
    const over = mount({ job: succeeded({ accepted: false, total: 9000, source: "plaid_sandbox" }) });
    expect(renderedText(over.container)).toContain("This plan is over budget.");
    expect(renderedText(over.container)).toContain("$90.00");
    expect(renderedText(over.container)).toContain("Source Plaid Sandbox");
    over.unmount();
  });

  it("hides pending amounts for a manual spending source", () => {
    const manual = mount({ job: succeeded({ source: "manual" }) });
    expect(renderedText(manual.container)).toContain("Source Your entered budget");
    expect(within(manual.container).queryAllByText(/^Pending\b/)).toHaveLength(0);
    expect(renderedText(manual.container)).not.toContain("Pending $");
    manual.unmount();
    const fixture = mount({ job: succeeded({ source: "fixture" }) });
    expect(renderedText(fixture.container)).toContain("Pending $2.00");
    expect(within(fixture.container).queryAllByText(/^Pending\b/)).toHaveLength(1);
    fixture.unmount();
  });

  it("labels fixture and Plaid Sandbox and marks unknown sources including plaid", () => {
    const fixture = mount({ job: succeeded({ source: "fixture" }) });
    expect(renderedText(fixture.container)).toContain("Source Demo spending");
    expect(renderedText(fixture.container)).not.toContain("Unverified spending source");
    fixture.unmount();
    const sandbox = mount({ job: succeeded({ source: "plaid_sandbox" }) });
    expect(renderedText(sandbox.container)).toContain("Source Plaid Sandbox");
    expect(renderedText(sandbox.container)).not.toContain("Unverified spending source");
    sandbox.unmount();
    const plaid = mount({ job: succeeded({ source: "plaid" }) });
    expect(renderedText(plaid.container)).toContain("Source Unverified spending source");
    expect(renderedText(plaid.container)).not.toContain("Source Plaid Sandbox");
    expect(renderedText(plaid.container)).not.toContain("Source Demo spending");
    plaid.unmount();
    const unknown = mount({ job: succeeded({ source: "live" }) });
    expect(renderedText(unknown.container)).toContain("Source Unverified spending source");
    expect(renderedText(unknown.container)).not.toContain("Source Plaid Sandbox");
    expect(renderedText(unknown.container)).not.toContain("Source Demo spending");
    unknown.unmount();
  });

  it("keeps the server cost when the draft is dirty", () => {
    const toggle = vi.fn();
    const rendered = mount({
      job: succeeded(),
      dirty: true,
      pantry: ["black_beans"],
      onPantryToggle: toggle,
    });
    const text = renderedText(rendered.container);
    expect(text).toContain("Previous estimate");
    expect(text).toContain("Rebuild the request to apply request changes.");
    expect(text).toContain("$4.78");
    expect(text).toContain("$1.29");
    expect(text).toContain("tortillas");
    const boxes = within(rendered.container).queryAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes[0]?.checked).toBe(true);
    expect(boxes[1]?.checked).toBe(false);
    expect(boxes[0]?.disabled).toBe(false);
    fireEvent.click(boxes[1] as HTMLInputElement);
    expect(toggle).toHaveBeenCalledWith("tortillas");
    expect(renderedText(rendered.container)).toContain("$4.78");
    expect(within(rendered.container).queryAllByRole("button")).toHaveLength(0);
    rendered.unmount();
  });

  it("labels 0 and 2 packages in the plural", () => {
    const rendered = mount({
      job: succeeded({
        lines: [
          line({ packages: 0, cost_cents: 0 }),
          line({ ingredient_id: "tortillas", name: "tortillas", unit: "ct", quantity: 16, packages: 2, cost_cents: 698 }),
        ],
      }),
    });
    const text = renderedText(rendered.container);
    expect(text).toContain("0 packages");
    expect(text).toContain("2 packages");
    expect(text).not.toContain("0 package ");
    expect(text).not.toContain("2 package ");
    rendered.unmount();
  });

  it("shows one copy of an identical plan and budget warning", () => {
    const rendered = mount({
      job: succeeded({ planWarnings: ["Shared warning"], budgetWarnings: ["Shared warning"] }),
    });
    expect(renderedText(rendered.container).split("Shared warning")).toHaveLength(2);
    rendered.unmount();
  });

  it("rebuilds through the callback and keeps the server cost", () => {
    const onRebuild = vi.fn();
    const rendered = mount({
      job: succeeded(),
      dirty: true,
      onRebuild,
    });
    const button = screen.getByRole("button", { name: "Rebuild estimate" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(renderedText(button)).toBe("Rebuild estimate");
    fireEvent.click(button);
    expect(onRebuild).toHaveBeenCalledTimes(1);
    expect(renderedText(rendered.container)).toContain("$4.78");
    rendered.unmount();
  });

  it("disables rebuild when blocked and omits it without a callback", () => {
    const onRebuild = vi.fn();
    const blocked = mount({ job: succeeded(), dirty: true, onRebuild, rebuildDisabled: true });
    expect((within(blocked.container).getByRole("button", { name: "Rebuild estimate" }) as HTMLButtonElement).disabled).toBe(true);
    expect(onRebuild).not.toHaveBeenCalled();
    expect(renderedText(blocked.container)).toContain("$4.78");
    blocked.unmount();
    const clean = mount({ job: succeeded(), dirty: false, onRebuild });
    expect(within(clean.container).queryAllByRole("button")).toHaveLength(0);
    clean.unmount();
  });

  it("disables pantry checkboxes while pending and never adds a shopping link", () => {
    const rendered = mount({ job: succeeded(), pending: true, pantry: [] });
    for (const box of within(rendered.container).queryAllByRole("checkbox")) {
      expect((box as HTMLInputElement).disabled).toBe(true);
      expect((box as HTMLInputElement).checked).toBe(false);
    }
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(renderedText(rendered.container)).toContain("$4.78");
    rendered.unmount();
  });

  it("omits nutrition when meal_nutrition is undefined", () => {
    const rendered = mount({ job: succeeded({ omitNutrition: true }) });
    expect(renderedText(rendered.container)).not.toContain("Estimated nutrition");
    expect(renderedText(rendered.container)).toContain("$4.78");
    rendered.unmount();
  });

  it("shows Spoonacular avg dollars for a purchased matching line", () => {
    const rendered = mount({
      job: succeeded({
        supermarket_estimate: {
          total_cents: 1299,
          notice: SPOONACULAR_COST_NOTICE,
          lines: [{ ingredient_id: "black_beans", cents: 199 }],
        },
      }),
    });
    const text = renderedText(rendered.container);
    expect(text).toContain("Spoonacular avg $1.99 for 425 g");
    expect(text).toContain("$4.78");
    expect(text).toContain("$12.99");
    expect(text).toContain(SPOONACULAR_COST_NOTICE);
    expect(rendered.container.querySelectorAll(".estimate-line-spoonacular")).toHaveLength(1);
    expect(rendered.container.querySelectorAll(".estimate-overlay-total")).toHaveLength(1);
    rendered.unmount();
  });

  it("shows Spoonacular avg unavailable for a matching null cents line", () => {
    const rendered = mount({
      job: succeeded({
        supermarket_estimate: {
          total_cents: 1299,
          notice: SPOONACULAR_COST_NOTICE,
          lines: [{ ingredient_id: "black_beans", cents: null }],
        },
      }),
    });
    expect(renderedText(rendered.container)).toContain("Spoonacular avg unavailable");
    expect(renderedText(rendered.container)).toContain("$12.99");
    expect(renderedText(rendered.container)).toContain(SPOONACULAR_COST_NOTICE);
    rendered.unmount();
  });

  it("omits per-line Spoonacular text for a pantry line with a matching overlay", () => {
    const rendered = mount({
      job: succeeded({
        lines: [line({ from_pantry: true })],
        total: 129,
        supermarket_estimate: {
          total_cents: 1299,
          notice: SPOONACULAR_COST_NOTICE,
          lines: [{ ingredient_id: "black_beans", cents: 199 }],
        },
      }),
    });
    const text = renderedText(rendered.container);
    expect(text).not.toContain("Spoonacular avg");
    expect(text).toContain("$1.29");
    expect(text).toContain("$12.99");
    expect(text).toContain(SPOONACULAR_COST_NOTICE);
    expect(rendered.container.querySelectorAll(".estimate-line-spoonacular")).toHaveLength(0);
    expect(rendered.container.querySelectorAll(".estimate-overlay-total")).toHaveLength(1);
    rendered.unmount();
  });

  it("makes the heading programmatically focusable with and without a result", () => {
    const empty = mount();
    expect(empty.container.querySelector("h2#estimate-heading")?.getAttribute("tabindex")).toBe("-1");
    empty.unmount();
    const withResult = mount({ job: succeeded() });
    expect(
      withResult.container.querySelector("h2#estimate-heading")?.getAttribute("tabindex"),
    ).toBe("-1");
    withResult.unmount();
  });

  it("renders exactly one status node in every state", () => {
    const states: Array<Parameters<typeof mount>[0]> = [
      {},
      { job: { id: "job-1", status: "queued", result: null, error_code: null } },
      { job: { id: "job-1", status: "running", result: null, error_code: null } },
      { job: { id: "job-1", status: "failed", result: null, error_code: "tool" } },
      { job: succeeded() },
      { job: succeeded(), dirty: true, onRebuild: vi.fn() },
    ];
    for (const state of states) {
      if (state === undefined) throw new Error("state must be defined");
      const rendered = mount(state);
      expect(within(rendered.container).getAllByRole("status")).toHaveLength(1);
      const second = rendered.container.querySelector(".estimate-panel")?.children[1];
      expect(second?.className).toBe(state.job?.status === "succeeded" ? "visually-hidden" : "estimate-status");
      rendered.unmount();
    }
  });

  it("shows the dirty sentence once outside the hidden status node", () => {
    const rendered = mount({ job: succeeded(), dirty: true, onRebuild: vi.fn() });
    const status = within(rendered.container).getByRole("status");
    expect(status.className).toBe("visually-hidden");
    const dirty = rendered.container.querySelectorAll(".estimate-dirty");
    expect(dirty).toHaveLength(1);
    const sentence = "Rebuild the request to apply request changes.";
    const outside = Array.from(rendered.container.querySelectorAll("p"))
      .filter((node) => node !== status && (node.textContent ?? "").includes(sentence));
    expect(outside).toHaveLength(1);
    expect(rendered.container.querySelectorAll(".estimate-plan-state")).toHaveLength(1);
    rendered.unmount();
  });

  it("keeps the same status node from queued to succeeded", () => {
    const rendered = mount({
      job: { id: "job-1", status: "queued", result: null, error_code: null },
    });
    const node = within(rendered.container).getByRole("status");
    expect(node.textContent).toBe("The grocery request is queued.");
    const props = {
      pending: false,
      dirty: false,
      pantry: [],
      recipes: [],
      onPantryToggle: (): void => {},
    };
    rendered.rerender(
      createElement(Estimate, {
        ...props,
        job: { id: "job-1", status: "running", result: null, error_code: null },
      }),
    );
    expect(within(rendered.container).getByRole("status")).toBe(node);
    expect(node.textContent).toBe("The grocery request is running.");
    rendered.rerender(createElement(Estimate, { ...props, job: succeeded() }));
    expect(within(rendered.container).getByRole("status")).toBe(node);
    expect(node.textContent).toBe("This estimate is within the plan budget.");
    rendered.unmount();
  });

  it("puts the dirty sentence first in the status text", () => {
    const rendered = mount({ job: succeeded(), dirty: true });
    expect(within(rendered.container).getByRole("status").textContent).toBe(
      "Rebuild the request to apply request changes. This estimate is within the plan budget.",
    );
    expect(rendered.container.querySelector(".estimate-dirty")?.getAttribute("role")).toBeNull();
    rendered.unmount();
  });

  it("omits per-line Spoonacular text when supermarket_estimate is absent", () => {
    const rendered = mount({ job: succeeded() });
    const text = renderedText(rendered.container);
    expect(text).toContain("$4.78");
    expect(text).toContain(NOTICE);
    expect(text).not.toContain("Spoonacular avg");
    expect(text).not.toContain("Average supermarket estimate");
    expect(rendered.container.querySelectorAll(".estimate-line-spoonacular")).toHaveLength(0);
    expect(rendered.container.querySelectorAll(".estimate-overlay-total")).toHaveLength(0);
    rendered.unmount();
  });
});
