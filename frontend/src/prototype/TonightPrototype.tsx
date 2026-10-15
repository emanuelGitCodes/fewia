import { useState, type JSX } from "react";
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
  const lines = groceryLines(state);
  const costCents = groceryCost(lines);
  return (
    <div className="tonight-prototype">
      <div className="tonight-canvas">
        <header className="tonight-header">
          <p className="tonight-wordmark">FEWIA</p>
          <p className="tonight-demo">{DEMO_NOTICE}</p>
        </header>
        <main>
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
