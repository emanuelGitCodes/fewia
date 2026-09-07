function Conversation() {
  return (
    <section className="panel conversation-panel" aria-labelledby="conversation-heading">
      <h2 id="conversation-heading">Your conversation</h2>
      <div className="conversation-empty" role="status" aria-live="polite">
        <p className="empty-title">Start with your meal ideas.</p>
        <p>Nothing is estimated yet. Your request and FEWIA&apos;s status updates will appear here when chat is connected.</p>
      </div>
    </section>
  );
}
function BudgetPanel() {
  return (
    <section className="panel budget-panel" aria-labelledby="budget-heading">
      <h2 id="budget-heading">Your grocery budget</h2>
      <p className="panel-note" role="status" aria-live="polite">No grocery budget or meal plan is set yet.</p>
      <div className="budget-empty">
        <p>Budget, meal plan, pantry, evidence, and Instacart development links will appear after a request completes.</p>
        <p className="estimate-notice">Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.</p>
      </div>
    </section>
  );
}
export default function App() {
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
          <Conversation />
          <BudgetPanel />
        </div>
      </main>
      <footer className="site-footer">No purchases are made here.</footer>
    </div>
  );
}
