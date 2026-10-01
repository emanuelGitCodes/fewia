import type { Dispatch, JSX, SetStateAction } from "react";
import type { CatalogItem, Diet, GroceryConfig, GroceryJobCreate } from "./apiTypes";
import { parseDollars } from "./money";

export type MealRow = { recipe_id: string; servings: number };
export type FormState = {
  monthly: string;
  cap: string;
  meals: MealRow[];
  diet: Diet;
  pantry: string[];
  exclusions: string[];
};
const MEAL_ERROR = "Choose 1 to 3 meals.";
const SERVING_ERROR = "Each meal uses 1 to 8 servings.";
const RECIPE_ERROR = "Choose a recipe from the catalog.";
const SERVINGS = [1, 2, 3, 4, 5, 6, 7, 8];
export function initialForm(): FormState {
  return {
    monthly: "300",
    cap: "40",
    diet: "omnivore",
    pantry: [],
    exclusions: [],
    meals: [{ recipe_id: "bean_tacos", servings: 2 }],
  };
}

export function buildRequest(config: GroceryConfig, state: FormState): GroceryJobCreate {
  if (state.meals.length < 1 || state.meals.length > 3) {
    throw new Error(MEAL_ERROR);
  }
  const known = new Set(config.recipes.map((item) => item.id));
  const meals = state.meals.map((meal) => {
    if (!known.has(meal.recipe_id)) {
      throw new Error(RECIPE_ERROR);
    }
    if (!Number.isSafeInteger(meal.servings) || meal.servings < 1 || meal.servings > 8) {
      throw new Error(SERVING_ERROR);
    }
    return { recipe_id: meal.recipe_id, servings: meal.servings };
  });
  const monthlyLimitCents = parseDollars(state.monthly);
  if (monthlyLimitCents === null) {
    throw new Error("Enter a monthly limit.");
  }
  return {
    monthly_limit_cents: monthlyLimitCents,
    request: {
      meals,
      diet: state.diet,
      budget_period: config.budget_period,
      plan_cap_cents: parseDollars(state.cap, true),
      pantry_ingredients: [...state.pantry],
      ingredient_exclusions: [...state.exclusions],
    },
  };
}

type Props = {
  config: GroceryConfig;
  value: FormState;
  onChange: Dispatch<SetStateAction<FormState>>;
  disabled: boolean;
};
function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
}
function checks(
  title: string, prefix: string, items: CatalogItem[], selected: string[],
  onToggle: (id: string) => void,
): JSX.Element {
  return (
    <details>
      <summary>{title}</summary>
      {items.map((item) => (
        <label key={`${prefix}-${item.id}`} htmlFor={`${prefix}-${item.id}`}>
          <input id={`${prefix}-${item.id}`} type="checkbox" checked={selected.includes(item.id)}
            onChange={() => { onToggle(item.id); }} />
          {`${prefix} ${item.name}`}
        </label>
      ))}
    </details>
  );
}
export function BudgetForm({ config, value, onChange, disabled }: Props): JSX.Element {
  const setMeal = (index: number, patch: Partial<MealRow>): void => {
    onChange((current) => ({
      ...current,
      meals: current.meals.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  };
  const addRecipe = config.recipes[0]?.id ?? "bean_tacos";
  return (
    <fieldset disabled={disabled}>
      <legend>Budget and meals</legend>
      <label htmlFor="monthly-limit">Monthly limit</label>
      <input id="monthly-limit" inputMode="decimal" value={value.monthly}
        onChange={(event) => { onChange((current) => ({ ...current, monthly: event.target.value })); }} />
      <label htmlFor="plan-cap">Plan cap (optional)</label>
      <input id="plan-cap" inputMode="decimal" value={value.cap}
        onChange={(event) => { onChange((current) => ({ ...current, cap: event.target.value })); }} />
      {value.meals.map((meal, index) => (
        <div key={`meal-${index}`}>
          <label htmlFor={`recipe-${index}`}>{`Recipe ${index + 1}`}</label>
          <select id={`recipe-${index}`} value={meal.recipe_id}
            onChange={(event) => { setMeal(index, { recipe_id: event.target.value }); }}>
            {config.recipes.map((recipe) => (
              <option key={recipe.id} value={recipe.id}>{recipe.name}</option>
            ))}
          </select>
          <label htmlFor={`servings-${index}`}>{`Servings ${index + 1}`}</label>
          <select id={`servings-${index}`} value={meal.servings}
            onChange={(event) => { setMeal(index, { servings: Number(event.target.value) }); }}>
            {SERVINGS.map((count) => (
              <option key={count} value={count}>{count}</option>
            ))}
          </select>
          <button type="button" disabled={value.meals.length <= 1}
            onClick={() => {
              onChange((current) => current.meals.length <= 1 ? current : {
                ...current, meals: current.meals.filter((_, row) => row !== index),
              });
            }}>{`Remove meal ${index + 1}`}</button>
        </div>
      ))}
      <button type="button" disabled={value.meals.length >= 3}
        onClick={() => {
          onChange((current) => current.meals.length >= 3 ? current : {
            ...current, meals: [...current.meals, { recipe_id: addRecipe, servings: 2 }],
          });
        }}>Add meal</button>
      <label htmlFor="diet">Diet</label>
      <select id="diet" value={value.diet}
        onChange={(event) => {
          onChange((current) => ({ ...current, diet: event.target.value as Diet }));
        }}>
        <option value="omnivore">No preference</option>
        <option value="vegetarian">Vegetarian</option>
        <option value="vegan">Vegan</option>
      </select>
      {checks("Pantry", "Pantry", config.ingredients, value.pantry, (id) => {
        onChange((current) => ({ ...current, pantry: toggleId(current.pantry, id) }));
      })}
      {checks("Ingredient exclusions", "Exclude", config.ingredients, value.exclusions, (id) => {
        onChange((current) => ({ ...current, exclusions: toggleId(current.exclusions, id) }));
      })}
    </fieldset>
  );
}
