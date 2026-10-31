/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProposalConflict, type Proposal, type ProposalPreview } from "../proposalApi";
import * as api from "../proposalApi";
import {
  ACTION_ERROR_LINE,
  APPLIED_LINE,
  DISCARDED_LINE,
  LOAD_ERROR_LINE,
  ProposalCard,
  UNCONFIRMED_LINE,
  describeChange,
} from "./ProposalCard";
import { addMeal, initialPlanState, togglePlanPantry, type PlanState } from "./planModel";
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
  vi.spyOn(Storage.prototype, "setItem");
  vi.spyOn(Storage.prototype, "getItem");
  vi.spyOn(Storage.prototype, "removeItem");
  vi.spyOn(Storage.prototype, "clear");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
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

  it("shows a loading line, then the change with Apply and Discard", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    const { container } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    expect(container.querySelector("p[aria-live='polite']")?.textContent).toMatch(/Loading/);
    expect(container.querySelector("[role='status']")).toBeNull();
    await screen.findByRole("button", { name: "Apply" });
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
    expect(screen.getByText(/to 4 servings/)).toBeTruthy();
  });

  it("Apply calls onApplied with the preview and says so", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockResolvedValue(REVISION);
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(onApplied).toHaveBeenCalledWith(changed);
    expect(screen.queryByRole("button", { name: "Apply" })).toBeNull();
  });

  it("treats a lost response as applied when the refetch says applied", async () => {
    vi.mocked(api.fetchProposal)
      .mockResolvedValueOnce(proposal(changed))
      .mockResolvedValueOnce(proposal(changed, "applied"));
    vi.mocked(api.applyProposal).mockRejectedValue(new Error("network"));
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(onApplied).toHaveBeenCalledWith(changed);
  });

  it("treats a 409 on an already-applied proposal as applied", async () => {
    vi.mocked(api.fetchProposal)
      .mockResolvedValueOnce(proposal(changed))
      .mockResolvedValueOnce(proposal(changed, "applied"));
    vi.mocked(api.applyProposal).mockRejectedValue(new ProposalConflict());
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(onApplied).toHaveBeenCalledTimes(1);
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
    let finish: (id: string) => void = () => undefined;
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.applyProposal).mockImplementation((_id, signal) => {
      seen = signal;
      return new Promise<string>((resolve) => {
        finish = resolve;
      });
    });
    const { unmount } = render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    unmount();
    expect(seen?.aborted).toBe(false);
    finish(REVISION);
    await Promise.resolve();
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("Discard says Discarded and does not change the plan", async () => {
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(changed));
    vi.mocked(api.discardProposal).mockResolvedValue(undefined);
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    await screen.findByText(DISCARDED_LINE);
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
    vi.mocked(api.applyProposal).mockResolvedValue(REVISION);
    render(<ProposalCard proposalId={ID} state={state} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await screen.findByText(APPLIED_LINE);
    expect(Storage.prototype.setItem).not.toHaveBeenCalled();
    expect(Storage.prototype.getItem).not.toHaveBeenCalled();
    expect(Storage.prototype.removeItem).not.toHaveBeenCalled();
    expect(Storage.prototype.clear).not.toHaveBeenCalled();
  });

  it("uses the current plan for the diff", async () => {
    const richer = togglePlanPantry(addMeal(state, other, 2), state.pantry[0]);
    vi.mocked(api.fetchProposal).mockResolvedValue(proposal(previewOf(state)));
    render(<ProposalCard proposalId={ID} state={richer} onApplied={onApplied} />);
    await screen.findByText(`Remove ${RECIPES[other].name}`);
  });
});
