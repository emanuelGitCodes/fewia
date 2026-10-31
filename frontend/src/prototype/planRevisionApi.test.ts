import { afterEach, describe, expect, it, vi } from "vitest";
import { initialPlanState, type PlanState } from "./planModel";
import { planRevisionBody, savePlanRevision } from "./planRevisionApi";
import { INGREDIENTS } from "./prototypeData";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("planRevisionBody", () => {
  it("maps meals and the cap and drops unknown or repeated pantry ids", () => {
    const known = Object.keys(INGREDIENTS)[0];
    const base = initialPlanState();
    const state: PlanState = {
      ...base,
      pantry: [known, "not-an-ingredient", known],
      budgetCents: 4200,
    };
    const body = planRevisionBody(state);
    expect(body.pantry_ingredient_ids).toEqual([known]);
    expect(body.plan_cap_cents).toBe(4200);
    expect(body.meals).toEqual(
      state.meals.map((meal) => ({ recipe_id: meal.recipeId, servings: meal.servings })),
    );
  });
});

describe("savePlanRevision", () => {
  const body = { meals: [], pantry_ingredient_ids: [], plan_cap_cents: 100 };

  it("posts the body and returns the revision id", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ plan_revision_id: "rev-1" }), { status: 201 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(savePlanRevision(body)).resolves.toBe("rev-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/grocery/plans",
      expect.objectContaining({ method: "POST", body: JSON.stringify(body) }),
    );
  });

  it("throws on an error status", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 422 }))));
    await expect(savePlanRevision(body)).rejects.toThrow();
  });

  it("throws on a malformed body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ id: 1 }), { status: 201 }))),
    );
    await expect(savePlanRevision(body)).rejects.toThrow();
  });
});
