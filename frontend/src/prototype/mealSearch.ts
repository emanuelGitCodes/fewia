import {
  CATALOG_SEARCH_TERMS,
  INGREDIENTS,
  RECIPE_ORDER,
  RECIPES,
  mealLabels,
  type Diet,
  type RecipeId,
  type Tag,
} from "./prototypeData";

type SearchTerm = { target: Diet | Tag; note?: string };

// The backend owns the terms. A null note in the JSON means the term has no note.
export const SEARCH_TERMS: Readonly<Record<string, SearchTerm>> = Object.fromEntries(
  Object.entries(CATALOG_SEARCH_TERMS).map(([term, { target, note }]) => [
    term,
    note === null ? { target } : { target, note },
  ]),
);

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
