import { IN_PROGRESS, useSupermarketEstimate } from "./useSupermarketEstimate";
import { formatDollars } from "./money";

export type SupermarketEstimateProps = { jobId: string };

export function SupermarketEstimate({ jobId }: SupermarketEstimateProps): JSX.Element {
  const { overlay, error, pending, lookup } = useSupermarketEstimate(jobId);
  const status = pending ? IN_PROGRESS : error;
  return (
    <section className="supermarket-estimate" aria-labelledby="supermarket-estimate-heading">
      <h3 id="supermarket-estimate-heading">Spoonacular estimate</h3>
      <button type="button" className="rebuild-estimate" disabled={pending} onClick={lookup}>
        Check supermarket estimate
      </button>
      {status !== null ? (
        <p className="estimate-status" role="status" aria-live="polite">
          {status}
        </p>
      ) : null}
      {overlay !== null && !pending ? (
        <>
          <p className="estimate-overlay-total" role="status" aria-live="polite">
            {formatDollars(overlay.total_cents)}
          </p>
          <p className="estimate-notice">{overlay.notice}</p>
        </>
      ) : null}
    </section>
  );
}
