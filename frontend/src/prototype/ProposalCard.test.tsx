/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProposalConflict, type AppliedProposal, type Proposal, type ProposalPreview } from "../proposalApi";
import * as api from "../proposalApi";
import { clearTestSession, seedTestSession, TEST_SESSION } from "../testSession";
import {
  ACTION_ERROR_LINE,
  APPLIED_LINE,
  DISCARDED_LINE,
  LOAD_ERROR_LINE,
  ProposalCard,
  UNCONFIRMED_LINE,
  describeChange,
} from "./ProposalCard";
import { addMeal, initialPlanState, togglePlanPantry, withPlanBudgetInput, type PlanState } from "./planModel";
import { INGREDIENTS, PANTRY_IDS, RECIPES, RECIPE_ORDER } from "./prototypeData";

vi.mock("../proposalApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../proposalApi")>()),
  fetchProposal: vi.fn(),
  applyProposal: vi.fn(),
  discardProposal: vi.fn(),
}));

const ID = "3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b";
const REVISION = "9a1b2c3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d";

function proposal(preview: ProposalPreview, status: Proposal["status"] = "pending"): Proposal {
  return {
    id: ID,
    status,
    base_plan_revision_id: REVISION,
    preview,
    applied_plan_revision_id: status === "applied" ? REVISION : null,
  };
}

function previewOf(state: PlanState, overrides: Partial<ProposalPreview> = {}): ProposalPreview {
  return {
    meals: state.meals.map((m) => ({ recipe_id: m.recipeId, servings: m.servings })),
    pantry_ingredient_ids: [...state.pantry],
    plan_cap_cents: state.budgetCents,
    ...overrides,
  };
}

const state = initialPlanState();
const first = state.meals[0];
const other = RECIPE_ORDER.find((id) => id !== first.recipeId) ?? "";

