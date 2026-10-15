import { useEffect, useRef, useState, type JSX } from "react";
import { DEMO_NOTICE } from "./prototypeData";
import {
  groceryCost,
  groceryLines,
  initialState,
  shiftServings,
  toggleChecked,
  togglePantry,
  withBudgetInput,
  withRecipe,
  withView,
  type PrototypeState,
} from "./prototypeModel";
import {
  BudgetPanel,
  PantryPanel,
  PrototypeNav,
  ShoppingPanel,
  TonightPanel,
} from "./PrototypePanels";
import "./tonight.css";

export function TonightPrototype(): JSX.Element {
  const [state, setState] = useState<PrototypeState>(initialState);
  const previousView = useRef(state.view);
  const canvasRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const lines = groceryLines(state);
  const costCents = groceryCost(lines);
  useEffect(() => {
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
          {state.view === "tonight" ? (
            <TonightPanel
              state={state}
              lines={lines}
              onSelect={(id) => {
                setState((current) => withRecipe(current, id));
              }}
              onShiftServings={(delta) => {
                setState((current) => shiftServings(current, delta));
              }}
              onEditPantry={() => {
                setState((current) => withView(current, "pantry"));
              }}
              onSeeShopping={() => {
                setState((current) => withView(current, "shopping"));
              }}
            />
          ) : null}
          {state.view === "pantry" ? (
            <PantryPanel
              pantry={state.pantry}
              onToggle={(id) => {
                setState((current) => togglePantry(current, id));
              }}
              onBack={() => {
                setState((current) => withView(current, "tonight"));
              }}
            />
          ) : null}
          {state.view === "shopping" ? (
            <ShoppingPanel
              lines={lines}
              checked={state.checked}
              onToggle={(id) => {
                setState((current) => toggleChecked(current, id));
              }}
              onBack={() => {
                setState((current) => withView(current, "tonight"));
              }}
            />
          ) : null}
          {state.view === "budget" ? (
            <BudgetPanel
              state={state}
              costCents={costCents}
              onChange={(value) => {
                setState((current) => withBudgetInput(current, value));
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
          setState((current) => withView(current, view));
        }}
      />
    </div>
  );
}
