import type { JSX, ReactNode } from "react";
import type { CatalogItem, GroceryJob } from "./apiTypes";
import { exclusionMessage } from "./exclusionMessage";

export type ExampleKind = "beans" | "vegan";

export type ConversationProps = {
  job: GroceryJob | null;
  error: string | null;
  pending: boolean;
  freshRequestsDisabled?: boolean;
  recipes?: CatalogItem[];
  ingredients?: CatalogItem[];
  onExample: (kind: ExampleKind) => void;
  onRetry: () => void;
  onNewRequest: () => void;
  children?: ReactNode;
};

function isNonterminal(job: GroceryJob | null): boolean {
  return job !== null && (job.status === "queued" || job.status === "running");
}

function successSummary(job: GroceryJob): string {
  const plan = job.result?.plan;
  const missingLineCost = plan !== undefined && plan.lines.some((line) => line.cost_cents === null);
  if (plan === undefined || plan.total_cents === null || missingLineCost) {
    return "The plan is incomplete.";
  }
  if (plan.accepted) {
    return "The estimate is within the plan budget.";
  }
  return "The plan is over budget.";
}

function liveStatus(
  job: GroceryJob | null,
  pending: boolean,
  recipes: CatalogItem[],
  ingredients: CatalogItem[],
): string | null {
  if (pending && job === null) {
    return "Submitting your grocery request.";
  }
  if (job?.status === "queued") {
    return "Your grocery request is queued.";
  }
  if (job?.status === "running") {
    return "Your grocery request is running.";
  }
  if (job?.status === "succeeded") {
    return successSummary(job);
  }
  if (job?.status === "failed") {
    return (
      exclusionMessage(job, recipes, ingredients) ??
      "The grocery request failed. Check meals, servings, and budget, then retry."
    );
  }
  return null;
}

export function Conversation({
  job,
  error,
  pending,
  freshRequestsDisabled = false,
  recipes = [],
  ingredients = [],
  onExample,
  onRetry,
  onNewRequest,
  children,
}: ConversationProps): JSX.Element {
  const status = liveStatus(job, pending, recipes, ingredients);
  const namedExclusion = exclusionMessage(job, recipes, ingredients);
  const showAction = error !== null || job?.status === "failed";
  const failed = job?.status === "failed";
  const examplesDisabled = pending || freshRequestsDisabled;
  const actionLabel = isNonterminal(job)
    ? "Check progress"
    : failed
      ? "Start a new request"
      : "Retry request";
  const onAction = failed ? onNewRequest : onRetry;
  const actionDisabled = pending || (failed && freshRequestsDisabled);
  return (
    <section className="panel conversation-panel" aria-labelledby="conversation-heading">
      <h2 id="conversation-heading">Your conversation</h2>
      <p className="conversation-welcome">
        Use the meal controls to choose 1 to 3 meals and 1 to 8 servings. Sample estimates use the demo
        price catalog.
      </p>
      <div className="conversation-examples">
        <button
          type="button"
          className="conversation-example"
          disabled={examplesDisabled}
          onClick={() => {
            onExample("beans");
          }}
        >
          Bean tacos for two
        </button>
        <button
          type="button"
          className="conversation-example"
          disabled={examplesDisabled}
          onClick={() => {
            onExample("vegan");
          }}
        >
          Three vegan dinners (2 servings each)
        </button>
      </div>
      {status !== null && error === null ? (
        <p className="conversation-status">{status}</p>
      ) : null}
      {error !== null ? (
        <p className="conversation-error" role="status">
          {namedExclusion ?? error}
        </p>
      ) : null}
      {showAction ? (
        <button type="button" className="conversation-action" disabled={actionDisabled} onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
      <div className="conversation-composer">{children}</div>
    </section>
  );
}
