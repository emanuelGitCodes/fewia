import {
  INITIAL_BUDGET_CENTS,
  INITIAL_BUDGET_INPUT,
  INITIAL_PANTRY,
  INITIAL_SERVINGS,
  MAX_MEALS,
  MAX_SERVINGS,
  MIN_SERVINGS,
  RECIPES,
  SERVING_ERROR,
  requireIngredient,
  type Nutrition,
  type RecipeId,
} from "./prototypeData";
import { packageCount, withBudgetInput } from "./prototypeModel";

export type PlannedMeal = { recipeId: RecipeId; servings: number };
export type PlanView = "plan" | "pantry";
export type PlanState = {
  meals: PlannedMeal[];
  pantry: string[];
  // Shopping checks apply only to the current grocery list.
  checked: string[];
  view: PlanView;
  budgetInput: string;
  budgetCents: number;
  budgetError: string | null;
  // servingsError is transient. A view change clears it.
  servingsError: { recipeId: RecipeId; message: string } | null;
};
export type PlanLine = {
  ingredientId: string;
  name: string;
  unit: "g" | "each";
  // quantity sums every planned meal before packages round up.
  quantity: number;
  packages: number;
  costCents: number;
  fromPantry: boolean;
  usedIn: RecipeId[];
};

export function initialPlanState(): PlanState {
  return {
    meals: [{ recipeId: "bean_tacos", servings: INITIAL_SERVINGS }],
    pantry: [...INITIAL_PANTRY],
    checked: [],
    view: "plan",
    budgetInput: INITIAL_BUDGET_INPUT,
    budgetCents: INITIAL_BUDGET_CENTS,
    budgetError: null,
    servingsError: null,
  };
}

export function planLines(state: PlanState): PlanLine[] {
  const byId = new Map<string, PlanLine>();
  for (const { recipeId, servings } of state.meals) {
    for (const [ingredientId, perServing] of RECIPES[recipeId].ingredients) {
      const line = byId.get(ingredientId);
      if (line === undefined) {
        const item = requireIngredient(ingredientId);
        byId.set(ingredientId, {
          ingredientId,
          name: item.name,
          unit: item.unit,
          quantity: perServing * servings,
          packages: 0,
          costCents: 0,
          fromPantry: state.pantry.includes(ingredientId),
          usedIn: [recipeId],
        });
      } else {
        line.quantity += perServing * servings;
        line.usedIn.push(recipeId);
      }
    }
  }
  // Round the summed quantity once, so a shared package is bought once.
  return [...byId.values()].map((line) => {
    const item = requireIngredient(line.ingredientId);
    const packages = line.fromPantry ? 0 : packageCount(line.quantity, item.packageQuantity);
    return { ...line, packages, costCents: packages * item.priceCents };
  });
}

export function planCost(lines: PlanLine[]): number {
  return lines.reduce((sum, line) => sum + line.costCents, 0);
}

export function planNutrition(state: PlanState): Nutrition {
  const total: Nutrition = { energyKcal: 0, proteinG: 0, carbsG: 0, fatG: 0 };
  for (const { recipeId, servings } of state.meals) {
    const per = RECIPES[recipeId].nutrition;
    total.energyKcal += per.energyKcal * servings;
    total.proteinG += per.proteinG * servings;
    total.carbsG += per.carbsG * servings;
    total.fatG += per.fatG * servings;
  }
  const round = (x: number): number => Math.round(x * 10) / 10;
  return {
    energyKcal: round(total.energyKcal),
    proteinG: round(total.proteinG),
    carbsG: round(total.carbsG),
    fatG: round(total.fatG),
  };
}

export function budgetGap(
  costCents: number,
  budgetCents: number,
): { fits: boolean; gapCents: number } {
  return { fits: costCents <= budgetCents, gapCents: Math.abs(budgetCents - costCents) };
}

// A check survives only while its line is still bought in the same quantity.
export function retainChecks(before: PlanLine[], after: PlanLine[], checked: string[]): string[] {
  return checked.filter((id) => {
    const next = after.find((line) => line.ingredientId === id);
    const prev = before.find((line) => line.ingredientId === id);
    return next !== undefined && !next.fromPantry && next.packages === prev?.packages;
  });
}

function withMeals(state: PlanState, meals: PlannedMeal[]): PlanState {
  const next = { ...state, meals, servingsError: null };
  return {
    ...next,
    checked: retainChecks(planLines(state), planLines(next), state.checked),
  };
}

export function addMeal(state: PlanState, recipeId: RecipeId): PlanState {
  if (state.meals.length >= MAX_MEALS || state.meals.some((m) => m.recipeId === recipeId)) {
    return state;
  }
  return withMeals(state, [...state.meals, { recipeId, servings: INITIAL_SERVINGS }]);
}

export function removeMeal(state: PlanState, recipeId: RecipeId): PlanState {
  return withMeals(
    state,
    state.meals.filter((m) => m.recipeId !== recipeId),
  );
}

export function shiftMealServings(state: PlanState, recipeId: RecipeId, delta: number): PlanState {
  const meal = state.meals.find((m) => m.recipeId === recipeId);
  if (meal === undefined) {
    return state;
  }
  const servings = meal.servings + delta;
  if (!Number.isSafeInteger(servings) || servings < MIN_SERVINGS || servings > MAX_SERVINGS) {
    return { ...state, servingsError: { recipeId, message: SERVING_ERROR } };
  }
  return withMeals(
    state,
    state.meals.map((m) => (m.recipeId === recipeId ? { ...m, servings } : m)),
  );
}

export function togglePlanPantry(state: PlanState, ingredientId: string): PlanState {
  const pantry = state.pantry.includes(ingredientId)
    ? state.pantry.filter((id) => id !== ingredientId)
    : [...state.pantry, ingredientId];
  const next = { ...state, pantry };
  return { ...next, checked: retainChecks(planLines(state), planLines(next), state.checked) };
}

export function togglePlanChecked(state: PlanState, ingredientId: string): PlanState {
  const checked = state.checked.includes(ingredientId)
    ? state.checked.filter((id) => id !== ingredientId)
    : [...state.checked, ingredientId];
  return { ...state, checked };
}

export function withPlanView(state: PlanState, view: PlanView): PlanState {
  if (view === state.view) {
    return state;
  }
  return { ...state, view, servingsError: null };
}

export function withPlanBudgetInput(state: PlanState, input: string): PlanState {
  return withBudgetInput(state, input);
}
