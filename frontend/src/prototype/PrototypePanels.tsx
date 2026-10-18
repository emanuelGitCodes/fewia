import { useEffect, useRef, useState, type JSX } from "react";
import { formatDollars } from "../money";
import {
  ESTIMATE_NOTICE,
  PANTRY_IDS,
  requireIngredient,
  type RecipeId,
} from "./prototypeData";
import { MealCards, MealPicker, filterMeals } from "./PlanMeals";
import { PlanShoppingList, PlanSummary, fitLine } from "./PlanSummary";
import { planCost, type PlanLine, type PlanState, type PlanView } from "./planModel";

export type IconName = "fork" | "jar" | "pencil" | "back";

const PATHS: Record<IconName, readonly string[]> = {
  fork: [
    "M8 3v7a2.5 2.5 0 1 0 5 0V3",
    "M8 3v4M10.5 3v18M13 3v4",
    "M17 4v17",
    "M17 4c2.4 1.6 2.6 6.2 0 8.4",
  ],
  jar: ["M8 8h8v11a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V8z", "M9 8V6h6v2M8 8h8M10 4.5h4"],
  pencil: ["M4 20l1.3-4.6L16.6 4.1a1.6 1.6 0 0 1 2.3 2.3L7.6 17.7 4 20z"],
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

function BackToPlan(props: { onBack: () => void }): JSX.Element {
  return (
    <button type="button" className="tonight-back" onClick={props.onBack}>
      <GeometryIcon name="back" />
      Back to plan
    </button>
  );
}

export function PlanPanel(props: {
  state: PlanState;
  lines: PlanLine[];
  onToggleMeal: (id: RecipeId, planned: boolean) => void;
  onShiftServings: (id: RecipeId, delta: number) => void;
  onTogglePantry: (ingredientId: string) => void;
  onToggleChecked: (id: string) => void;
  onBudgetChange: (value: string) => void;
  onEditPantry: () => void;
}): JSX.Element {
  const { meals } = props.state;
  const costCents = planCost(props.lines);
  const cost = formatDollars(costCents);
  const home = props.lines.filter((line) => line.fromPantry).length;
  const pantryStatus = home === 0 ? "None marked" : `${String(home)} at home`;
  const totalServings = meals.reduce((sum, meal) => sum + meal.servings, 0);
  const mealCount = `${String(meals.length)} ${meals.length === 1 ? "meal" : "meals"}`;
  const servingCount = `${String(totalServings)} ${totalServings === 1 ? "serving" : "servings"}`;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const pinnedRef = useRef<HTMLParagraphElement>(null);
  const [filter, setFilter] = useState("");
  const noMatch = filterMeals(filter).length === 0;
  // The pinned bar can wrap at large text sizes, so the canvas scroll padding follows its height (WCAG 2.4.11).
  useEffect(() => {
    const pinned = pinnedRef.current;
    const canvas = pinned?.closest(".tonight-canvas");
    if (pinned === null || !(canvas instanceof HTMLElement)) {
      return undefined;
    }
    const measure = (): void => {
      canvas.style.setProperty("--tonight-pinned-height", `${String(pinned.offsetHeight)}px`);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(pinned);
    return () => {
      observer?.disconnect();
      canvas.style.removeProperty("--tonight-pinned-height");
    };
  }, []);
  // A removed card button unmounts, so focus moves to the heading (WCAG 2.4.3).
  const toggleMeal = (id: RecipeId, planned: boolean): void => {
    if (planned) {
      headingRef.current?.focus({ preventScroll: false });
    }
    props.onToggleMeal(id, planned);
  };
  return (
    <section className="tonight-home" aria-labelledby="plan-heading">
      <p className="tonight-pinned" aria-hidden="true" ref={pinnedRef}>
        {`${cost} · ${fitLine(costCents, props.state.budgetCents)}`}
      </p>
      <h1 id="plan-heading" ref={headingRef} tabIndex={-1}>Your plan</h1>
      <div className="tonight-plan-main">
        <MealPicker meals={meals} filter={filter} onFilterChange={setFilter} onToggle={toggleMeal} />
        <MealCards
          meals={meals}
          servingsError={props.state.servingsError}
          onShiftServings={props.onShiftServings}
          pantry={props.state.pantry}
          onTogglePantry={props.onTogglePantry}
          onRemove={(id) => { toggleMeal(id, true); }}
        />
      </div>
      <div className="tonight-plan-side">
        <PlanSummary state={props.state} lines={props.lines} onBudgetChange={props.onBudgetChange} />
        <PlanShoppingList
          lines={props.lines}
          checked={props.state.checked}
          onToggle={props.onToggleChecked}
          pantryRow={
            <button
              type="button"
              className="tonight-pantry-row"
              aria-label={`${pantryStatus}, Edit pantry`}
              onClick={props.onEditPantry}
            >
              <span>{pantryStatus}</span>
              <GeometryIcon name="pencil" />
            </button>
          }
        />
      </div>
      <p className="tonight-notice">{ESTIMATE_NOTICE}</p>
      {/* One atomic status announces meals, servings, cost, fit, and the estimate qualifier. */}
      <div className="tonight-estimate-status" role="status" aria-atomic="true">
        {`${noMatch ? "No meals match. " : ""}${mealCount}, ${servingCount}. Groceries to buy ${cost}. ${fitLine(costCents, props.state.budgetCents)} Whole packages · Sample estimate.`}
      </div>
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
      <BackToPlan onBack={props.onBack} />
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

export function PrototypeNav(props: {
  view: PlanView;
  onNav: (view: PlanView) => void;
}): JSX.Element {
  const items: ReadonlyArray<{
    view: PlanView;
    icon: IconName;
    label: string;
    current: boolean;
  }> = [
    { view: "plan", icon: "fork", label: "Plan", current: props.view === "plan" },
    { view: "pantry", icon: "jar", label: "Pantry", current: props.view === "pantry" },
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
