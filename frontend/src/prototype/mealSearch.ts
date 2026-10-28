import {
  INGREDIENTS,
  RECIPE_ORDER,
  RECIPES,
  mealLabels,
  type Diet,
  type RecipeId,
  type Tag,
} from "./prototypeData";

type SearchTerm = { target: Diet | Tag; note?: string };

const KETO_NOTE =
  "No meal in this catalog is keto. These meals have 30 g of carbs or less per serving.";
const CARNIVORE_NOTE = "No meal is strictly carnivore. These meals include chicken.";

export const SEARCH_TERMS: Readonly<Record<string, SearchTerm>> = {
  keto: { target: "lower_carb", note: KETO_NOTE },
  "low carb": { target: "lower_carb", note: KETO_NOTE },
  lowcarb: { target: "lower_carb", note: KETO_NOTE },
  "low-carb": { target: "lower_carb", note: KETO_NOTE },
  carnivore: { target: "chicken", note: CARNIVORE_NOTE },
  meat: { target: "chicken", note: CARNIVORE_NOTE },
  gf: { target: "gluten_free_ingredients" },
  "gluten free": { target: "gluten_free_ingredients" },
  "gluten-free": { target: "gluten_free_ingredients" },
  celiac: { target: "gluten_free_ingredients" },
  "plant based": { target: "vegan" },
  "plant-based": { target: "vegan" },
  veggie: { target: "vegetarian" },
  protein: { target: "high_protein" },
};

function normalize(filter: string): string {
  return filter.toLowerCase().trim().replace(/\s+/g, " ");
}

function termFor(query: string): SearchTerm | null {
  return Object.prototype.hasOwnProperty.call(SEARCH_TERMS, query) ? SEARCH_TERMS[query] : null;
}

function matchesText(id: RecipeId, query: string): boolean {
  const recipe = RECIPES[id];
  return (
    recipe.name.toLowerCase().includes(query) ||
    mealLabels(recipe).some((label) => label.toLowerCase().includes(query)) ||
    recipe.ingredients.some(([ingredientId]) =>
      (INGREDIENTS[ingredientId]?.name ?? "").toLowerCase().includes(query),
    )
  );
}

function hasTarget(id: RecipeId, target: Diet | Tag): boolean {
  const recipe = RECIPES[id];
  return (
    (recipe.diets as readonly string[]).includes(target) ||
    (recipe.tags as readonly string[]).includes(target)
  );
}

export function filterMeals(filter: string): RecipeId[] {
  const query = normalize(filter);
  const term = termFor(query);
  return RECIPE_ORDER.filter(
    (id) => matchesText(id, query) || (term !== null && hasTarget(id, term.target)),
  );
}

export function searchNote(filter: string): string | null {
  return termFor(normalize(filter))?.note ?? null;
}
