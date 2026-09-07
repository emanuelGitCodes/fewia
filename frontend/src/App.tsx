import { SAMPLE_ESTIMATE_NOTICE } from "./apiTypes";
import { BudgetForm } from "./BudgetForm";
import { Conversation } from "./Conversation";
import { Estimate } from "./Estimate";
import { formatDollars } from "./money";
import { useGroceryDemo } from "./useGroceryDemo";
import "./form.css";
import "./estimate.css";

const CATALOG_LOADING = "Loading the grocery catalog.";

function sourceLabel(source: string): string {
  if (source === "fixture") {
    return "Demo spending";
  }
  return "Unverified spending source";
}

export default function App(): JSX.Element {
  const demo = useGroceryDemo();
  const blocked = demo.config === null || demo.configPending || demo.configError !== null;
  const showNotice = demo.job?.status !== "succeeded" || demo.job.result === null;
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
            pending={demo.pending}
            freshRequestsDisabled={blocked}
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
                  disabled={blocked || demo.pending}
                />
                {demo.formError !== null ? (
                  <p className="form-error" role="alert">
                    {demo.formError}
                  </p>
                ) : null}
                <button type="submit" className="build-estimate" disabled={blocked || demo.pending}>
                  Build my estimate
                </button>
              </form>
            ) : null}
          </Conversation>
          <div className="panel budget-panel">
            <Estimate
              job={demo.job}
              pending={demo.pending}
              dirty={demo.dirty}
              pantry={demo.form.pantry}
              onPantryToggle={demo.togglePantry}
              onRebuild={demo.submitForm}
              rebuildDisabled={blocked || demo.pending}
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
