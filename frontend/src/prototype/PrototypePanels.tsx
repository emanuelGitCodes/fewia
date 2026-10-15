import { useEffect, useState, type JSX } from "react";
import { formatDollars } from "../money";
import {
  ESTIMATE_NOTICE,
  NUTRITION_DEMO_LABEL,
  PANTRY_IDS,
  RECIPE_ORDER,
  RECIPES,
  requireIngredient,
  type RecipeId,
} from "./prototypeData";
import {
  atHomeNames,
  formatMacro,
  groceryCost,
  mealFits,
  shoppingLines,
  type GroceryLine,
  type PrototypeState,
  type PrototypeView,
} from "./prototypeModel";

export type IconName = "fork" | "jar" | "bars" | "pencil" | "arrow" | "back";

const PATHS: Record<IconName, readonly string[]> = {
  fork: [
    "M8 3v7a2.5 2.5 0 1 0 5 0V3",
    "M8 3v4M10.5 3v18M13 3v4",
    "M17 4v17",
    "M17 4c2.4 1.6 2.6 6.2 0 8.4",
  ],
  jar: ["M8 8h8v11a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V8z", "M9 8V6h6v2M8 8h8M10 4.5h4"],
  bars: ["M6 18V11M12 18V6M18 18v-5"],
  pencil: ["M4 20l1.3-4.6L16.6 4.1a1.6 1.6 0 0 1 2.3 2.3L7.6 17.7 4 20z"],
  arrow: ["M5 12h14M13 6l6 6-6 6"],
  back: ["M19 12H5M11 6l-6 6 6 6"],
};

export function GeometryIcon(props: { name: IconName }): JSX.Element {
  return (
    <svg className="tonight-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        {PATHS[props.name].map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
    </svg>
  );
}

function MealPhoto(props: { src: string; alt: string; className: string }): JSX.Element {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [props.src]);
  return (
    <div className={props.className}>
      {failed ? (
        <span className="tonight-photo-fallback">{props.alt}</span>
      ) : (
        <img src={props.src} alt={props.alt} onError={() => { setFailed(true); }} />
      )}
    </div>
  );
}

function BackTonight(props: { onBack: () => void }): JSX.Element {
  return (
    <button type="button" className="tonight-back" onClick={props.onBack}>
      <GeometryIcon name="back" />
      Back to tonight
    </button>
  );
}

export function TonightPanel(props: {
  state: PrototypeState;
  lines: GroceryLine[];
  onSelect: (id: RecipeId) => void;
  onShiftServings: (delta: number) => void;
  onEditPantry: () => void;
  onSeeShopping: () => void;
}): JSX.Element {
  const recipe = RECIPES[props.state.recipeId];
  const cost = formatDollars(groceryCost(props.lines));
  const home = atHomeNames(props.state);
  const servingsLabel = `${String(props.state.servings)} ${props.state.servings === 1 ? "serving" : "servings"}`;
  const macros: ReadonlyArray<readonly [string, string]> = [
    [formatMacro(recipe.nutrition.energyKcal), "kcal"],
    [`${formatMacro(recipe.nutrition.proteinG)} g`, "Protein"],
    [`${formatMacro(recipe.nutrition.carbsG)} g`, "Carbs"],
    [`${formatMacro(recipe.nutrition.fatG)} g`, "Fat"],
  ];
  return (
    <section className="tonight-home" aria-labelledby="tonight-heading">
      <h1 id="tonight-heading" tabIndex={-1}>What sounds good?</h1>
      <div className="tonight-meals" role="group" aria-label="Meal choices">
        {RECIPE_ORDER.map((id) => {
          const choice = RECIPES[id];
          const selected = id === props.state.recipeId;
          return (
            <button
              key={id}
              type="button"
              className={selected ? "tonight-meal is-selected" : "tonight-meal"}
              aria-pressed={selected}
              onClick={() => { props.onSelect(id); }}
            >
              <MealPhoto src={choice.image} alt="" className="tonight-thumb" />
              <span>{choice.name}</span>
            </button>
          );
        })}
      </div>
      <div className="tonight-hero">
        <MealPhoto src={recipe.image} alt={recipe.name} className="tonight-photo" />
        <div className="tonight-facts">
          <h2>{recipe.name}</h2>
          <div className="tonight-stepper" role="group" aria-label="Servings">
            <button type="button" aria-label="Decrease servings" onClick={() => { props.onShiftServings(-1); }}>
              −
            </button>
            <p role="status">{servingsLabel}</p>
            <button type="button" aria-label="Increase servings" onClick={() => { props.onShiftServings(1); }}>
              +
            </button>
          </div>
          {props.state.servingsError !== null ? (
            <p className="tonight-error" role="alert">{props.state.servingsError}</p>
          ) : null}
          <p className="tonight-kicker">Groceries to buy</p>
          <p className="tonight-price" role="status">{cost}</p>
          <p className="tonight-package">Whole packages · Sample estimate</p>
          <p className="tonight-kicker">Already at home</p>
          <div className="tonight-pantry-row">
            <p>{home.length === 0 ? "None marked" : home.join(", ")}</p>
            <button type="button" aria-label="Edit pantry" onClick={props.onEditPantry}>
              <GeometryIcon name="pencil" />
            </button>
          </div>
        </div>
      </div>
      <section className="tonight-nutrition" aria-labelledby="nutrition-heading">
        <h2 id="nutrition-heading">Nutrition per serving</h2>
        <p className="tonight-nutrition-note">{NUTRITION_DEMO_LABEL}</p>
        <div className="tonight-macros">
          {macros.map(([value, label]) => (
            <div key={label}>
              <p>{value}</p>
              <p>{label}</p>
            </div>
          ))}
        </div>
      </section>
      <button type="button" className="tonight-primary" onClick={props.onSeeShopping}>
        <span>See shopping list</span>
        <GeometryIcon name="arrow" />
      </button>
      <p className="tonight-notice">{ESTIMATE_NOTICE}</p>
    </section>
  );
}

