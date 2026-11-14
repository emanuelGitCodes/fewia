/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR, acceptSession, captureSessionGuard, currentSession, loseSession } from "./api";
import { TEST_SESSION, clearTestSession, seedTestSession } from "./testSession";
import { INITIAL_PANTRY, RECIPE_ORDER } from "./prototype/prototypeData";
import {
  ProposalConflict,
  ProposalConstraintsError,
  applyProposal,
  discardProposal,
  fetchProposal,
} from "./proposalApi";

const ID = "3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b";
const BASE = "9a1b2c3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d";
const recipe = RECIPE_ORDER[0];
const pantry = INITIAL_PANTRY[0];
const one = { recipe_id: recipe, servings: 2 };
const snapshot = { meals: [one], pantry_ingredient_ids: [pantry], plan_cap_cents: 5000 };

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

function expectRequest(path: string, init: RequestInit): void {
  expect(fetch).toHaveBeenCalledWith(path, {
    ...init,
    headers: expect.any(Headers),
    credentials: "same-origin",
    redirect: "error",
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
  expect(headers.get("X-FEWIA-Workspace")).toBe(TEST_SESSION.workspace_id);
  expect(headers.get("Content-Type")).toBe(new Headers(init.headers).get("Content-Type"));
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function delayedBody(status: number, data: unknown): {
  started: Promise<void>;
  resolve: (value: unknown) => void;
} {
  const started = deferred<void>();
  const parsed = deferred<unknown>();
  const response = new Response(JSON.stringify(data), { status });
  vi.spyOn(response, "json").mockImplementation(() => {
    started.resolve();
    return parsed.promise;
  });
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response)));
  return { started: started.promise, resolve: parsed.resolve };
}

const actions: [string, (signal: AbortSignal) => Promise<unknown>, unknown][] = [
  ["GET", (signal) => fetchProposal(ID, signal), body()],
  ["Apply", (signal) => applyProposal(ID, signal, 5000), { plan_revision_id: BASE, snapshot }],
  ["Discard", (signal) => discardProposal(ID, signal), { status: "discarded" }],
];

beforeEach(() => {
  seedTestSession();
});