beforeEach(() => {
  seedTestSession();
  for (const storage of [window.localStorage, window.sessionStorage]) {
    vi.spyOn(storage, "setItem");
    vi.spyOn(storage, "getItem");
    vi.spyOn(storage, "removeItem");
    vi.spyOn(storage, "clear");
  }
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
  clearTestSession();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("describeChange", () => {
  it("states meal and pantry changes without advertising the inherited cap", () => {
    const pantryId = state.pantry[0];
    const lines = describeChange(
      state,
      previewOf(state, {
        meals: [
          { recipe_id: first.recipeId, servings: 4 },
          { recipe_id: other, servings: 1 },
        ],
        pantry_ingredient_ids: state.pantry.slice(1),
        plan_cap_cents: 9000,
      }),
    );
    expect(lines).toContain(`${RECIPES[first.recipeId].name}: ${String(first.servings)} to 4 servings`);
    expect(lines).toContain(`Add ${RECIPES[other].name}, 1 serving`);
    expect(lines).toContain(`Remove ${INGREDIENTS[pantryId].name} from your pantry`);
    expect(lines.some((line) => line.includes("Plan cap"))).toBe(false);
    const removed = describeChange(state, previewOf(state, { meals: [] }));
    expect(removed).toEqual([`Remove ${RECIPES[first.recipeId].name}`]);
  });

  it("states a pantry add and ignores a null cap", () => {
    const missing = PANTRY_IDS.find((id) => !state.pantry.includes(id)) ?? "";
    const lines = describeChange(
      state,
      previewOf(state, {
        pantry_ingredient_ids: [...state.pantry, missing],
        plan_cap_cents: null,
      }),
    );
    expect(lines).toEqual([`Add ${INGREDIENTS[missing].name} to your pantry`]);
  });

  it("reports no change when only the inherited cap differs", () => {
    expect(describeChange(state, previewOf(state, { plan_cap_cents: 9000 }))).toEqual([]);
  });
});

describe("ProposalCard", () => {
  const onApplied = vi.fn();
  const changed = previewOf(state, { meals: [{ recipe_id: first.recipeId, servings: 4 }] });

  it("sends the budget edited before Apply through the real API", async () => {
    const actual = await vi.importActual<typeof import("../proposalApi")>("../proposalApi");
    vi.mocked(api.fetchProposal).mockImplementation(actual.fetchProposal);
    vi.mocked(api.applyProposal).mockImplementation(actual.applyProposal);
    const committed = previewOf(state, { meals: [{ recipe_id: other, servings: 2 }], plan_cap_cents: 1702 });
    const request = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(proposal(changed)), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ plan_revision_id: REVISION, snapshot: committed }), { status: 200 }));
    vi.stubGlobal("fetch", request);
    const { rerender } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    await screen.findByRole("button", { name: "Apply" });
    const edited = withPlanBudgetInput(state, "17.02");
    rerender(<ProposalCard proposalId={ID} state={edited} onApplied={onApplied} />);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(request).toHaveBeenNthCalledWith(1, `/api/grocery/proposals/${ID}`, {
      method: "GET",
      signal: expect.any(AbortSignal),
      headers: new Headers({ "X-FEWIA-Workspace": TEST_SESSION.workspace_id }),
      credentials: "same-origin",
      redirect: "error",
    });
    expect(request).toHaveBeenNthCalledWith(2, `/api/grocery/proposals/${ID}/apply`, {
      method: "POST",
      signal: expect.any(AbortSignal),
      headers: new Headers({
        "Content-Type": "application/json",
        "X-FEWIA-Workspace": TEST_SESSION.workspace_id,
      }),
      body: JSON.stringify({ plan_cap_cents: 1702 }),
      credentials: "same-origin",
      redirect: "error",
    });
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(onApplied).toHaveBeenCalledWith(committed);
  });

  it("does not read back or apply a snapshot after Apply returns 401", async () => {
    const actual = await vi.importActual<typeof import("../proposalApi")>("../proposalApi");
    vi.mocked(api.fetchProposal).mockImplementation(actual.fetchProposal);
    vi.mocked(api.applyProposal).mockImplementation(actual.applyProposal);
    const request = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(proposal(changed)), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockRejectedValue(new Error("Unexpected readback"));
    vi.stubGlobal("fetch", request);
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    const apply = await screen.findByRole("button", { name: "Apply" });
    await act(async () => {
      fireEvent.click(apply);
      await expect(vi.mocked(api.applyProposal).mock.results[0].value).rejects.toThrow();
    });
    expect(api.applyProposal).toHaveBeenCalledTimes(1);
    expect(api.fetchProposal).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledTimes(2);
    expect(onApplied).not.toHaveBeenCalled();
    expect(screen.queryByText(APPLIED_LINE)).toBeNull();
  });

  it("blocks Apply for an invalid budget draft and keeps Discard available", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    const invalid = withPlanBudgetInput(state, "invalid");
    render(<ProposalCard proposalId={ID} state={invalid} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    expect(screen.getByText("Enter a valid budget before applying this change.")).toBeTruthy();
    expect(api.applyProposal).not.toHaveBeenCalled();
    expect(api.fetchProposal).toHaveBeenCalledTimes(1);
    expect(onApplied).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Discard" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows exact rejected budget amounts and keeps retry and Discard available", async () => {
    const actual = await vi.importActual<typeof import("../proposalApi")>("../proposalApi");
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockImplementation(actual.applyProposal);
    vi.mocked(api.discardProposal).mockResolvedValue(undefined);
    const request = vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      detail: {
        code: "proposal_constraints", reason: "over_budget",
        total_cents: 1703, available_cents: 1702, message: "private server text",
      },
    }), { status: 409 })));
    vi.stubGlobal("fetch", request);
    const original = structuredClone(state);
    const { container } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    const message = "The proposed plan estimate is $17.03, above your available $17.02. Your plan did not change.";
    await screen.findByText((text) => text.startsWith(message));
    expect(container.querySelector("p[aria-live='polite']")?.textContent).toContain(message);
    const card = container.querySelector(".tonight-proposal");
    expect(card?.querySelectorAll("p[aria-live='polite']").length).toBe(1);
    expect(card?.children[1]).toBe(card?.querySelector("p[aria-live='polite']"));
    expect(card?.children[2]).toBe(card?.querySelector(".tonight-proposal-actions"));
    expect(screen.queryByText(/private server text/)).toBeNull();
    expect(screen.getByText(/to 4 servings/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Apply" }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: "Discard" }) as HTMLButtonElement).disabled).toBe(false);
    expect(api.fetchProposal).toHaveBeenCalledTimes(1);
    expect(onApplied).not.toHaveBeenCalled();
    expect(state).toEqual(original);

    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await screen.findByText((text) => text.startsWith(message));
    expect(request).toHaveBeenCalledTimes(2);
    expect(api.fetchProposal).toHaveBeenCalledTimes(1);
    expect(onApplied).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    await screen.findByText(DISCARDED_LINE);
    expect(api.discardProposal).toHaveBeenCalledTimes(1);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it.each([
    ["over_budget", { total_cents: "1703", available_cents: 1702 }, "The proposed plan exceeds your available budget."],
    ["over_budget", {}, "The proposed plan exceeds your available budget."],
    ["over_budget", { total_cents: 1702, available_cents: 1703 }, "The proposed plan exceeds your available budget."],
    ["diet_conflict", {}, "The proposed plan conflicts with your diet."],
    ["exclusion_conflict", {}, "The proposed plan includes an excluded ingredient."],
    ["estimate_unavailable", {}, "The proposed plan estimate is unavailable."],
  ] as const)("shows a static %s rejection without a refetch", async (reason, amounts, message) => {
    const actual = await vi.importActual<typeof import("../proposalApi")>("../proposalApi");
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockImplementation(actual.applyProposal);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      detail: { code: "proposal_constraints", reason, ...amounts, message: "private server text" },
    }), { status: 409 }))));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(`${message} Your plan did not change.`);
    expect(screen.queryByText(/private server text|\$/)).toBeNull();
    expect(api.fetchProposal).toHaveBeenCalledTimes(1);
    expect(onApplied).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Apply" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
  });

  it("shows a loading line, then the change with Apply and Discard", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    const { container } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    expect(container.querySelector("p[aria-live='polite']")?.textContent).toMatch(/Loading/);
    expect(container.querySelector("[role='status']")).toBeNull();
    await screen.findByRole("button", { name: "Apply" });
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
    expect(screen.getByText(/to 4 servings/)).toBeTruthy();
  });

  it("Apply calls onApplied with the committed server snapshot", async () => {
    const committed = previewOf(state, {
      meals: [{ recipe_id: other, servings: 3 }],
      pantry_ingredient_ids: [],
      plan_cap_cents: 1702,
    });
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockResolvedValue({ plan_revision_id: REVISION, snapshot: committed });
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(onApplied).toHaveBeenCalledWith(committed);
    expect(onApplied).not.toHaveBeenCalledWith(changed);
    expect(api.applyProposal).toHaveBeenCalledWith(ID, expect.any(AbortSignal), state.budgetCents);
    expect(screen.queryByRole("button", { name: "Apply" })).toBeNull();
  });

  it("treats a lost response as applied when the refetch says applied", async () => {
    const committed = previewOf(state, { meals: [{ recipe_id: other, servings: 2 }], plan_cap_cents: 1702 });
    vi.mocked(api.fetchProposal)
      .mockResolvedValueOnce(proposal(changed))
      .mockResolvedValueOnce(proposal(committed, "applied"));
    vi.mocked(api.applyProposal).mockRejectedValue(new Error("network"));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(onApplied).toHaveBeenCalledWith(committed);
    expect(onApplied).not.toHaveBeenCalledWith(changed);
  });

  it("treats a 409 on an already-applied proposal as applied", async () => {
    const committed = previewOf(state, { meals: [{ recipe_id: other, servings: 1 }], pantry_ingredient_ids: [] });
    vi.mocked(api.fetchProposal)
      .mockResolvedValueOnce(proposal(changed))
      .mockResolvedValueOnce(proposal(committed, "applied"));
    vi.mocked(api.applyProposal).mockRejectedValue(new ProposalConflict());
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(onApplied).toHaveBeenCalledWith(committed);
    expect(onApplied).not.toHaveBeenCalledWith(changed);
  });

  it("offers a retry when the refetch says pending", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockRejectedValue(new Error("x"));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(ACTION_ERROR_LINE);
    expect((screen.getByRole("button", { name: "Apply" }) as HTMLButtonElement).disabled).toBe(false);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it.each([undefined, { meals: [] }])("keeps the plan when Apply returns an invalid snapshot: %j", async (snapshot) => {
    const actual = await vi.importActual<typeof import("../proposalApi")>("../proposalApi");
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockImplementation(actual.applyProposal);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      plan_revision_id: REVISION, snapshot,
    }), { status: 200 }))));
    const original = structuredClone(state);
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(ACTION_ERROR_LINE);
    expect(api.fetchProposal).toHaveBeenCalledTimes(2);
    expect(onApplied).not.toHaveBeenCalled();
    expect(state).toEqual(original);
  });

  it("says it cannot confirm when the refetch fails or says discarded", async () => {
    vi.mocked(api.fetchProposal)
      .mockResolvedValueOnce(proposal(changed))
      .mockRejectedValueOnce(new Error("down"));
    vi.mocked(api.applyProposal).mockRejectedValue(new ProposalConflict());
    const { unmount } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(UNCONFIRMED_LINE);
    expect(screen.queryByRole("button")).toBeNull();
    unmount();
    vi.mocked(api.fetchProposal)
      .mockResolvedValueOnce(proposal(changed))
      .mockResolvedValueOnce(proposal(changed, "discarded"));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(UNCONFIRMED_LINE);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("does not abort an in-flight Apply on unmount and ignores its result", async () => {
    let seen: AbortSignal | undefined;
    let finish: (result: AppliedProposal) => void = () => undefined;
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockImplementation((_id, signal) => {
      seen = signal;
      return new Promise<AppliedProposal>((resolve) => {
        finish = resolve;
      });
    });
    const { unmount } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    unmount();
    expect(seen?.aborted).toBe(false);
    finish({ plan_revision_id: REVISION, snapshot: changed });
    await Promise.resolve();
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("Discard says Discarded and does not change the plan", async () => {
    const actual = await vi.importActual<typeof import("../proposalApi")>("../proposalApi");
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.discardProposal).mockImplementation(actual.discardProposal);
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "discarded" }), { status: 200 }));
    vi.stubGlobal("fetch", request);
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    await screen.findByText(DISCARDED_LINE);
    expect(request).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith(`/api/grocery/proposals/${ID}/discard`, {
      method: "POST",
      signal: expect.any(AbortSignal),
      headers: new Headers({
        "Content-Type": "application/json",
        "X-FEWIA-Workspace": TEST_SESSION.workspace_id,
      }),
      body: JSON.stringify({ confirm: true }),
      credentials: "same-origin",
      redirect: "error",
    });
    expect(onApplied).not.toHaveBeenCalled();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it.each([
    ["applied", APPLIED_LINE],
    ["discarded", DISCARDED_LINE],
  ] as const)("shows %s on load with no buttons", async (status, line) => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed, status));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    await screen.findByText(line);
    expect(screen.queryByRole("button")).toBeNull();
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("shows a load error", async () => {
    vi.mocked(api.fetchProposal).mockRejectedValue(new Error("x"));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    await screen.findByText(LOAD_ERROR_LINE);
  });

  it("aborts the fetch on unmount", async () => {
    let seen: AbortSignal | undefined;
    vi.mocked(api.fetchProposal).mockImplementation((_id, signal) => {
      seen = signal;
      return new Promise<Proposal>(() => undefined);
    });
    const { unmount } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    await waitFor(() => {
      expect(seen).toBeDefined();
    });
    expect(seen?.aborted).toBe(false);
    unmount();
    expect(seen?.aborted).toBe(true);
  });

  it("does not touch browser storage", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockResolvedValue({ plan_revision_id: REVISION, snapshot: changed });
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    for (const storage of [window.localStorage, window.sessionStorage]) {
      expect(storage.setItem).not.toHaveBeenCalled();
      expect(storage.getItem).not.toHaveBeenCalled();
      expect(storage.removeItem).not.toHaveBeenCalled();
      expect(storage.clear).not.toHaveBeenCalled();
    }
  });

  it("uses the current plan for the diff", async () => {
    const richer = togglePlanPantry(addMeal(state, other, 2), state.pantry[0]);
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(previewOf(state)));
    render(<ProposalCard proposalId={ID} state={richer} onApplied={onApplied} />);
    await screen.findByText(`Remove ${RECIPES[other].name}`);
  });
});
