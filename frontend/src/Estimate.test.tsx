/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  SAMPLE_ESTIMATE_NOTICE,
  SPOONACULAR_COST_NOTICE,
  type GroceryJob,
  type PlanLine,
  type SupermarketEstimate,
} from "./apiTypes";
import { Estimate } from "./Estimate";
import {
  NUTRITION_NOTICE,
  NUTRITION_PORTION_NOTICE,
  type MacroTotals,
  type MealPlanNutrition,
} from "./nutritionTypes";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance | undefined {
  return root.findAllByType("button").find((node) => childText(node) === name);
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

function macros(overrides: Partial<MacroTotals> = {}): MacroTotals {
  return {
    energy_kcal: 200,
    protein_mg: 10000,
    carbohydrate_mg: 30000,
    fat_mg: 8000,
    ...overrides,
  };
}

function nutrition(overrides: Partial<MealPlanNutrition> = {}): MealPlanNutrition {
  return {
    notice: NUTRITION_NOTICE,
    portion_notice: NUTRITION_PORTION_NOTICE,
    total: macros({ energy_kcal: 400, protein_mg: 20000, carbohydrate_mg: 60000, fat_mg: 16000 }),
    meals: [
      {
        recipe_id: "bean_tacos",
        servings: 2,
        per_serving: macros(),
        total: macros({ energy_kcal: 400, protein_mg: 20000, carbohydrate_mg: 60000, fat_mg: 16000 }),
      },
    ],
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
  nutrition?: MealPlanNutrition;
} = {}): GroceryJob {
  const lines = overrides.lines ?? [line(), line({ ingredient_id: "tortillas", name: "tortillas", unit: "ct", quantity: 8, packages: 1, cost_cents: 349 })];
  return {
    id: "job-1",
    status: "succeeded",
    error_code: null,
    result: {
      spending_source: overrides.source ?? "fixture",
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
      ...(overrides.nutrition === undefined ? {} : { nutrition: overrides.nutrition }),
    },
  };
}

function mount(
  props: Partial<{
    job: GroceryJob | null;
    pending: boolean;
    dirty: boolean;
    pantry: string[];
    onPantryToggle: (id: string) => void;
    onRebuild: () => void | Promise<void>;
    rebuildDisabled: boolean;
  }> = {},
): ReactTestRenderer {
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(
      createElement(Estimate, {
        job: props.job ?? null,
        pending: props.pending ?? false,
        dirty: props.dirty ?? false,
        pantry: props.pantry ?? [],
        onPantryToggle: props.onPantryToggle ?? ((): void => {}),
        onRebuild: props.onRebuild,
        rebuildDisabled: props.rebuildDisabled,
      }),
    );
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return renderer;
}

describe("Estimate", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        throw new Error("fetch must not run");
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders an empty state when no job is present", () => {
    const renderer = mount();
    expect(childText(renderer.root)).toContain("No grocery budget or meal plan is set yet.");
    expect(childText(renderer.root)).not.toContain("$");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("renders pending, queued, running, and failed without a completed result", () => {
    const pending = mount({ pending: true });
    expect(childText(pending.root)).toContain("The grocery request is in progress.");
    pending.unmount();
    const queued = mount({ job: { id: "job-1", status: "queued", result: null, error_code: null } });
    expect(childText(queued.root)).toContain("The grocery request is queued.");
    expect(childText(queued.root)).not.toContain(NOTICE);
    queued.unmount();
    const running = mount({ job: { id: "job-1", status: "running", result: null, error_code: null } });
    expect(childText(running.root)).toContain("The grocery request is running.");
    running.unmount();
    const failed = mount({
      job: { id: "job-1", status: "failed", result: succeeded().result, error_code: "tool" },
    });
    expect(childText(failed.root)).toContain("The grocery request failed.");
    expect(childText(failed.root)).not.toContain("$4.78");
    expect(childText(failed.root)).not.toContain(NOTICE);
    failed.unmount();
  });

  it("shows the server total, notice, every row, and budget labels", () => {
    const renderer = mount({ job: succeeded() });
    const text = childText(renderer.root);
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
    expect(renderer.root.findAllByType("input")).toHaveLength(2);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(text.toLowerCase()).not.toMatch(/checkout/);
    expect(text).not.toContain("Average supermarket estimate");
    expect(text).toContain("Spoonacular estimate");
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeDefined();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("does not render a job overlay and waits for an explicit lookup", () => {
    const renderer = mount({
      job: succeeded({
        supermarket_estimate: { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE },
      }),
    });
    const text = childText(renderer.root);
    expect(text).toContain("$4.78");
    expect(text).not.toContain("$12.99");
    expect(text).not.toContain("Average supermarket estimate");
    expect(text).not.toContain(SPOONACULAR_COST_NOTICE);
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeDefined();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("omits overlay dollars when the job has no supermarket_estimate", () => {
    const renderer = mount({ job: succeeded() });
    const text = childText(renderer.root);
    expect(text).toContain("$4.78");
    expect(text).toContain(NOTICE);
    expect(text).not.toContain("Average supermarket estimate");
    expect(text).not.toContain("$12.99");
    expect(text).not.toContain(SPOONACULAR_COST_NOTICE);
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeDefined();
    renderer.unmount();
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
    expect(childText(incomplete.root)).toContain("This plan is incomplete.");
    expect(childText(incomplete.root)).toContain("Incomplete estimate");
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
    expect(childText(missingLine.root)).toContain("This plan is incomplete.");
    expect(childText(missingLine.root)).not.toContain("This estimate is within the plan budget.");
    expect(childText(missingLine.root)).toContain("black beans");
    missingLine.unmount();
    const over = mount({ job: succeeded({ accepted: false, total: 9000, source: "plaid_sandbox" }) });
    expect(childText(over.root)).toContain("This plan is over budget.");
    expect(childText(over.root)).toContain("$90.00");
    expect(childText(over.root)).toContain("Source Plaid Sandbox");
    over.unmount();
  });

  it("labels fixture and Plaid Sandbox and marks unknown sources including plaid", () => {
    const fixture = mount({ job: succeeded({ source: "fixture" }) });
    expect(childText(fixture.root)).toContain("Source Demo spending");
    expect(childText(fixture.root)).not.toContain("Unverified spending source");
    fixture.unmount();
    const sandbox = mount({ job: succeeded({ source: "plaid_sandbox" }) });
    expect(childText(sandbox.root)).toContain("Source Plaid Sandbox");
    expect(childText(sandbox.root)).not.toContain("Unverified spending source");
    sandbox.unmount();
    const plaid = mount({ job: succeeded({ source: "plaid" }) });
    expect(childText(plaid.root)).toContain("Source Unverified spending source");
    expect(childText(plaid.root)).not.toContain("Source Plaid Sandbox");
    expect(childText(plaid.root)).not.toContain("Source Demo spending");
    plaid.unmount();
    const unknown = mount({ job: succeeded({ source: "live" }) });
    expect(childText(unknown.root)).toContain("Source Unverified spending source");
    expect(childText(unknown.root)).not.toContain("Source Plaid Sandbox");
    expect(childText(unknown.root)).not.toContain("Source Demo spending");
    unknown.unmount();
  });

  it("keeps the server cost when the draft is dirty", () => {
    const toggle = vi.fn();
    const renderer = mount({
      job: succeeded(),
      dirty: true,
      pantry: ["black_beans"],
      onPantryToggle: toggle,
    });
    const text = childText(renderer.root);
    expect(text).toContain("Previous estimate");
    expect(text).toContain("Rebuild the request to apply request changes.");
    expect(text).toContain("$4.78");
    expect(text).toContain("$1.29");
    expect(text).toContain("tortillas");
    const boxes = renderer.root.findAllByType("input");
    expect(boxes[0]?.props.checked).toBe(true);
    expect(boxes[1]?.props.checked).toBe(false);
    expect(boxes[0]?.props.disabled).toBe(false);
    act(() => {
      (boxes[1]?.props.onChange as (() => void) | undefined)?.();
    });
    expect(toggle).toHaveBeenCalledWith("tortillas");
    expect(childText(renderer.root)).toContain("$4.78");
    expect(buttonNamed(renderer.root, "Rebuild estimate")).toBeUndefined();
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeUndefined();
    renderer.unmount();
  });

  it("labels 0 and 2 packages in the plural", () => {
    const renderer = mount({
      job: succeeded({
        lines: [
          line({ packages: 0, cost_cents: 0 }),
          line({ ingredient_id: "tortillas", name: "tortillas", unit: "ct", quantity: 16, packages: 2, cost_cents: 698 }),
        ],
      }),
    });
    const text = childText(renderer.root);
    expect(text).toContain("0 packages");
    expect(text).toContain("2 packages");
    expect(text).not.toContain("0 package ");
    expect(text).not.toContain("2 package ");
    renderer.unmount();
  });

  it("shows one copy of an identical plan and budget warning", () => {
    const renderer = mount({
      job: succeeded({ planWarnings: ["Shared warning"], budgetWarnings: ["Shared warning"] }),
    });
    expect(childText(renderer.root).split("Shared warning")).toHaveLength(2);
    renderer.unmount();
  });

  it("rebuilds through the callback and keeps the server cost", () => {
    const onRebuild = vi.fn();
    const renderer = mount({
      job: succeeded(),
      dirty: true,
      onRebuild,
    });
    const button = buttonNamed(renderer.root, "Rebuild estimate");
    expect(button?.props.disabled).toBe(false);
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeUndefined();
    act(() => {
      (button?.props.onClick as (() => void) | undefined)?.();
    });
    expect(onRebuild).toHaveBeenCalledTimes(1);
    expect(childText(renderer.root)).toContain("$4.78");
    renderer.unmount();
  });

  it("disables rebuild when blocked and omits it without a callback", () => {
    const onRebuild = vi.fn();
    const blocked = mount({ job: succeeded(), dirty: true, onRebuild, rebuildDisabled: true });
    expect(buttonNamed(blocked.root, "Rebuild estimate")?.props.disabled).toBe(true);
    expect(buttonNamed(blocked.root, "Check supermarket estimate")).toBeUndefined();
    expect(onRebuild).not.toHaveBeenCalled();
    expect(childText(blocked.root)).toContain("$4.78");
    blocked.unmount();
    const clean = mount({ job: succeeded(), dirty: false, onRebuild });
    expect(buttonNamed(clean.root, "Rebuild estimate")).toBeUndefined();
    expect(buttonNamed(clean.root, "Check supermarket estimate")).toBeDefined();
    clean.unmount();
  });

  it("disables pantry checkboxes while pending and never adds a shopping link", () => {
    const renderer = mount({ job: succeeded(), pending: true, pantry: [] });
    for (const box of renderer.root.findAllByType("input")) {
      expect(box.props.disabled).toBe(true);
      expect(box.props.checked).toBe(false);
    }
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(childText(renderer.root)).toContain("$4.78");
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeUndefined();
    renderer.unmount();
  });

  it("renders nutrition from the job payload before the ingredient list", () => {
    const renderer = mount({ job: succeeded({ nutrition: nutrition() }) });
    const text = childText(renderer.root);
    expect(text).toContain("Estimated nutrition");
    expect(text).toContain("Calories (kcal)");
    expect(text).toContain("Protein (g)");
    expect(text).toContain("Carbs (g)");
    expect(text).toContain("Fat (g)");
    expect(text).toContain("400 kcal");
    expect(text).toContain("20.0 g");
    expect(text).toContain("200 kcal");
    expect(text).toContain("10.0 g");
    expect(text).toContain("Bean Tacos");
    expect(text).toContain("2 servings");
    expect(text).toContain("Per serving");
    expect(text).toContain(NUTRITION_NOTICE);
    expect(text).toContain("Pantry ingredients are included.");
    expect(text.indexOf("Estimated nutrition")).toBeLessThan(text.indexOf("black beans"));
    expect(text.indexOf("Total for selected plan")).toBeLessThan(text.indexOf("black beans"));
    expect(text).not.toContain("sodium");
    expect(text).not.toContain("iron");
    expect(renderer.root.findByType("a").props.href).toBe("https://fdc.nal.usda.gov/");
    expect(text).toContain("$4.78");
    renderer.unmount();
  });

  it("keeps previous nutrition values when the estimate is dirty", () => {
    const renderer = mount({ job: succeeded({ nutrition: nutrition() }), dirty: true });
    const text = childText(renderer.root);
    expect(text).toContain("Nutrition for previous plan");
    expect(text).toContain("These values belong to the last saved plan.");
    expect(text).toContain("400 kcal");
    expect(text).toContain("Rebuild the request to apply request changes.");
    renderer.unmount();
  });

  it("resets the supermarket lookup when the plan job changes", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: () => Promise.resolve({ total_cents: 1299, notice: SPOONACULAR_COST_NOTICE }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount({ job: succeeded() });
    await act(async () => {
      const lookup = buttonNamed(renderer.root, "Check supermarket estimate");
      if (lookup === undefined) {
        throw new Error("missing lookup");
      }
      (lookup.props.onClick as () => void)();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(childText(renderer.root)).toContain("$12.99");
    act(() => {
      renderer.update(
        createElement(Estimate, {
          job: { ...succeeded(), id: "job-2" },
          pending: false,
          dirty: false,
          pantry: [],
          onPantryToggle: (): void => {},
        }),
      );
    });
    expect(childText(renderer.root)).not.toContain("$12.99");
    expect(buttonNamed(renderer.root, "Check supermarket estimate")).toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });
});