afterEach(() => {
  clearTestSession();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("fetchProposal", () => {
  it("GETs and parses a proposal without operations", async () => {
    reply(200, body());
    const proposal = await fetchProposal(ID, signal);
    expectRequest(`/api/grocery/proposals/${ID}`, { method: "GET", signal });
    expect(proposal.status).toBe("pending");
    expect(proposal.preview.meals).toEqual([{ recipe_id: recipe, servings: 4 }]);
    expect("operations" in proposal).toBe(false);
  });

  it("accepts a null cap and an applied revision id", async () => {
    reply(200, body({
      status: "applied",
      applied_plan_revision_id: BASE,
      preview: { meals: [{ recipe_id: recipe, servings: 2 }], pantry_ingredient_ids: [], plan_cap_cents: null },
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
    ["pantry", { preview: { meals: [one], pantry_ingredient_ids: ["nope"], plan_cap_cents: null } }],
    ["negative cap", { preview: { meals: [one], pantry_ingredient_ids: [], plan_cap_cents: -1 } }],
    ["fraction cap", { preview: { meals: [one], pantry_ingredient_ids: [], plan_cap_cents: 1.5 } }],
    ["no meals", { preview: { meals: [], pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["four meals", { preview: { meals: [0, 1, 2, 3].map((i) => ({ recipe_id: RECIPE_ORDER[i], servings: 2 })), pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["duplicate recipe", { preview: { meals: [one, one], pantry_ingredient_ids: [], plan_cap_cents: null } }],
    ["duplicate pantry id", { preview: { meals: [one], pantry_ingredient_ids: [pantry, pantry], plan_cap_cents: null } }],
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
  it.each([
    "over_budget", "diet_conflict", "exclusion_conflict", "estimate_unavailable",
  ] as const)("recognizes the %s constraint reason", async (reason) => {
    reply(409, { detail: { code: "proposal_constraints", reason, total_cents: 1703, available_cents: 1702 } });
    await expect(applyProposal(ID, signal, 5000)).rejects.toMatchObject({
      name: "ProposalConstraintsError",
      reason,
      amounts: reason === "over_budget" ? { totalCents: 1703, availableCents: 1702 } : null,
    });
  });

  it.each([
    {},
    { total_cents: "1703", available_cents: 1702 },
    { total_cents: 1703, available_cents: "1702" },
    { total_cents: -1, available_cents: 0 },
    { total_cents: 1703, available_cents: -1 },
    { total_cents: 1703.5, available_cents: 1702 },
    { total_cents: 1703, available_cents: 1702.5 },
    { total_cents: Number.MAX_SAFE_INTEGER + 1, available_cents: 1702 },
    { total_cents: 1703, available_cents: Number.MAX_SAFE_INTEGER + 1 },
    { total_cents: null, available_cents: 1702 },
    { total_cents: 1702, available_cents: 1702 },
    { total_cents: 1701, available_cents: 1702 },
  ])("keeps a budget rejection definitive without usable amounts: %j", async (amounts) => {
    reply(409, { detail: { code: "proposal_constraints", reason: "over_budget", ...amounts } });
    await expect(applyProposal(ID, signal, 5000)).rejects.toBeInstanceOf(ProposalConstraintsError);
    await expect(applyProposal(ID, signal, 5000)).rejects.toMatchObject({ reason: "over_budget", amounts: null });
  });

  it.each([
    null,
    { detail: null },
    { detail: [] },
    { detail: { code: "proposal_constraints", reason: "server text" } },
    { detail: { code: "proposal_constraints", reason: "constructor" } },
    { detail: { code: "proposal_constraints" } },
    { detail: { code: "other", reason: "over_budget" } },
    { code: "proposal_constraints", reason: "over_budget" },
  ])("keeps an unrecognized response generic: %j", async (data) => {
    reply(409, data);
    await expect(applyProposal(ID, signal, 5000)).rejects.toBeInstanceOf(ProposalConflict);
  });

  it("keeps invalid JSON generic", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not JSON", { status: 409 }))));
    await expect(applyProposal(ID, signal, 5000)).rejects.toBeInstanceOf(ProposalConflict);
  });

  it.each([fetchProposal, discardProposal])("keeps constraint payloads generic outside Apply", async (action) => {
    reply(409, { detail: { code: "proposal_constraints", reason: "over_budget" } });
    await expect(action(ID, signal)).rejects.toBeInstanceOf(ProposalConflict);
  });

  it("returns the plan revision id and committed snapshot", async () => {
    reply(200, { plan_revision_id: BASE, snapshot });
    await expect(applyProposal(ID, signal, 5000)).resolves.toEqual({ plan_revision_id: BASE, snapshot });
  });

  it.each([0, 1702, Number.MAX_SAFE_INTEGER])("POSTs the supplied cap of %i cents as JSON", async (planCapCents) => {
    const committed = { ...snapshot, plan_cap_cents: planCapCents };
    reply(200, { plan_revision_id: BASE, snapshot: committed });
    await expect(applyProposal(ID, signal, planCapCents)).resolves.toEqual({ plan_revision_id: BASE, snapshot: committed });
    expectRequest(`/api/grocery/proposals/${ID}/apply`, {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_cap_cents: planCapCents }),
    });
  });

  it.each([undefined, null, "1702", -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])(
    "rejects an invalid current cap before sending: %s",
    async (cap) => {
      reply(200, { plan_revision_id: BASE, snapshot });
      await expect(applyProposal(ID, signal, cap as number)).rejects.toThrow(SHAPE_ERROR);
      expect(fetch).not.toHaveBeenCalled();
    },
  );

  it("accepts a committed snapshot with a null cap", async () => {
    const committed = { ...snapshot, plan_cap_cents: null };
    reply(200, { plan_revision_id: BASE, snapshot: committed });
    await expect(applyProposal(ID, signal, 5000)).resolves.toEqual({ plan_revision_id: BASE, snapshot: committed });
  });

  it.each<[string, unknown]>([
    ["missing snapshot", undefined],
    ["null snapshot", null],
    ["missing meals", { ...snapshot, meals: undefined }],
    ["missing pantry", { ...snapshot, pantry_ingredient_ids: undefined }],
    ["missing cap", { ...snapshot, plan_cap_cents: undefined }],
    ["unknown recipe", { ...snapshot, meals: [{ recipe_id: "nope", servings: 2 }] }],
    ["inherited recipe", { ...snapshot, meals: [{ recipe_id: "constructor", servings: 2 }] }],
    ["missing servings", { ...snapshot, meals: [{ recipe_id: recipe }] }],
    ["zero servings", { ...snapshot, meals: [{ recipe_id: recipe, servings: 0 }] }],
    ["nine servings", { ...snapshot, meals: [{ recipe_id: recipe, servings: 9 }] }],
    ["fraction servings", { ...snapshot, meals: [{ recipe_id: recipe, servings: 1.5 }] }],
    ["no meals", { ...snapshot, meals: [] }],
    ["four meals", { ...snapshot, meals: [0, 1, 2, 3].map((i) => ({ recipe_id: RECIPE_ORDER[i], servings: 2 })) }],
    ["duplicate meals", { ...snapshot, meals: [one, one] }],
    ["unknown pantry", { ...snapshot, pantry_ingredient_ids: ["nope"] }],
    ["inherited pantry", { ...snapshot, pantry_ingredient_ids: ["constructor"] }],
    ["duplicate pantry", { ...snapshot, pantry_ingredient_ids: [pantry, pantry] }],
    ["negative cap", { ...snapshot, plan_cap_cents: -1 }],
    ["fraction cap", { ...snapshot, plan_cap_cents: 1.5 }],
    ["string cap", { ...snapshot, plan_cap_cents: "5000" }],
    ["unsafe cap", { ...snapshot, plan_cap_cents: Number.MAX_SAFE_INTEGER + 1 }],
  ])("rejects a committed snapshot with %s", async (_name, invalid) => {
    reply(200, { plan_revision_id: BASE, snapshot: invalid });
    await expect(applyProposal(ID, signal, 5000)).rejects.toThrow(SHAPE_ERROR);
  });

  it("maps 409 and rejects a bad body", async () => {
    reply(409, { error: { code: "stale", message: "m" } });
    await expect(applyProposal(ID, signal, 5000)).rejects.toBeInstanceOf(ProposalConflict);
    reply(200, { plan_revision_id: "nope", snapshot });
    await expect(applyProposal(ID, signal, 5000)).rejects.toThrow(SHAPE_ERROR);
  });
});

describe("discardProposal", () => {
  it("POSTs JSON confirmation and expects discarded", async () => {
    reply(200, { status: "discarded" });
    await expect(discardProposal(ID, signal)).resolves.toBeUndefined();
    expectRequest(`/api/grocery/proposals/${ID}/discard`, {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    });
  });

  it("maps 409 and rejects a bad body", async () => {
    reply(409, { error: { code: "applied", message: "m" } });
    await expect(discardProposal(ID, signal)).rejects.toBeInstanceOf(ProposalConflict);
    reply(200, { status: "applied" });
    await expect(discardProposal(ID, signal)).rejects.toThrow(SHAPE_ERROR);
  });
});

describe("proposal session boundary", () => {
  it.each(actions)("blocks %s without a session", async (_name, action, data) => {
    loseSession();
    reply(200, data);
    await expect(action(signal)).rejects.toThrow(HTTP_ERROR);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(actions)("clears the session on %s 401 without replay", async (_name, action) => {
    reply(401, {});
    await expect(action(signal)).rejects.toThrow(HTTP_ERROR);
    expect(currentSession()).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(actions)("preserves the session on %s generic 409 without replay", async (_name, action) => {
    reply(409, { error: { code: "stale", message: "server text" } });
    await expect(action(signal)).rejects.toBeInstanceOf(ProposalConflict);
    expect(currentSession()).toEqual(TEST_SESSION);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(actions)("preserves a plain %s 409", async (_name, action) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("Conflict", { status: 409 }))));
    await expect(action(signal)).rejects.toBeInstanceOf(ProposalConflict);
    expect(currentSession()).toEqual(TEST_SESSION);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  describe.each(actions)("%s JSON freshness", (_name, action, data) => {
    it.each([
      ["workspace switch", () => { acceptSession({ ...TEST_SESSION, workspace_id: ID }); }],
      ["auth switch", () => { acceptSession({ ...TEST_SESSION, auth_mode: "alb" }); }],
      ["session loss", () => { loseSession(); }],
      ["session loss and restoration", () => { loseSession(); acceptSession(TEST_SESSION); }],
      ["workspace round trip", () => {
        acceptSession({ ...TEST_SESSION, workspace_id: ID });
        acceptSession(TEST_SESSION);
      }],
    ] as const)("rejects JSON after %s", async (_change, change) => {
      const delayed = delayedBody(200, data);
      const pending = action(signal);
      const rejected = expect(pending).rejects.toThrow(HTTP_ERROR);
      await delayed.started;
      change();
      const active = currentSession();
      delayed.resolve(data);
      await rejected;
      expect(currentSession()).toEqual(active);
      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("accepts JSON after same-workspace validation", async () => {
      const delayed = delayedBody(200, data);
      const pending = action(signal);
      await delayed.started;
      const previous = currentSession();
      acceptSession(TEST_SESSION);
      expect(currentSession()).not.toBe(previous);
      delayed.resolve(data);
      await pending;
      expect(currentSession()).toEqual(TEST_SESSION);
      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("honors an abort before sending", async () => {
      reply(200, data);
      const controller = new AbortController();
      controller.abort();
      await expect(action(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
      expect(fetch).not.toHaveBeenCalled();
    });

    it("honors an abort during body parsing", async () => {
      const delayed = delayedBody(200, data);
      const controller = new AbortController();
      const pending = action(controller.signal);
      const rejected = expect(pending).rejects.toMatchObject({ name: "AbortError" });
      await delayed.started;
      controller.abort();
      await rejected;
      delayed.resolve(data);
      expect(currentSession()).toEqual(TEST_SESSION);
      expect(fetch).toHaveBeenCalledTimes(1);
    });
  });

  it("rejects stale constraint JSON after session restoration", async () => {
    const data = { detail: { code: "proposal_constraints", reason: "over_budget" } };
    const delayed = delayedBody(409, data);
    const pending = applyProposal(ID, signal, 5000);
    const rejected = expect(pending).rejects.toThrow(HTTP_ERROR);
    await delayed.started;
    loseSession();
    acceptSession(TEST_SESSION);
    delayed.resolve(data);
    await rejected;
    expect(currentSession()).toEqual(TEST_SESSION);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("honors aborts while parsing a constraint conflict", async () => {
    const data = { detail: { code: "proposal_constraints", reason: "over_budget" } };
    const delayed = delayedBody(409, data);
    const controller = new AbortController();
    const pending = applyProposal(ID, controller.signal, 5000);
    const rejected = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await delayed.started;
    controller.abort();
    await rejected;
    delayed.resolve(data);
    expect(currentSession()).toEqual(TEST_SESSION);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps a mounted card guard invalid after the original workspace returns", () => {
    const isCurrent = captureSessionGuard();
    acceptSession(TEST_SESSION);
    expect(isCurrent()).toBe(true);
    loseSession();
    acceptSession(TEST_SESSION);
    expect(isCurrent()).toBe(false);
  });
});
