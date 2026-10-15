import { parseDollars } from "../money";
import {
  INITIAL_BUDGET_CENTS,
  INITIAL_BUDGET_INPUT,
  INITIAL_PANTRY,
  INITIAL_SERVINGS,
  MAX_SERVINGS,
  MIN_SERVINGS,
  RECIPES,
  SERVING_ERROR,
  requireIngredient,
  type RecipeId,
} from "./prototypeData";

export type PrototypeView = "tonight" | "pantry" | "shopping" | "budget";
export type PrototypeState = {
  recipeId: RecipeId;
  servings: number;
  pantry: string[];
  checked: string[];
  view: PrototypeView;
  budgetInput: string;
  budgetCents: number;
  budgetError: string | null;
  servingsError: string | null;
};
export type GroceryLine = {
  ingredientId: string;
  name: string;
  unit: "g" | "each";
  quantity: number;
  packages: number;
  costCents: number;
  fromPantry: boolean;
};

const AMOUNT_ERROR = "Enter a non-negative dollar amount with at most two decimal places.";

export function initialState(): PrototypeState {
  return {
    recipeId: "bean_tacos",
    servings: INITIAL_SERVINGS,
    pantry: [...INITIAL_PANTRY],
    checked: [],
    view: "tonight",
    budgetInput: INITIAL_BUDGET_INPUT,
    budgetCents: INITIAL_BUDGET_CENTS,
    budgetError: null,
    servingsError: null,
  };
}

export function packageCount(totalQuantity: number, packageQuantity: number): number {
  if (totalQuantity <= 0) {
    return 0;
  }
  return Math.trunc((totalQuantity + packageQuantity - 1) / packageQuantity);
}

export function groceryLines(state: PrototypeState): GroceryLine[] {
  return RECIPES[state.recipeId].ingredients.map(([ingredientId, perServing]) => {
    const item = requireIngredient(ingredientId);
    const fromPantry = state.pantry.includes(ingredientId);
    const quantity = perServing * state.servings;
    const packages = fromPantry ? 0 : packageCount(quantity, item.packageQuantity);
    return {
      ingredientId,
      name: item.name,
      unit: item.unit,
      quantity,
      packages,
      costCents: fromPantry ? 0 : packages * item.priceCents,
      fromPantry,
    };
  });
}

export function groceryCost(lines: GroceryLine[]): number {
  return lines.reduce((sum, line) => sum + line.costCents, 0);
}

export function shoppingLines(lines: GroceryLine[]): GroceryLine[] {
  return lines.filter((line) => !line.fromPantry);
}

export function atHomeNames(state: PrototypeState): string[] {
  const inMeal = new Set(RECIPES[state.recipeId].ingredients.map(([id]) => id));
  return state.pantry.filter((id) => inMeal.has(id)).map((id) => requireIngredient(id).name);
}

export function mealFits(costCents: number, budgetCents: number): boolean {
  return costCents <= budgetCents;
}

export function withRecipe(state: PrototypeState, recipeId: RecipeId): PrototypeState {
  if (recipeId === state.recipeId) {
    return state;
  }
  return { ...state, recipeId, checked: [], servingsError: null };
}

export function shiftServings(state: PrototypeState, delta: number): PrototypeState {
  const servings = state.servings + delta;
  if (!Number.isSafeInteger(servings) || servings < MIN_SERVINGS || servings > MAX_SERVINGS) {
    return { ...state, servingsError: SERVING_ERROR };
  }
  return { ...state, servings, servingsError: null, checked: [] };
}

export function togglePantry(state: PrototypeState, ingredientId: string): PrototypeState {
  const pantry = state.pantry.includes(ingredientId)
    ? state.pantry.filter((id) => id !== ingredientId)
    : [...state.pantry, ingredientId];
  return { ...state, pantry, checked: [] };
}

export function toggleChecked(state: PrototypeState, ingredientId: string): PrototypeState {
  const checked = state.checked.includes(ingredientId)
    ? state.checked.filter((id) => id !== ingredientId)
    : [...state.checked, ingredientId];
  return { ...state, checked };
}

export function withView(state: PrototypeState, view: PrototypeView): PrototypeState {
  return { ...state, view };
}

export function withBudgetInput(state: PrototypeState, budgetInput: string): PrototypeState {
  try {
    const budgetCents = parseDollars(budgetInput);
    if (budgetCents === null) {
      return { ...state, budgetInput, budgetError: AMOUNT_ERROR };
    }
    return { ...state, budgetInput, budgetCents, budgetError: null };
  } catch (error) {
    const budgetError = error instanceof Error ? error.message : AMOUNT_ERROR;
    return { ...state, budgetInput, budgetError };
  }
}

export function formatMacro(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
