import type { JSX } from "react";
import { formatDollars } from "../money";
import { NUTRITION_DEMO_LABEL, RECIPES } from "./prototypeData";
import { formatMacro } from "./prototypeModel";
import { budgetGap, planCost, planNutrition, type PlanLine, type PlanState } from "./planModel";

export function fitLine(costCents: number, budgetCents: number): string {
  const { fits, gapCents } = budgetGap(costCents, budgetCents);
  const cap = formatDollars(budgetCents);
  return fits
    ? `${formatDollars(gapCents)} left under the ${cap} plan cap.`
    : `${formatDollars(gapCents)} over the ${cap} plan cap.`;
}

export function PlanSummary(props: {
  state: PlanState;
  lines: PlanLine[];
  onBudgetChange: (value: string) => void;
}): JSX.Element {
  const { state } = props;
  const costCents = planCost(props.lines);
  const n = planNutrition(state);
  const macros: ReadonlyArray<readonly [number, string]> = [
    [n.energyKcal, "kcal"],
    [n.proteinG, "g protein"],
    [n.carbsG, "g carbs"],
    [n.fatG, "g fat"],
  ];
  return (
    <section className="tonight-summary" aria-labelledby="summary-heading">
      <h2 id="summary-heading">Plan summary</h2>
      <p className="tonight-kicker">Groceries to buy</p>
      <p className="tonight-price">{formatDollars(costCents)}</p>
      <p className="tonight-package">Whole packages · Sample estimate</p>
      <label htmlFor="plan-cap">Plan cap</label>
      <input
        id="plan-cap"
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={state.budgetInput}
        aria-invalid={state.budgetError !== null}
        aria-describedby={state.budgetError !== null ? "budget-error" : "budget-status"}
        onChange={(event) => { props.onBudgetChange(event.target.value); }}
      />
      {state.budgetError !== null ? (
        <p id="budget-error" className="tonight-error" role="alert">{state.budgetError}</p>
      ) : null}
      <p id="budget-status">{fitLine(costCents, state.budgetCents)}</p>
      <div className="tonight-nutrition-head">
        <h3>Plan total</h3>
        <p className="tonight-nutrition-note">{NUTRITION_DEMO_LABEL}</p>
      </div>
      <div className="tonight-macros">
        {macros.map(([value, label]) => (
          <div key={label}>
            <p>{formatMacro(value)}</p>
            <p>{label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PlanShoppingList(props: {
  lines: PlanLine[];
  checked: string[];
  pantryRow: JSX.Element;
  onToggle: (id: string) => void;
}): JSX.Element {
  const needed = props.lines.filter((line) => !line.fromPantry);
  const home = props.lines.filter((line) => line.fromPantry).map((line) => line.name.toLowerCase());
  return (
    <section className="tonight-shopping" aria-labelledby="shopping-heading">
      <h2 id="shopping-heading">Shopping list</h2>
      {needed.length === 0 ? (
        <p>Nothing to buy. Every ingredient is marked at home.</p>
      ) : (
        <ul className="tonight-check-list">
          {needed.map((line) => {
            const inputId = `shop-${line.ingredientId}`;
            const packs = `${String(line.packages)} ${line.packages === 1 ? "package" : "packages"}`;
            const usedIn = line.usedIn.map((id) => RECIPES[id].name).join(", ");
            return (
              <li key={line.ingredientId}>
                <label htmlFor={inputId}>
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={props.checked.includes(line.ingredientId)}
                    onChange={() => { props.onToggle(line.ingredientId); }}
                  />
                  <span>
                    <span>{line.name}</span>
                    <span className="tonight-line-meta">
                      {`${packs} · ${formatDollars(line.costCents)} · Used in ${usedIn}`}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <p className="tonight-kicker">Already at home</p>
      {props.pantryRow}
      {home.length > 0 ? <p className="tonight-line-meta">{home.join(", ")}</p> : null}
    </section>
  );
}
