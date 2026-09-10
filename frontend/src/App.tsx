import { SAMPLE_ESTIMATE_NOTICE } from "./apiTypes";
import { BudgetForm } from "./BudgetForm";
import { ChatWorkspace, useChatWorkspace } from "./ChatWorkspace";
import { Conversation } from "./Conversation";
import { Estimate } from "./Estimate";
import { formatDollars } from "./money";
import { useGroceryDemo } from "./useGroceryDemo";
import "./form.css";
import "./estimate.css";
import "./chat.css";

const CATALOG_LOADING = "Loading the grocery catalog.";

function sourceLabel(source: string): string {
  if (source === "fixture") {
    return "Demo spending";
  }
  return "Unverified spending source";
}

export default function App(): JSX.Element {
  const demo = useGroceryDemo();
  const chat = useChatWorkspace({
    form: demo.form,
    setForm: demo.setForm,
    formJob: demo.job,
    formDirty: demo.dirty,
  });
  const blocked = demo.config === null || demo.configPending || demo.configError !== null;
  const busy = demo.pending || chat.pending;
  const estimateJob = chat.estimateJob ?? demo.job;
  const estimateDirty = chat.estimateJob !== null ? chat.estimateDirty : demo.dirty;
  const showNotice = estimateJob?.status !== "succeeded" || estimateJob.result === null;
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
                  {`Source ${sourceLabel(demo.config.source)}. Pending ${formatDollars(demo.config.pending_cents)}`}
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
              onPantryToggle={demo.togglePantry}
              onRebuild={demo.submitForm}
              rebuildDisabled={blocked || busy}
            />
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
