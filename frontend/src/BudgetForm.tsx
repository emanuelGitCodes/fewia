import { useLayoutEffect, useRef, type Dispatch, type JSX, type SetStateAction } from "react";
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
export type AmountField = "monthly" | "cap";
export class AmountValidationError extends Error {
  readonly field: AmountField;

  constructor(field: AmountField, message: string) {
    super(`${field === "monthly" ? "Monthly limit" : "Plan cap"}: ${message}`);
    this.field = field;
  }
}

function parseAmount(state: FormState, field: AmountField): number | null {
  try {
    return parseDollars(state[field], field === "cap");
  } catch (caught) {
    if (caught instanceof Error) {
      throw new AmountValidationError(field, caught.message);
    }
    throw caught;
  }
}
const MEAL_ERROR = "Choose 1 to 3 meals.";
const SERVING_ERROR = "Each meal uses 1 to 8 servings.";
const RECIPE_ERROR = "Choose a recipe from the catalog.";
const SERVINGS = [1, 2, 3, 4, 5, 6, 7, 8];
export function initialForm(): FormState {
  return {
    monthly: "100",
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
  const monthlyLimitCents = parseAmount(state, "monthly");
  if (monthlyLimitCents === null) {
    throw new Error("Enter a monthly limit.");
  }
  return {
    monthly_limit_cents: monthlyLimitCents,
    request: {
      meals,
      diet: state.diet,
      budget_period: config.budget_period,
      plan_cap_cents: parseAmount(state, "cap"),
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
  validation?: { field: AmountField | null; message: string } | null;
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
export function BudgetForm({ config, value, onChange, disabled, validation = null }: Props): JSX.Element {
  const invalidField = validation?.message ? validation.field : null;
  const fieldsetRef = useRef<HTMLFieldSetElement>(null);
  const focusRow = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (focusRow.current !== null) {
      fieldsetRef.current?.querySelector<HTMLSelectElement>(`#recipe-${focusRow.current}`)?.focus();
      focusRow.current = null;
    }
  }, [value.meals]);
  const setMeal = (index: number, patch: Partial<MealRow>): void => {
    onChange((current) => ({
      ...current,
      meals: current.meals.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  };
  const addRecipe = config.recipes[0]?.id ?? "bean_tacos";
  return (
    <fieldset ref={fieldsetRef} disabled={disabled}>
      <legend>Budget and meals</legend>
      <p id="amount-format" className="amount-format">
        Enter a non-negative dollar amount with at most two decimal places, such as 100 or 40.50.
        Use digits and a decimal point, without a dollar sign or commas. Leave the plan cap blank for no cap.
      </p>
      <label htmlFor="monthly-limit">Monthly limit</label>
      <input id="monthly-limit" inputMode="decimal" value={value.monthly}
        aria-required="true"
        aria-invalid={invalidField === "monthly" || undefined}
        aria-describedby={invalidField === "monthly" ? "amount-format form-error" : "amount-format"}
        onChange={(event) => { onChange((current) => ({ ...current, monthly: event.target.value })); }} />
      {invalidField === "monthly" ? (
        <p id="form-error" className="form-error" role="alert" tabIndex={-1}>
          {validation?.message}
        </p>
      ) : null}
      <label htmlFor="plan-cap">Plan cap (optional)</label>
      <input id="plan-cap" inputMode="decimal" value={value.cap}
        aria-invalid={invalidField === "cap" || undefined}
        aria-describedby={invalidField === "cap" ? "amount-format form-error" : "amount-format"}
        onChange={(event) => { onChange((current) => ({ ...current, cap: event.target.value })); }} />
      {invalidField === "cap" ? (
        <p id="form-error" className="form-error" role="alert" tabIndex={-1}>
          {validation?.message}
        </p>
      ) : null}
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
              if (value.meals.length <= 1) return;
              focusRow.current = Math.min(index, value.meals.length - 2);
              onChange((current) => current.meals.length <= 1 ? current : {
                ...current, meals: current.meals.filter((_, row) => row !== index),
              });
            }}>{`Remove meal ${index + 1}`}</button>
        </div>
      ))}
      <button type="button" disabled={value.meals.length >= 3}
        onClick={() => {
          if (value.meals.length >= 3) return;
          focusRow.current = value.meals.length;
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
