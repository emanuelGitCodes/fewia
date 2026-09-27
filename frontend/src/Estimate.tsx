import { sourceLabel, type GroceryJob, type GroceryJobResult, type PlanLine } from "./apiTypes";
import { formatDollars } from "./money";

export type EstimateProps = {
  job: GroceryJob | null;
  pending: boolean;
  dirty: boolean;
  pantry: string[];
  onPantryToggle: (id: string) => void;
  onRebuild?: () => void | Promise<void>;
  rebuildDisabled?: boolean;
};

function isIncomplete(result: GroceryJobResult): boolean {
  return result.plan.total_cents === null || result.plan.lines.some((line) => line.cost_cents === null);
}

function planWording(result: GroceryJobResult): string {
  if (isIncomplete(result)) {
    return "This plan is incomplete.";
  }
  if (result.plan.accepted) {
    return "This estimate is within the plan budget.";
  }
  return "This plan is over budget.";
}

function statusText(job: GroceryJob | null, pending: boolean): string {
  if (job?.status === "queued") {
    return "The grocery request is queued.";
  }
  if (job?.status === "running") {
    return "The grocery request is running.";
  }
  if (pending) {
    return "The grocery request is in progress.";
  }
  if (job?.status === "failed") {
    return "The grocery request failed.";
  }
  return "No grocery budget or meal plan is set yet.";
}

function LineRow(props: {
  line: PlanLine;
  pantry: string[];
  pending: boolean;
  onPantryToggle: (id: string) => void;
}): JSX.Element {
  const { line, pantry, pending, onPantryToggle } = props;
  const inputId = `pantry-${line.ingredient_id}`;
  return (
    <li className="estimate-line">
      <p className="estimate-line-name">{line.name}</p>
      <p className="estimate-line-need">{`Needed ${line.quantity} ${line.unit}`}</p>
      <p className="estimate-line-packages">{`${line.packages} ${line.packages === 1 ? "package" : "packages"}`}</p>
      <p className="estimate-line-cost">{formatDollars(line.cost_cents)}</p>
      <label className="estimate-pantry" htmlFor={inputId}>
        <input
          id={inputId}
          type="checkbox"
          checked={pantry.includes(line.ingredient_id)}
          disabled={pending}
          onChange={() => {
            onPantryToggle(line.ingredient_id);
          }}
        />
        {`I have ${line.name}`}
      </label>
    </li>
  );
}

export function Estimate({
  job,
  pending,
  dirty,
  pantry,
  onPantryToggle,
  onRebuild,
  rebuildDisabled = false,
}: EstimateProps): JSX.Element {
  const result = job?.status === "succeeded" ? job.result : null;
  if (result === null) {
    return (
      <section className="estimate-panel" aria-labelledby="estimate-heading">
        <h2 id="estimate-heading">Grocery estimate</h2>
        <p className="estimate-status" role="status" aria-live="polite">
          {statusText(job, pending)}
        </p>
      </section>
    );
  }
  const warnings = [...new Set([...result.plan.warnings, ...result.budget.warnings])];
  return (
    <section className="estimate-panel" aria-labelledby="estimate-heading">
      <h2 id="estimate-heading">{dirty ? "Previous estimate" : "Grocery estimate"}</h2>
      {dirty ? (
        <p className="estimate-dirty" role="status">
          Rebuild the request to apply request changes.
        </p>
      ) : null}
      {dirty && onRebuild !== undefined ? (
        <button
          type="button"
          className="rebuild-estimate"
          disabled={rebuildDisabled}
          onClick={() => {
            void onRebuild();
          }}
        >
          Rebuild estimate
        </button>
      ) : null}
      <p className="estimate-plan-state" role="status" aria-live="polite">
        {planWording(result)}
      </p>
      <p className="estimate-total">{formatDollars(result.plan.total_cents)}</p>
      {result.supermarket_estimate !== undefined ? (
        <>
          <p className="estimate-overlay-label">Average supermarket estimate</p>
          <p className="estimate-overlay-total">
            {formatDollars(result.supermarket_estimate.total_cents)}
          </p>
          <p className="estimate-notice">{result.supermarket_estimate.notice}</p>
        </>
      ) : null}
      <p className="estimate-available">{`Available for this plan ${formatDollars(result.budget.available_cents)}`}</p>
      {result.spending_source === "manual" ? null : (
        <p className="estimate-pending">{`Pending ${formatDollars(result.budget.pending_cents)}`}</p>
      )}
      <p className="estimate-source">{`Source ${sourceLabel(result.spending_source)}`}</p>
      <ul className="estimate-lines">
        {result.plan.lines.map((line) => (
          <LineRow
            key={line.ingredient_id}
            line={line}
            pantry={pantry}
            pending={pending}
            onPantryToggle={onPantryToggle}
          />
        ))}
      </ul>
      {warnings.map((warning, index) => (
        <p key={`${index}-${warning}`} className="estimate-warning" role="status">
          {warning}
        </p>
      ))}
      <p className="estimate-notice">{result.plan.notice}</p>
    </section>
  );
}
