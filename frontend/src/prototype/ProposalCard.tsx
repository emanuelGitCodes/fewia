import { useEffect, useRef, useState, type JSX } from "react";
import { SAMPLE_ESTIMATE_NOTICE, captureSessionGuard, isAbortError } from "../api";
import { formatDollars } from "../money";
import {
  applyProposal,
  discardProposal,
  fetchProposal,
  ProposalConstraintsError,
  type ProposalPreview,
  type ProposalStatus,
} from "../proposalApi";
import type { PlanState } from "./planModel";
import { INGREDIENTS, RECIPES, isKnownIngredient } from "./prototypeData";

export const APPLIED_LINE = "Applied to your plan.";
export const DISCARDED_LINE = "Discarded.";
export const LOADING_LINE = "Loading the proposed change.";
export const LOAD_ERROR_LINE = "The proposed change could not be loaded.";
export const ACTION_ERROR_LINE = "FEWIA could not save that. Try again.";
export const DISCARD_ERROR_LINE = "FEWIA could not discard that. Try again.";
export const UNCONFIRMED_LINE = "FEWIA could not confirm the change. Refresh the page to see your plan.";
export const NO_CHANGE_LINE = "No changes to your plan.";

function constraintsMessage(error: ProposalConstraintsError): string {
  let reason: string;
  switch (error.reason) {
    case "over_budget":
      reason = error.amounts === null
        ? "The proposed plan exceeds your available budget."
        : `The proposed plan estimate is ${formatDollars(error.amounts.totalCents)}, above your available ${formatDollars(error.amounts.availableCents)}.`;
      break;
    case "diet_conflict":
      reason = "The proposed plan conflicts with your diet.";
      break;
    case "exclusion_conflict":
      reason = "The proposed plan includes an excluded ingredient.";
      break;
    case "estimate_unavailable":
      reason = "The proposed plan estimate is unavailable.";
      break;
  }
  const notice = error.reason === "over_budget" && error.amounts !== null
    ? ` ${SAMPLE_ESTIMATE_NOTICE}`
    : "";
  return `${reason} Your plan did not change.${notice}`;
}

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
    if (isKnownIngredient(id) && !preview.pantry_ingredient_ids.includes(id)) {
      lines.push(`Remove ${INGREDIENTS[id].name} from your pantry`);
    }
  }
  return lines;
}

type Phase = "loading" | "error" | "unconfirmed" | ProposalStatus;

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
  const mounted = useRef(true);
  const sessionGuard = useRef<(() => boolean) | null>(null);
  const actionInFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    const session = captureSessionGuard();
    sessionGuard.current = session;
    actionInFlight.current = false;
    controller.current = ctl;
    setPhase("loading");
    fetchProposal(proposalId, ctl.signal).then(
      (proposal) => {
        if (ctl.signal.aborted || !session()) return;
        setPreview(proposal.preview);
        setPhase(proposal.status);
      },
      (error: unknown) => {
        if (!ctl.signal.aborted && session() && !isAbortError(error)) {
          setPhase("error");
        }
      },
    );
    return () => {
      ctl.abort();
      if (sessionGuard.current === session) sessionGuard.current = null;
    };
  }, [proposalId]);

  // Apply is never aborted: once sent, the server may apply it even if this card unmounts.
  const apply = async (): Promise<void> => {
    const session = sessionGuard.current;
    if (busy || actionInFlight.current || preview === null || session === null || !session()) {
      return;
    }
    if (state.budgetError !== null) {
      setNote("Enter a valid budget before applying this change.");
      return;
    }
    let snapshot: ProposalPreview | null = null;
    actionInFlight.current = true;
    setBusy(true);
    setNote("");
    let outcome: ProposalStatus | "unknown";
    try {
      const applied = await applyProposal(proposalId, new AbortController().signal, state.budgetCents);
      snapshot = applied.snapshot;
      outcome = "applied";
    } catch (error: unknown) {
      if (!mounted.current || sessionGuard.current !== session || !session()) return;
      if (error instanceof ProposalConstraintsError) {
        actionInFlight.current = false;
        setBusy(false);
        setNote(constraintsMessage(error));
        return;
      }
      try {
        const proposal = await fetchProposal(proposalId, new AbortController().signal);
        outcome = proposal.status;
        if (proposal.status === "applied") {
          snapshot = proposal.preview;
        }
      } catch {
        outcome = "unknown";
      }
    }
    if (!mounted.current || sessionGuard.current !== session || !session()) {
      return;
    }
    actionInFlight.current = false;
    setBusy(false);
    if (outcome === "applied" && snapshot !== null) {
      onApplied(snapshot);
      setPhase("applied");
    } else if (outcome === "pending") {
      setNote(ACTION_ERROR_LINE);
    } else {
      setPhase("unconfirmed");
    }
  };
  const discard = (): void => {
    const signal = controller.current?.signal;
    const session = sessionGuard.current;
    if (busy || actionInFlight.current || signal === undefined || session === null || !session()) {
      return;
    }
    actionInFlight.current = true;
    setBusy(true);
    setNote("");
    discardProposal(proposalId, signal).then(
      () => {
        if (!mounted.current || sessionGuard.current !== session || !session()) return;
        actionInFlight.current = false;
        setBusy(false);
        setPhase("discarded");
      },
      (error: unknown) => {
        if (!mounted.current || sessionGuard.current !== session || !session()) return;
        if (!isAbortError(error)) {
          actionInFlight.current = false;
          setBusy(false);
          setNote(DISCARD_ERROR_LINE);
        }
      },
    );
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
  } else if (phase === "unconfirmed") {
    message = UNCONFIRMED_LINE;
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
        </>
      ) : null}
      <p className="tonight-proposal-note" aria-live="polite">
        {message}
      </p>
      {phase === "pending" ? (
        <div className="tonight-proposal-actions">
          <button type="button" className="tonight-ask-send" disabled={busy} onClick={() => void apply()}>
            Apply
          </button>
          <button type="button" className="tonight-ask-btn" disabled={busy} onClick={discard}>
            Discard
          </button>
        </div>
      ) : null}
    </section>
  );
}
