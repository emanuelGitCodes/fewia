import { useEffect, useRef, useState, type JSX } from "react";
import { isAbortError } from "../api";
import { formatDollars } from "../money";
import {
  ProposalConflict,
  applyProposal,
  discardProposal,
  fetchProposal,
  type ProposalPreview,
  type ProposalStatus,
} from "../proposalApi";
import type { PlanState } from "./planModel";
import { INGREDIENTS, RECIPES } from "./prototypeData";

export const APPLIED_LINE = "Applied to your plan.";
export const DISCARDED_LINE = "Discarded.";
export const CONFLICT_LINE = "This change no longer fits your plan.";
export const LOADING_LINE = "Loading the proposed change.";
export const LOAD_ERROR_LINE = "The proposed change could not be loaded.";
export const ACTION_ERROR_LINE = "FEWIA could not save that. Your plan did not change.";
export const NO_CHANGE_LINE = "No changes to your plan.";

function servingsText(servings: number): string {
  return `${String(servings)} ${servings === 1 ? "serving" : "servings"}`;
}

// The client states the change itself, from catalog names. Server text is never shown.
export function describeChange(state: PlanState, preview: ProposalPreview): string[] {
  const lines: string[] = [];
  const current = new Map(state.meals.map((meal) => [meal.recipeId, meal.servings]));
  const proposed = new Map(preview.meals.map((meal) => [meal.recipe_id, meal.servings]));
  for (const [id, servings] of proposed) {
    const before = current.get(id);
    if (before === undefined) {
      lines.push(`Add ${RECIPES[id].name}, ${servingsText(servings)}`);
    } else if (before !== servings) {
      lines.push(`${RECIPES[id].name}: ${String(before)} to ${servingsText(servings)}`);
    }
  }
  for (const id of current.keys()) {
    if (!proposed.has(id)) {
      lines.push(`Remove ${RECIPES[id].name}`);
    }
  }
  for (const id of preview.pantry_ingredient_ids) {
    if (!state.pantry.includes(id)) {
      lines.push(`Add ${INGREDIENTS[id].name} to your pantry`);
    }
  }
  for (const id of state.pantry) {
    if (Object.prototype.hasOwnProperty.call(INGREDIENTS, id) && !preview.pantry_ingredient_ids.includes(id)) {
      lines.push(`Remove ${INGREDIENTS[id].name} from your pantry`);
    }
  }
  const cap = preview.plan_cap_cents;
  if (cap !== null && cap !== state.budgetCents) {
    lines.push(`Plan cap: ${formatDollars(state.budgetCents)} to ${formatDollars(cap)}`);
  }
  return lines;
}

type Phase = "loading" | "error" | ProposalStatus;

export function ProposalCard(props: {
  proposalId: string;
  state: PlanState;
  onApplied: (snapshot: ProposalPreview) => void;
}): JSX.Element {
  const { proposalId, state, onApplied } = props;
  const [phase, setPhase] = useState<Phase>("loading");
  const [preview, setPreview] = useState<ProposalPreview | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    controller.current = ctl;
    setPhase("loading");
    fetchProposal(proposalId, ctl.signal).then(
      (proposal) => {
        setPreview(proposal.preview);
        setPhase(proposal.status);
      },
      (error: unknown) => {
        if (!isAbortError(error)) {
          setPhase("error");
        }
      },
    );
    return () => {
      ctl.abort();
    };
  }, [proposalId]);

  const run = (act: () => Promise<void>): void => {
    const signal = controller.current?.signal;
    if (busy || signal === undefined) {
      return;
    }
    setBusy(true);
    setNote("");
    act().then(
      () => {
        setBusy(false);
      },
      (error: unknown) => {
        if (isAbortError(error)) {
          return;
        }
        setBusy(false);
        setNote(error instanceof ProposalConflict ? CONFLICT_LINE : ACTION_ERROR_LINE);
      },
    );
  };
  const apply = (): void => {
    run(async () => {
      await applyProposal(proposalId, controller.current?.signal ?? new AbortController().signal);
      if (preview !== null) {
        onApplied(preview);
      }
      setPhase("applied");
    });
  };
  const discard = (): void => {
    run(async () => {
      await discardProposal(proposalId, controller.current?.signal ?? new AbortController().signal);
      setPhase("discarded");
    });
  };

  const changes = preview === null || phase !== "pending" ? [] : describeChange(state, preview);
  let message = note;
  if (phase === "loading") {
    message = LOADING_LINE;
  } else if (phase === "error") {
    message = LOAD_ERROR_LINE;
  } else if (phase === "applied") {
    message = APPLIED_LINE;
  } else if (phase === "discarded") {
    message = DISCARDED_LINE;
  }

  return (
    <section className="tonight-proposal" aria-label="Proposed plan change">
      {phase === "pending" ? (
        <>
          {changes.length > 0 ? (
            <ul className="tonight-proposal-changes" aria-label="Changes">
              {changes.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <p>{NO_CHANGE_LINE}</p>
          )}
          <div className="tonight-proposal-actions">
            <button type="button" className="tonight-ask-send" disabled={busy} onClick={apply}>
              Apply
            </button>
            <button type="button" className="tonight-ask-btn" disabled={busy} onClick={discard}>
              Discard
            </button>
          </div>
        </>
      ) : null}
      <p className="tonight-proposal-note" aria-live="polite">
        {message}
      </p>
    </section>
  );
}
