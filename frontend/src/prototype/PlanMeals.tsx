import { useEffect, useState, type JSX } from "react";
import { RECIPE_ORDER, RECIPES, requireIngredient, type RecipeId } from "./prototypeData";
import { formatMacro } from "./prototypeModel";
import type { PlannedMeal } from "./planModel";

export function MealPhoto(props: { src: string; alt: string; className: string }): JSX.Element {
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

export function MealPicker(props: {
  meals: PlannedMeal[];
  onToggle: (id: RecipeId, planned: boolean) => void;
}): JSX.Element {
  return (
    <div className="tonight-meals" role="group" aria-label="Meal choices">
      {RECIPE_ORDER.map((id) => {
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
          </button>
        );
      })}
    </div>
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
