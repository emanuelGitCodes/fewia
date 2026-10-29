import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import catalogJson from "./catalog.generated.json";

export type Unit = "g" | "each";
export type RecipeId = string;
export type Diet = "vegan" | "vegetarian";
export const DIET_LABELS: Record<Diet, string> = {
  vegan: "Vegan",
  vegetarian: "Vegetarian",
};
export type Tag =
  | "chicken"
  | "egg"
  | "beans"
  | "lentils"
  | "chickpeas"
  | "high_protein"
  | "lower_carb"
  | "gluten_free_ingredients";
export const TAG_LABELS: Record<Tag, string> = {
  chicken: "Chicken",
  egg: "Egg",
  beans: "Beans",
  lentils: "Lentils",
  chickpeas: "Chickpeas",
  high_protein: "High protein",
  lower_carb: "Lower carb",
  gluten_free_ingredients: "Gluten-free ingredients",
};
export type Ingredient = {
  id: string;
  name: string;
  unit: Unit;
  packageQuantity: number;
  // null means the catalog has no sample price for the package.
  priceCents: number | null;
  isPantry: boolean;
};
export type Nutrition = {
  energyKcal: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
};
export type Recipe = {
  id: RecipeId;
  name: string;
  image: string | null;
  diets: readonly Diet[];
  tags: readonly Tag[];
  // Each pair is an ingredient id and a per-serving quantity.
  ingredients: ReadonlyArray<readonly [string, number]>;
  // Nutrition stays per serving. Servings and pantry do not change it.
  nutrition: Nutrition;
};

// catalog.generated.json is written by the backend command
// `python -m app.prototype_catalog_export`. Do not edit it by hand.
type CatalogJson = {
  catalogVersion: string;
  ingredients: Ingredient[];
  recipes: Array<{
    id: string;
    name: string;
    diets: Diet[];
    tags: Tag[];
    ingredients: Array<[string, number]>;
    nutrition: Nutrition;
  }>;
  searchTerms: Record<string, { target: Diet | Tag; note: string | null }>;
};
const CATALOG = catalogJson as unknown as CatalogJson;

// Search terms come from the backend, with the tag rules they point at.
export const CATALOG_SEARCH_TERMS: Readonly<
  Record<string, { target: Diet | Tag; note: string | null }>
> = CATALOG.searchTerms;

export const ESTIMATE_NOTICE = SAMPLE_ESTIMATE_NOTICE;
export const DEMO_NOTICE = "Demo data";
export const NUTRITION_DEMO_LABEL = "Demo estimates";
export const SERVING_ERROR = "Each meal uses 1 to 8 servings.";
export const MIN_SERVINGS = 1;
export const MAX_SERVINGS = 8;
export const INITIAL_SERVINGS = 2;
export const MAX_MEALS = 3;
export const INITIAL_BUDGET_INPUT = "40";
export const INITIAL_BUDGET_CENTS = 4000;

// Map each catalog recipe to its local photo file.
const PHOTOS: Readonly<Record<string, string>> = {
  bean_tacos: "bean-tacos.webp",
  chicken_tacos: "chicken-tacos.webp",
  vegetable_pasta: "vegetable-pasta.webp",
  chicken_and_rice_bowls: "chicken-and-rice-bowls.webp",
  lentil_soup: "lentil-soup.webp",
  chickpea_curry: "chickpea-curry.webp",
  vegetable_stir_fry: "vegetable-stir-fry.webp",
  baked_potatoes_with_beans: "baked-potatoes-with-beans.webp",
  breakfast_burritos: "breakfast-burritos.webp",
  overnight_oats: "overnight-oats.webp",
  chicken_pasta: "chicken-pasta.webp",
  chicken_stir_fry: "chicken-stir-fry.webp",
  chicken_curry: "chicken-curry.webp",
  chicken_vegetable_soup: "chicken-vegetable-soup.webp",
  chicken_burrito_bowls: "chicken-burrito-bowls.webp",
  chicken_potato_bake: "chicken-potato-bake.webp",
  chicken_lentil_stew: "chicken-lentil-stew.webp",
  chicken_chickpea_skillet: "chicken-chickpea-skillet.webp",
  chicken_fried_rice: "chicken-fried-rice.webp",
  chicken_tortilla_soup: "chicken-tortilla-soup.webp",
  egg_fried_rice: "egg-fried-rice.webp",
  egg_tacos: "egg-tacos.webp",
  tomato_egg_pasta: "tomato-egg-pasta.webp",
  potato_hash_with_eggs: "potato-hash-with-eggs.webp",
  chickpea_egg_scramble: "chickpea-egg-scramble.webp",
  vegetable_egg_stir_fry: "vegetable-egg-stir-fry.webp",
  egg_rice_bowls: "egg-rice-bowls.webp",
  lentil_egg_skillet: "lentil-egg-skillet.webp",
  rice_and_beans: "rice-and-beans.webp",
  lentil_pasta: "lentil-pasta.webp",
  chickpea_tacos: "chickpea-tacos.webp",
  potato_curry: "potato-curry.webp",
  tomato_rice: "tomato-rice.webp",
  garlic_tomato_pasta: "garlic-tomato-pasta.webp",
  vegetable_soup: "vegetable-soup.webp",
  lentil_tacos: "lentil-tacos.webp",
  chickpea_pasta: "chickpea-pasta.webp",
  coconut_lentil_curry: "coconut-lentil-curry.webp",
  potato_tacos: "potato-tacos.webp",
  salsa_rice_bowls: "salsa-rice-bowls.webp",
};

export const INITIAL_PANTRY: readonly string[] = CATALOG.ingredients
  .filter((item) => item.isPantry)
  .map((item) => item.id);
export const RECIPE_ORDER: readonly RecipeId[] = CATALOG.recipes.map((recipe) => recipe.id);

// packageQuantity is the catalog package size in the ingredient unit.
export const INGREDIENTS: Record<string, Ingredient> = {};
for (const item of CATALOG.ingredients) {
  INGREDIENTS[item.id] = item;
}

// Recipe quantities use the same unit as packageQuantity. The nutrition values
// are per serving and come from the backend.
export const RECIPES: Record<RecipeId, Recipe> = {};
for (const recipe of CATALOG.recipes) {
  const file = PHOTOS[recipe.id];
  RECIPES[recipe.id] = {
    id: recipe.id,
    name: recipe.name,
    image: file === undefined ? null : `/prototype/${file}`,
    diets: recipe.diets,
    tags: recipe.tags,
    ingredients: recipe.ingredients,
    nutrition: recipe.nutrition,
  };
}

// RECIPES is a plain object, so an inherited key such as "constructor" is not a recipe.
export function isKnownRecipe(id: string): boolean {
  return Object.prototype.hasOwnProperty.call(RECIPES, id);
}

// Diet labels first, then tag labels.
export function mealLabels(recipe: Recipe): string[] {
  return [...recipe.diets.map((d) => DIET_LABELS[d]), ...recipe.tags.map((t) => TAG_LABELS[t])];
}

export function requireIngredient(id: string): Ingredient {
  const item = INGREDIENTS[id];
  if (item === undefined) {
    throw new Error(`Unknown catalog ingredient: ${id}`);
  }
  return item;
}

export const PANTRY_IDS: string[] = [];
for (const recipeId of RECIPE_ORDER) {
  for (const [ingredientId] of RECIPES[recipeId].ingredients) {
    if (!PANTRY_IDS.includes(ingredientId)) {
      PANTRY_IDS.push(ingredientId);
    }
  }
}
