import { useCallback, useEffect, useRef, useState, type JSX } from "react";
import { filterMeals, searchNote } from "./mealSearch";
import {
  RECIPES,
  mealLabels,
  requireIngredient,
  type Recipe,
  type RecipeId,
} from "./prototypeData";
import { formatMacro } from "./prototypeModel";
import type { PlannedMeal } from "./planModel";

export function MealPhoto(props: {
  src: string | null;
  alt: string;
  className: string;
}): JSX.Element {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [props.src]);
  if (props.src === null) {
    return <div className={props.className} />;
  }
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

function dietText(recipe: Recipe): string {
  return mealLabels(recipe).join(" · ");
}

export { filterMeals };

export function MealPicker(props: {
  meals: PlannedMeal[];
  filter: string;
  onFilterChange: (value: string) => void;
  onToggle: (id: RecipeId, planned: boolean) => void;
}): JSX.Element {
  const visible = filterMeals(props.filter);
  const note = searchNote(props.filter);
  const visibleKey = visible.join(",");
  const mealsRef = useRef<HTMLDivElement>(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);

  const updateArrows = useCallback(() => {
    const el = mealsRef.current;
    if (el === null) {
      setCanPrev(false);
      setCanNext(false);
      return;
    }
    setCanPrev(el.scrollLeft > 1);
    setCanNext(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    updateArrows();
    const el = mealsRef.current;
    if (el === null) {
      return undefined;
    }
    el.addEventListener("scroll", updateArrows);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateArrows);
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", updateArrows);
      observer?.disconnect();
    };
  }, [visibleKey, updateArrows]);

  const scrollMeals = (dir: -1 | 1): void => {
    const el = mealsRef.current;
    if (el === null) {
      return;
    }
    const step = Math.max(el.clientWidth * 0.8, 1);
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    if (typeof el.scrollBy === "function") {
      el.scrollBy({ left: dir * step, behavior: reduced ? "auto" : "smooth" });
    } else {
      el.scrollLeft += dir * step;
    }
    updateArrows();
  };

  return (
    <>
      <label htmlFor="meal-filter" className="tonight-filter-label">Find a meal</label>
      <input
        id="meal-filter"
        type="search"
        className="tonight-filter"
        autoComplete="off"
        aria-describedby={note === null ? undefined : "meal-filter-note"}
        value={props.filter}
        onChange={(event) => { props.onFilterChange(event.target.value); }}
      />
      {note === null ? null : <p id="meal-filter-note" className="tonight-filter-note">{note}</p>}
      {visible.length === 0 ? (
        <p>No meals match.</p>
      ) : (
        <div className="tonight-carousel">
          <button
            type="button"
            className="tonight-carousel-btn tonight-carousel-prev"
            aria-label="Show previous meals"
            disabled={!canPrev}
            onClick={() => { scrollMeals(-1); }}
          >
            <svg
              className="tonight-icon"
              viewBox="0 0 24 24"
              width="24"
              height="24"
              aria-hidden="true"
              focusable="false"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M15 6l-6 6 6 6" />
            </svg>
          </button>
          <div ref={mealsRef} className="tonight-meals" role="group" aria-label="Meal choices">
            {visible.map((id) => {
              const planned = props.meals.some((meal) => meal.recipeId === id);
              return (
                <button
                  key={id}
                  type="button"
                  className={planned ? "tonight-meal is-selected" : "tonight-meal"}
                  aria-pressed={planned}
                  onClick={() => { props.onToggle(id, planned); }}
                >
                  <MealPhoto src={RECIPES[id].image} alt="" className="tonight-thumb" />
                  <span>{RECIPES[id].name}</span>
                  {mealLabels(RECIPES[id]).length > 0 ? (
                    <span className="tonight-meal-diets">{dietText(RECIPES[id])}</span>
                  ) : null}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            className="tonight-carousel-btn tonight-carousel-next"
            aria-label="Show next meals"
            disabled={!canNext}
            onClick={() => { scrollMeals(1); }}
          >
            <svg
              className="tonight-icon"
              viewBox="0 0 24 24"
              width="24"
              height="24"
              aria-hidden="true"
              focusable="false"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      )}
    </>
  );
}

export function MealCards(props: {
  meals: PlannedMeal[];
  servingsError: { recipeId: RecipeId; message: string } | null;
  onShiftServings: (id: RecipeId, delta: number) => void;
  pantry: string[];
  onTogglePantry: (ingredientId: string) => void;
  onRemove: (id: RecipeId) => void;
}): JSX.Element {
  if (props.meals.length === 0) {
    return <p>Add a meal to start your plan.</p>;
  }
  return (
    <ul className="tonight-plan-cards" aria-label="Planned meals">
      {props.meals.map(({ recipeId, servings }) => {
        const recipe = RECIPES[recipeId];
        const nameId = `plan-card-${recipeId}`;
        const n = recipe.nutrition;
        const macros = `${formatMacro(n.energyKcal)} kcal · ${formatMacro(n.proteinG)} g protein · ${formatMacro(n.carbsG)} g carbs · ${formatMacro(n.fatG)} g fat per serving`;
        return (
          <li key={recipeId}>
            <article className="tonight-plan-card" aria-labelledby={nameId}>
              <MealPhoto src={recipe.image} alt="" className="tonight-thumb" />
              <div className="tonight-plan-card-body">
                <h2 id={nameId}>{recipe.name}</h2>
                {mealLabels(recipe).length > 0 ? (
                  <p className="tonight-diets">{dietText(recipe)}</p>
                ) : null}
                <div className="tonight-stepper" role="group" aria-label={`Servings for ${recipe.name}`}>
                  <button
                    type="button"
                    aria-label={`Decrease servings for ${recipe.name}`}
                    onClick={() => { props.onShiftServings(recipeId, -1); }}
                  >
                    −
                  </button>
                  <div className="tonight-servings">
                    {`${String(servings)} ${servings === 1 ? "serving" : "servings"}`}
                  </div>
                  <button
                    type="button"
                    aria-label={`Increase servings for ${recipe.name}`}
                    onClick={() => { props.onShiftServings(recipeId, 1); }}
                  >
                    +
                  </button>
                </div>
                {props.servingsError?.recipeId === recipeId ? (
                  <p className="tonight-error" role="alert">{props.servingsError.message}</p>
                ) : null}
                <p className="tonight-package">{macros}</p>
                <details className="tonight-plan-ingredients">
                  <summary>{`Ingredients (${String(recipe.ingredients.length)})`}</summary>
                  <fieldset>
                    <legend>Already at home</legend>
                    {recipe.ingredients.map(([ingredientId, perServing]) => {
                      const item = requireIngredient(ingredientId);
                      const inputId = `home-${recipeId}-${ingredientId}`;
                      const quantity = perServing * servings;
                      const amount =
                        item.unit === "g" ? `${String(quantity)} g` : `× ${String(quantity)}`;
                      return (
                        <div key={ingredientId} className="tonight-plan-ingredient">
                          <input
                            id={inputId}
                            type="checkbox"
                            checked={props.pantry.includes(ingredientId)}
                            onChange={() => { props.onTogglePantry(ingredientId); }}
                          />
                          <label htmlFor={inputId}>
                            {item.name} <span className="tonight-plan-qty">{amount}</span>
                          </label>
                        </div>
                      );
                    })}
                  </fieldset>
                </details>
                <button
                  type="button"
                  className="tonight-plan-remove"
                  onClick={() => { props.onRemove(recipeId); }}
                >
                  {`Remove ${recipe.name}`}
                </button>
              </div>
            </article>
          </li>
        );
      })}
    </ul>
  );
}
