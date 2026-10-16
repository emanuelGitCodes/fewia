import { useEffect, useRef, useState, type JSX } from "react";
import { DEMO_NOTICE } from "./prototypeData";
import {
  addMeal,
  initialPlanState,
  planCost,
  planLines,
  removeMeal,
  shiftMealServings,
  togglePlanChecked,
  togglePlanPantry,
  withPlanBudgetInput,
  withPlanView,
  type PlanState,
} from "./planModel";
import {
  BudgetPanel,
  PantryPanel,
  PlanPanel,
  PrototypeNav,
  ShoppingPanel,
} from "./PrototypePanels";
import "./tonight.css";

export function TonightPrototype(): JSX.Element {
  const [state, setState] = useState<PlanState>(initialPlanState);
  const previousView = useRef(state.view);
  const canvasRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const lines = planLines(state);
  const costCents = planCost(lines);
  useEffect(() => {
    // Focus moves only when the view changes.
    if (previousView.current === state.view) {
      return;
    }
    previousView.current = state.view;
    const heading = mainRef.current?.querySelector("h1");
    if (heading instanceof HTMLElement) {
      heading.focus({ preventScroll: true });
    }
    const canvas = canvasRef.current;
    if (canvas !== null) {
      canvas.scrollTop = 0;
    }
    window.scrollTo(0, 0);
  }, [state.view]);
  return (
    <div className="tonight-prototype">
      <div className="tonight-canvas" ref={canvasRef}>
        <header className="tonight-header">
          <p className="tonight-wordmark">FEWIA</p>
          <p className="tonight-demo">{DEMO_NOTICE}</p>
        </header>
        <main ref={mainRef}>
          {state.view === "plan" ? (
            <PlanPanel
              state={state}
              lines={lines}
              onToggleMeal={(id, planned) => {
                setState((current) => (planned ? removeMeal(current, id) : addMeal(current, id)));
              }}
              onShiftServings={(id, delta) => {
                setState((current) => shiftMealServings(current, id, delta));
              }}
              onEditPantry={() => {
                setState((current) => withPlanView(current, "pantry"));
              }}
              onSeeShopping={() => {
                setState((current) => withPlanView(current, "shopping"));
              }}
            />
          ) : null}
          {state.view === "pantry" ? (
            <PantryPanel
              pantry={state.pantry}
              onToggle={(id) => {
                setState((current) => togglePlanPantry(current, id));
              }}
              onBack={() => {
                setState((current) => withPlanView(current, "plan"));
              }}
            />
          ) : null}
          {state.view === "shopping" ? (
            <ShoppingPanel
              lines={lines}
              checked={state.checked}
              onToggle={(id) => {
                setState((current) => togglePlanChecked(current, id));
              }}
              onBack={() => {
                setState((current) => withPlanView(current, "plan"));
              }}
            />
          ) : null}
          {state.view === "budget" ? (
            <BudgetPanel
              budgetInput={state.budgetInput}
              budgetCents={state.budgetCents}
              budgetError={state.budgetError}
              costCents={costCents}
              onChange={(value) => {
                setState((current) => withPlanBudgetInput(current, value));
              }}
            />
          ) : null}
        </main>
        <footer className="tonight-footer">
          <a href="/">Existing app</a>
        </footer>
      </div>
      <PrototypeNav
        view={state.view}
        onNav={(view) => {
          setState((current) => withPlanView(current, view));
        }}
      />
    </div>
  );
}
