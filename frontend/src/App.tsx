import { useEffect, type JSX } from "react";
import { SAMPLE_ESTIMATE_NOTICE, sourceLabel } from "./apiTypes";
import { BudgetForm } from "./BudgetForm";
import { ChatWorkspace, useChatWorkspace } from "./ChatWorkspace";
import { Conversation } from "./Conversation";
import { Estimate } from "./Estimate";
import { HandoffControls } from "./HandoffControls";
import { formatDollars } from "./money";
import { useGroceryDemo } from "./useGroceryDemo";
import { useHandoff } from "./useHandoff";
import "./form.css";
import "./estimate.css";
import "./chat.css";

const CATALOG_LOADING = "Loading the grocery catalog.";

export default function App(): JSX.Element {
  const demo = useGroceryDemo();
  const chat = useChatWorkspace({
    form: demo.form,
    setForm: demo.setForm,
    formJob: demo.job,
    formDirty: demo.dirty,
    formPending: demo.pending,
  });
  const handoff = useHandoff();
  const blocked = demo.config === null || demo.configPending || demo.configError !== null;
  const busy = demo.pending || chat.pending;
  const estimateJob = chat.estimateJob ?? demo.job;
  const estimateDirty =
    (chat.estimateJob !== null ? chat.estimateDirty : demo.dirty) || chat.unresolvedChatEstimate;
  const showNotice = estimateJob?.status !== "succeeded" || estimateJob.result === null;
  const jobId = estimateJob?.status === "succeeded" ? estimateJob.id : null;
  const result = estimateJob?.status === "succeeded" ? estimateJob.result : null;
  const canStart =
    chat.instacartConfigured &&
    !estimateDirty &&
    !busy &&
    jobId !== null &&
    result !== null &&
    result.plan.accepted &&
    result.plan.total_cents !== null &&
    result.plan.lines.some((line) => !line.from_pantry);
  useEffect(() => {
    handoff.clear();
    // handoff.clear is stable via useCallback; the handoff object itself is
    // recreated every render, and depending on it would re-run this effect
    // on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, estimateDirty, handoff.clear]);
  return (
    <div className="app-shell">
      <header className="site-header">
        <span className="wordmark">FEWIA</span>
        <span className="mode-label">Local demo · Sample prices</span>
      </header>
      <main className="page">
        <div className="intro">
          <h1>Meals that fit your budget</h1>
          <p>Plan a few meals with what you have.</p>
        </div>
        <div className="workspace">
          <Conversation
            job={demo.job}
            error={demo.error}
            pending={busy}
            freshRequestsDisabled={blocked || chat.pending}
            recipes={demo.config?.recipes ?? []}
            ingredients={demo.config?.ingredients ?? []}
            onExample={demo.example}
            onRetry={demo.retry}
            onNewRequest={demo.newRequest}
          >
            {demo.configError !== null ? (
              <div className="catalog-banner">
                <p className="catalog-error" role="status" aria-live="polite">
                  {demo.configError}
                </p>
                <button type="button" className="retry-catalog" onClick={demo.reloadConfig}>
                  Retry catalog
                </button>
              </div>
            ) : demo.configPending || demo.config === null ? (
              <p className="catalog-status" role="status" aria-live="polite">
                {CATALOG_LOADING}
              </p>
            ) : null}
            {demo.config !== null ? (
              <form
                className="budget-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void demo.submitForm();
                }}
              >
                <p className="budget-source">
                  {demo.config.source === "manual"
                    ? `Source ${sourceLabel(demo.config.source)}.`
                    : `Source ${sourceLabel(demo.config.source)}. Pending ${formatDollars(demo.config.pending_cents)}`}
                </p>
                <BudgetForm
                  config={demo.config}
                  value={demo.form}
                  onChange={demo.setForm}
                  disabled={blocked || busy}
                />
                {demo.formError !== null ? (
                  <p className="form-error" role="alert">
                    {demo.formError}
                  </p>
                ) : null}
                <button type="submit" className="build-estimate" disabled={blocked || busy}>
                  Build my estimate
                </button>
              </form>
            ) : null}
          </Conversation>
          <ChatWorkspace
            formPending={demo.pending}
            configured={chat.configured}
            configurationPending={chat.configurationPending}
            providerError={chat.providerError}
            retryProviders={chat.retryProviders}
            conversation={chat.conversation}
            freshSendBlocked={chat.needsRebuild}
            freshSendDisabled={blocked}
          />
          <div className="panel budget-panel">
            <Estimate
              job={estimateJob}
              pending={busy}
              dirty={estimateDirty}
              pantry={demo.form.pantry}
              recipes={demo.config?.recipes ?? []}
              ingredients={demo.config?.ingredients ?? []}
              onPantryToggle={demo.togglePantry}
              onRebuild={demo.submitForm}
              rebuildDisabled={blocked || busy}
            />
            {chat.instacartConfigured || handoff.view !== null ? (
              <HandoffControls
                view={handoff.view}
                error={handoff.error}
                pending={handoff.pending}
                canStart={canStart}
                onStart={() => {
                  if (typeof jobId === "string") {
                    void handoff.start(jobId);
                  }
                }}
                onRetry={() => {
                  void handoff.retry();
                }}
              />
            ) : null}
            {showNotice ? (
              <p className="estimate-notice">{demo.config?.notice ?? SAMPLE_ESTIMATE_NOTICE}</p>
            ) : null}
          </div>
        </div>
      </main>
      <footer className="site-footer">No purchases are made here.</footer>
    </div>
  );
}
