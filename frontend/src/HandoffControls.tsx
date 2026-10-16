import { useEffect, useRef, useState, type JSX } from "react";
import { HandoffConsent } from "./HandoffConsent";
import { isSafeHandoffUrl, type HandoffView } from "./handoffTypes";

export type HandoffControlsProps = {
  view: HandoffView | null;
  error: string | null;
  pending: boolean;
  canStart: boolean;
  onStart: () => void;
  onRetry: () => void;
};

const IN_PROGRESS = "The shopping link request is in progress.";
const UNCERTAIN = "The shopping link is uncertain. Retry only if you choose to.";
const FAILED = "The shopping link request failed.";
const PREPARED = "The shopping list is ready.";

function stateStatus(state: HandoffView["state"]): string | null {
  if (state === "prepared") {
    return PREPARED;
  }
  if (state === "dispatching") {
    return IN_PROGRESS;
  }
  if (state === "failed") {
    return FAILED;
  }
  if (state === "uncertain") {
    return UNCERTAIN;
  }
  return null;
}

export function HandoffControls({
  view,
  error,
  pending,
  canStart,
  onStart,
  onRetry,
}: HandoffControlsProps): JSX.Element {
  const [consentOpen, setConsentOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const confirmedRef = useRef(false);
  useEffect(() => {
    if (!consentOpen && confirmedRef.current) {
      confirmedRef.current = false;
      headingRef.current?.focus();
    }
  }, [consentOpen]);
  useEffect(() => {
    if (!canStart || pending || view !== null) {
      setConsentOpen(false);
    }
  }, [canStart, pending, view]);
  const linkHref =
    view !== null &&
    view.state === "succeeded" &&
    view.retry_allowed === false &&
    isSafeHandoffUrl(view.url)
      ? view.url
      : null;
  const status = pending ? IN_PROGRESS : view === null ? null : stateStatus(view.state);
  return (
    <section className="handoff-controls" aria-labelledby="handoff-heading">
      <h2 id="handoff-heading" ref={headingRef} tabIndex={-1}>
        Shopping list
      </h2>
      {view === null && canStart ? (
        <button
          ref={triggerRef}
          type="button"
          className="rebuild-estimate"
          aria-haspopup="dialog"
          disabled={pending}
          onClick={() => {
            triggerRef.current?.focus();
            setConsentOpen(true);
          }}
        >
          Create shopping list
        </button>
      ) : null}
      {consentOpen && canStart && !pending && view === null ? (
        <HandoffConsent
          onCancel={() => setConsentOpen(false)}
          onConfirm={() => {
            if (canStart && !pending && view === null) {
              confirmedRef.current = true;
              onStart();
            }
          }}
        />
      ) : null}
      {view !== null && view.retry_allowed ? (
        <button
          type="button"
          className="rebuild-estimate"
          disabled={pending}
          onClick={() => {
            onRetry();
          }}
        >
          Retry shopping list
        </button>
      ) : null}
      {linkHref !== null ? (
        <a className="handoff-link" href={linkHref} rel="noopener noreferrer" target="_blank">
          Open shopping list
        </a>
      ) : null}
      {status !== null ? (
        <p className="estimate-status" role="status" aria-live="polite">
          {status}
        </p>
      ) : null}
      {!pending && error !== null ? (
        <p className="form-error" role="status">
          {error}
        </p>
      ) : null}
    </section>
  );
}
