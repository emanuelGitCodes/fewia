// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  consumePlanCheckpoint,
  MAX_BUDGET_DRAFT_LENGTH,
  MAX_CHECKPOINT_LENGTH,
  PLAN_CHECKPOINT_KEY,
  PLAN_CHECKPOINT_TTL_MS,
  PLAN_RESTORE_ERROR,
  readReturnPlan,
  savePlanCheckpoint,
} from "./planCheckpoint";
import { initialPlanState, withPlanBudgetInput } from "./planModel";
import { INGREDIENTS } from "./prototypeData";

const NOW = 1_800_000_000_000;

function checkpoint() {
  const { meals, pantry, checked, view, budgetInput, budgetCents } = initialPlanState();
  return { version: 1, savedAt: NOW, plan: { meals, pantry, checked, view, budgetInput, budgetCents } };
}

function store(value: unknown): void {
  window.sessionStorage.setItem(PLAN_CHECKPOINT_KEY, JSON.stringify(value));
}

beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(NOW);
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/prototype?kroger=connected");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("plan checkpoint", () => {
  it.each(["connected", "error"])("restores the local plan on a %s return without consuming during reads", (marker) => {
    const state = {
      ...withPlanBudgetInput(initialPlanState(), "25.50"),
      meals: [{ recipeId: "bean_tacos", servings: 8 }, { recipeId: "egg_fried_rice", servings: 1 }],
      pantry: ["rice"], checked: ["salsa"], view: "pantry" as const,
      servingsError: { recipeId: "bean_tacos", message: "Transient" },
    };
    expect(savePlanCheckpoint(state)).toBe(true);
    window.history.replaceState(null, "", `/prototype?kroger=${marker}`);
    const expected = { ...state, servingsError: null };
    expect(readReturnPlan()).toEqual({ state: expected, returning: true, error: null, kroger: marker });
    expect(readReturnPlan().state).toEqual(expected);
    expect(window.sessionStorage.getItem(PLAN_CHECKPOINT_KEY)).not.toBeNull();
    expect(consumePlanCheckpoint()).toBe(true);
    expect(readReturnPlan().error).toBe(PLAN_RESTORE_ERROR);
  });

  it.each(["", "12.345", "-1", "invalid", "99999999999999999999999"])("keeps the invalid draft %j and the last valid cents", (draft) => {
    const state = withPlanBudgetInput(withPlanBudgetInput(initialPlanState(), "17.25"), draft);
    expect(savePlanCheckpoint(state)).toBe(true);
    expect(readReturnPlan().state).toEqual(state);
    expect(readReturnPlan().state.budgetError).not.toBeNull();
  });

  it("allows an empty plan and zero cap", () => {
    const state = { ...withPlanBudgetInput(initialPlanState(), "0"), meals: [], pantry: [], checked: [] };
    expect(savePlanCheckpoint(state)).toBe(true);
    expect(readReturnPlan().state).toEqual(state);
  });

  it("accepts three distinct meals and the maximum draft length", () => {
    const state = {
      ...withPlanBudgetInput(initialPlanState(), "x".repeat(MAX_BUDGET_DRAFT_LENGTH)),
      meals: [
        { recipeId: "bean_tacos", servings: 1 },
        { recipeId: "egg_fried_rice", servings: 8 },
        { recipeId: "chickpea_curry", servings: 2 },
      ],
      pantry: Object.keys(INGREDIENTS),
    };
    expect(savePlanCheckpoint(state)).toBe(true);
    expect(readReturnPlan().state).toEqual(state);
  });

  it.each(["", "?kroger=other", "?other=connected"])("ignores checkpoints on unrelated visits %j", (search) => {
    expect(savePlanCheckpoint(withPlanBudgetInput(initialPlanState(), "12"))).toBe(true);
    window.history.replaceState(null, "", `/prototype${search}`);
    const get = vi.spyOn(window.sessionStorage, "getItem");
    expect(readReturnPlan()).toEqual({ state: initialPlanState(), returning: false, error: null, kroger: null });
    expect(get).not.toHaveBeenCalled();
  });

  it("stores only the bounded plan fields", () => {
    const state = { ...initialPlanState(), transcript: "private", token: "private", revisionId: "private" };
    expect(savePlanCheckpoint(state)).toBe(true);
    const raw = window.sessionStorage.getItem(PLAN_CHECKPOINT_KEY) ?? "";
    expect(JSON.parse(raw)).toEqual(checkpoint());
    expect(raw).not.toContain("private");
  });

  const invalidPlans: [string, Record<string, unknown>][] = [
    ["unknown field", { extra: true }],
    ["missing meals", { meals: undefined }],
    ["unknown recipe", { meals: [{ recipeId: "missing", servings: 2 }] }],
    ["inherited recipe", { meals: [{ recipeId: "constructor", servings: 2 }] }],
    ["recipe type", { meals: [{ recipeId: 1, servings: 2 }] }],
    ["extra meal field", { meals: [{ recipeId: "bean_tacos", servings: 2, extra: true }] }],
    ["null meal", { meals: [null] }],
    ["duplicate meal", { meals: [{ recipeId: "bean_tacos", servings: 2 }, { recipeId: "bean_tacos", servings: 3 }] }],
    ["too many meals", { meals: ["bean_tacos", "egg_fried_rice", "chickpea_curry", "lentil_soup"].map((recipeId) => ({ recipeId, servings: 2 })) }],
    ["low servings", { meals: [{ recipeId: "bean_tacos", servings: 0 }] }],
    ["high servings", { meals: [{ recipeId: "bean_tacos", servings: 9 }] }],
    ["fractional servings", { meals: [{ recipeId: "bean_tacos", servings: 1.5 }] }],
    ["string servings", { meals: [{ recipeId: "bean_tacos", servings: "2" }] }],
    ["boolean servings", { meals: [{ recipeId: "bean_tacos", servings: true }] }],
    ["unknown pantry", { pantry: ["missing"] }],
    ["inherited pantry", { pantry: ["constructor"] }],
    ["duplicate pantry", { pantry: ["salsa", "salsa"] }],
    ["pantry type", { pantry: "salsa" }],
    ["pantry ID type", { pantry: [1] }],
    ["pantry bound", { pantry: Array.from({ length: Object.keys(INGREDIENTS).length + 1 }, () => "salsa") }],
    ["unknown check", { checked: ["missing"] }],
    ["duplicate check", { checked: ["salsa", "salsa"] }],
    ["check type", { checked: [true] }],
    ["check array", { checked: {} }],
    ["unbought check", { checked: ["salt"] }],
    ["absent check", { checked: ["rice"] }],
    ["invalid view", { view: "chat" }],
    ["view type", { view: null }],
    ["draft type", { budgetInput: 40 }],
    ["long draft", { budgetInput: "x".repeat(MAX_BUDGET_DRAFT_LENGTH + 1) }],
    ["negative cents", { budgetCents: -1 }],
    ["unsafe cents", { budgetCents: Number.MAX_SAFE_INTEGER + 1 }],
    ["fractional cents", { budgetCents: 4.5 }],
    ["cents type", { budgetCents: "4000" }],
    ["mismatched valid draft", { budgetInput: "25", budgetCents: 4000 }],
  ];

  it.each(invalidPlans)("rejects the entire checkpoint for %s", (_name, fields) => {
    const value = checkpoint();
    store({ ...value, plan: { ...value.plan, ...fields } });
    expect(readReturnPlan()).toEqual({ state: initialPlanState(), returning: true, error: PLAN_RESTORE_ERROR, kroger: "connected" });
  });

  it.each([
    null, [], {},
    { ...checkpoint(), version: 2 },
    { ...checkpoint(), version: "1" },
    { ...checkpoint(), extra: "field" },
    { ...checkpoint(), plan: null },
    { ...checkpoint(), plan: [] },
    { ...checkpoint(), savedAt: "now" },
    { ...checkpoint(), savedAt: -1 },
    { ...checkpoint(), savedAt: NOW + 0.5 },
    { ...checkpoint(), savedAt: NOW + 1 },
    { ...checkpoint(), savedAt: NOW - PLAN_CHECKPOINT_TTL_MS - 1 },
  ].map((value) => [value]))("rejects an invalid envelope %#", (value) => {
    store(value);
    expect(readReturnPlan().error).toBe(PLAN_RESTORE_ERROR);
  });

  it.each(["{broken", " ".repeat(MAX_CHECKPOINT_LENGTH + 1)])("rejects corrupt or oversized serialization %#", (raw) => {
    window.sessionStorage.setItem(PLAN_CHECKPOINT_KEY, raw);
    expect(readReturnPlan().error).toBe(PLAN_RESTORE_ERROR);
  });

  it("accepts a checkpoint at its TTL boundary", () => {
    store({ ...checkpoint(), savedAt: NOW - PLAN_CHECKPOINT_TTL_MS });
    expect(readReturnPlan().error).toBeNull();
  });

  it("reports read and consume failures without exposing exception details", () => {
    const getItem = vi.fn((): string | null => { throw new Error("private"); });
    const removeItem = vi.fn((): void => { throw new Error("private"); });
    vi.stubGlobal("sessionStorage", { getItem, removeItem });
    expect(readReturnPlan().error).toBe(PLAN_RESTORE_ERROR);
    expect(getItem).toHaveBeenCalledWith(PLAN_CHECKPOINT_KEY);
    expect(consumePlanCheckpoint()).toBe(false);
    expect(removeItem).toHaveBeenCalledWith(PLAN_CHECKPOINT_KEY);
  });

  it("refuses to save invalid UI state", () => {
    expect(savePlanCheckpoint({ ...initialPlanState(), budgetCents: -1 })).toBe(false);
    expect(window.sessionStorage.getItem(PLAN_CHECKPOINT_KEY)).toBeNull();
  });
});
