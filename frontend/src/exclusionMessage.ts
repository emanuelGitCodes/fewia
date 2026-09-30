import type { CatalogItem, GroceryJob } from "./apiTypes";

function catalogName(items: CatalogItem[], id: string): string {
  return items.find((item) => item.id === id)?.name ?? id;
}

function recipeTitle(items: CatalogItem[], id: string): string {
  const match = items.find((item) => item.id === id)?.name;
  if (match === undefined) {
    return id;
  }
  return `${match.slice(0, 1).toUpperCase()}${match.slice(1)}`;
}

export function exclusionMessage(
  job: GroceryJob | null,
  recipes: CatalogItem[],
  ingredients: CatalogItem[],
): string | null {
  if (job?.status !== "failed" || job.error_code !== "exclusion_reject" || job.error_detail == null) {
    return null;
  }
  const recipeName = recipeTitle(recipes, job.error_detail.recipe_id);
  const ingredientName = catalogName(ingredients, job.error_detail.ingredient_id);
  return `The grocery request failed. ${recipeName} needs ${ingredientName}, which is excluded. Clear the ${ingredientName} exclusion or choose another meal, then rebuild.`;
}