export function PantryPanel(props: {
  pantry: string[];
  onToggle: (id: string) => void;
  onBack: () => void;
}): JSX.Element {
  return (
    <section className="tonight-page" aria-labelledby="pantry-heading">
      <BackTonight onBack={props.onBack} />
      <h1 id="pantry-heading" tabIndex={-1}>Pantry</h1>
      <p>Mark ingredients you already have.</p>
      <ul className="tonight-check-list">
        {PANTRY_IDS.map((id) => {
          const inputId = `pantry-${id}`;
          return (
            <li key={id}>
              <label htmlFor={inputId}>
                <input
                  id={inputId}
                  type="checkbox"
                  checked={props.pantry.includes(id)}
                  onChange={() => { props.onToggle(id); }}
                />
                {requireIngredient(id).name}
              </label>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function ShoppingPanel(props: {
  lines: GroceryLine[];
  checked: string[];
  onToggle: (id: string) => void;
  onBack: () => void;
}): JSX.Element {
  const needed = shoppingLines(props.lines);
  const total = formatDollars(groceryCost(props.lines));
  return (
    <section className="tonight-page" aria-labelledby="shopping-heading">
      <BackTonight onBack={props.onBack} />
      <h1 id="shopping-heading" tabIndex={-1}>Shopping list</h1>
      {needed.length === 0 ? (
        <p role="status">Nothing to buy. Every ingredient is marked at home.</p>
      ) : (
        <ul className="tonight-check-list">
          {needed.map((line) => {
            const inputId = `shop-${line.ingredientId}`;
            const packs = `${String(line.packages)} ${line.packages === 1 ? "package" : "packages"}`;
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
                    <span className="tonight-line-meta">{`${packs} · ${formatDollars(line.costCents)}`}</span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <p className="tonight-price" role="status">{`Total ${total}`}</p>
      <p className="tonight-package">Whole packages</p>
      <p className="tonight-notice">{ESTIMATE_NOTICE}</p>
    </section>
  );
}

export function BudgetPanel(props: {
  state: PrototypeState;
  costCents: number;
  onChange: (value: string) => void;
}): JSX.Element {
  const cost = formatDollars(props.costCents);
  const cap = formatDollars(props.state.budgetCents);
  const fits = mealFits(props.costCents, props.state.budgetCents);
  const status = fits
    ? `This meal fits the ${cap} plan cap.`
    : `This meal is over the ${cap} plan cap.`;
  return (
    <section className="tonight-page" aria-labelledby="budget-heading">
      <h1 id="budget-heading" tabIndex={-1}>Budget</h1>
      <label htmlFor="plan-cap">Plan cap</label>
      <input
        id="plan-cap"
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={props.state.budgetInput}
        aria-invalid={props.state.budgetError !== null}
        aria-describedby={props.state.budgetError !== null ? "budget-error" : "budget-status"}
        onChange={(event) => { props.onChange(event.target.value); }}
      />
      {props.state.budgetError !== null ? (
        <p id="budget-error" className="tonight-error" role="alert">{props.state.budgetError}</p>
      ) : null}
      <p>{`Groceries to buy ${cost}`}</p>
      <p id="budget-status" role="status">{status}</p>
      <p className="tonight-notice">{ESTIMATE_NOTICE}</p>
    </section>
  );
}

export function PrototypeNav(props: {
  view: PrototypeView;
  onNav: (view: "tonight" | "pantry" | "budget") => void;
}): JSX.Element {
  const items: ReadonlyArray<{
    view: "tonight" | "pantry" | "budget";
    icon: IconName;
    label: string;
    current: boolean;
  }> = [
    {
      view: "tonight",
      icon: "fork",
      label: "Tonight",
      current: props.view === "tonight" || props.view === "shopping",
    },
    { view: "pantry", icon: "jar", label: "Pantry", current: props.view === "pantry" },
    { view: "budget", icon: "bars", label: "Budget", current: props.view === "budget" },
  ];
  return (
    <nav className="tonight-nav" aria-label="Prototype sections">
      {items.map((item) => (
        <button
          key={item.view}
          type="button"
          aria-current={item.current ? "page" : undefined}
          onClick={() => { props.onNav(item.view); }}
        >
          <GeometryIcon name={item.icon} />
          {item.label}
        </button>
      ))}
    </nav>
  );
}
