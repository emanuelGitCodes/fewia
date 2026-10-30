import { afterEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR } from "./api";
import { INITIAL_PANTRY, RECIPE_ORDER } from "./prototype/prototypeData";
import {
  ProposalConflict,
  applyProposal,
  discardProposal,
  fetchProposal,
} from "./proposalApi";

const ID = "3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b";
const BASE = "9a1b2c3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d";
const recipe = RECIPE_ORDER[0];
const pantry = INITIAL_PANTRY[0];

function body(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: ID,
    status: "pending",
    base_plan_revision_id: BASE,
    operations: [{ op: "ignored" }],
    preview: {
      meals: [{ recipe_id: recipe, servings: 4 }],
      pantry_ingredient_ids: [pantry],
      plan_cap_cents: 5000,
    },
    applied_plan_revision_id: null,
    ...overrides,
  };
}

function reply(status: number, data: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(data), { status }))),
  );
}

const signal = new AbortController().signal;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchProposal", () => {
  it("GETs and parses a proposal without operations", async () => {
    reply(200, body());
    const proposal = await fetchProposal(ID, signal);
    expect(fetch).toHaveBeenCalledWith(`/api/grocery/proposals/${ID}`, { method: "GET", signal });
    expect(proposal.status).toBe("pending");
    expect(proposal.preview.meals).toEqual([{ recipe_id: recipe, servings: 4 }]);
    expect("operations" in proposal).toBe(false);
  });

  it("accepts a null cap and an applied revision id", async () => {
    reply(200, body({
      status: "applied",
      applied_plan_revision_id: BASE,
      preview: { meals: [], pantry_ingredient_ids: [], plan_cap_cents: null },
    }));
    const proposal = await fetchProposal(ID, signal);
    expect(proposal.preview.plan_cap_cents).toBeNull();
    expect(proposal.applied_plan_revision_id).toBe(BASE);
  });

  it.each<[string, Record<string, unknown>]>([
    ["id", { id: "nope" }],
    ["status", { status: "done" }],
    ["base", { base_plan_revision_id: 3 }],
    ["applied id", { applied_plan_revision_id: "x" }],
    ["unknown recipe", { preview: { meals: [{ recipe_id: "nope", servings: 2 }], pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["inherited recipe", { preview: { meals: [{ recipe_id: "constructor", servings: 2 }], pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["servings 0", { preview: { meals: [{ recipe_id: recipe, servings: 0 }], pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["servings 9", { preview: { meals: [{ recipe_id: recipe, servings: 9 }], pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["pantry", { preview: { meals: [], pantry_ingredient_ids: ["nope"], plan_cap_cents: null } }],
    ["negative cap", { preview: { meals: [], pantry_ingredient_ids: [], plan_cap_cents: -1 } }],
    ["fraction cap", { preview: { meals: [], pantry_ingredient_ids: [], plan_cap_cents: 1.5 } }],
    ["missing preview", { preview: null }],
  ])("rejects a bad %s", async (_name, overrides) => {
    reply(200, body(overrides));
    await expect(fetchProposal(ID, signal)).rejects.toThrow(SHAPE_ERROR);
  });

  it("maps 409 to ProposalConflict and other failures to the HTTP error", async () => {
    reply(409, { error: { code: "stale", message: "server text" } });
    await expect(fetchProposal(ID, signal)).rejects.toBeInstanceOf(ProposalConflict);
    reply(500, {});
    await expect(fetchProposal(ID, signal)).rejects.toThrow(HTTP_ERROR);
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("down"))));
    await expect(fetchProposal(ID, signal)).rejects.toThrow(HTTP_ERROR);
  });
});

describe("applyProposal", () => {
  it("POSTs and returns the plan revision id", async () => {
    reply(200, { plan_revision_id: BASE });
    await expect(applyProposal(ID, signal)).resolves.toBe(BASE);
    expect(fetch).toHaveBeenCalledWith(`/api/grocery/proposals/${ID}/apply`, { method: "POST", signal });
  });

  it("maps 409 and rejects a bad body", async () => {
    reply(409, { error: { code: "stale", message: "m" } });
    await expect(applyProposal(ID, signal)).rejects.toBeInstanceOf(ProposalConflict);
    reply(200, { plan_revision_id: "nope" });
    await expect(applyProposal(ID, signal)).rejects.toThrow(SHAPE_ERROR);
  });
});

describe("discardProposal", () => {
  it("POSTs and expects discarded", async () => {
    reply(200, { status: "discarded" });
    await expect(discardProposal(ID, signal)).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith(`/api/grocery/proposals/${ID}/discard`, { method: "POST", signal });
  });

  it("maps 409 and rejects a bad body", async () => {
    reply(409, { error: { code: "applied", message: "m" } });
    await expect(discardProposal(ID, signal)).rejects.toBeInstanceOf(ProposalConflict);
    reply(200, { status: "applied" });
    await expect(discardProposal(ID, signal)).rejects.toThrow(SHAPE_ERROR);
  });
});
