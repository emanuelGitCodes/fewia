import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";

export type Unit = "g" | "each";
export type RecipeId = "bean_tacos" | "egg_fried_rice" | "chickpea_curry";
export type Ingredient = {
  id: string;
  name: string;
  unit: Unit;
  packageQuantity: number;
  priceCents: number;
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
  image: string;
  // Each pair is an ingredient id and a per-serving quantity.
  ingredients: ReadonlyArray<readonly [string, number]>;
  // Nutrition stays per serving. Servings and pantry do not change it.
  nutrition: Nutrition;
};

export const ESTIMATE_NOTICE = SAMPLE_ESTIMATE_NOTICE;
export const DEMO_NOTICE = "Demo data";
export const NUTRITION_DEMO_LABEL = "Demo estimates";
export const SERVING_ERROR = "Each meal uses 1 to 8 servings.";
export const MIN_SERVINGS = 1;
export const MAX_SERVINGS = 8;
export const INITIAL_SERVINGS = 2;
export const INITIAL_BUDGET_INPUT = "40";
export const INITIAL_BUDGET_CENTS = 4000;
export const INITIAL_PANTRY: readonly string[] = ["olive_oil", "salt", "cumin"];
export const RECIPE_ORDER: readonly RecipeId[] = [
  "bean_tacos",
  "egg_fried_rice",
  "chickpea_curry",
];

// packageQuantity is the catalog package size in the ingredient unit.
const ROWS: ReadonlyArray<readonly [string, string, Unit, number, number]> = [
  ["black_beans", "black beans", "g", 425, 129],
  ["tortillas", "corn tortillas", "each", 8, 299],
  ["salsa", "salsa", "g", 454, 249],
  ["onion", "onion", "g", 454, 129],
  ["cumin", "ground cumin", "g", 42, 199],
  ["olive_oil", "olive oil", "g", 500, 599],
  ["salt", "salt", "g", 737, 99],
  ["eggs", "eggs", "each", 12, 349],
  ["rice", "white rice", "g", 907, 199],
  ["mixed_vegetables", "mixed vegetables", "g", 454, 199],
  ["soy_sauce", "soy sauce", "g", 296, 199],
  ["garlic", "garlic", "g", 100, 89],
  ["chickpeas", "chickpeas", "g", 425, 129],
  ["coconut_milk", "coconut milk", "g", 400, 249],
  ["curry_powder", "curry powder", "g", 42, 249],
];

export const INGREDIENTS: Record<string, Ingredient> = {};
for (const [id, name, unit, packageQuantity, priceCents] of ROWS) {
  INGREDIENTS[id] = { id, name, unit, packageQuantity, priceCents };
}

function meal(
  id: RecipeId,
  name: string,
  file: string,
  ingredients: ReadonlyArray<readonly [string, number]>,
  nutrition: Nutrition,
): Recipe {
  return { id, name, image: `/prototype/${file}`, ingredients, nutrition };
}

// Recipe quantities use the same unit as packageQuantity. The nutrition values
// are per serving from the USDA values in backend/app/services/meal_nutrition.py.
export const RECIPES: Record<RecipeId, Recipe> = {
  bean_tacos: meal(
    "bean_tacos",
    "Bean tacos",
    "bean-tacos.webp",
    [
      ["black_beans", 120],
      ["tortillas", 2],
      ["salsa", 40],
      ["onion", 30],
      ["cumin", 1],
      ["olive_oil", 10],
      ["salt", 1],
    ],
    { energyKcal: 379, proteinG: 14.5, carbsG: 55.8, fatG: 12.3 },
  ),
  egg_fried_rice: meal(
    "egg_fried_rice",
    "Egg fried rice",
    "egg-fried-rice.webp",
    [
      ["eggs", 2],
      ["rice", 75],
      ["mixed_vegetables", 80],
      ["soy_sauce", 15],
      ["onion", 30],
      ["garlic", 5],
      ["olive_oil", 10],
    ],
    { energyKcal: 590, proteinG: 22.4, carbsG: 76.7, fatG: 20.6 },
  ),
  chickpea_curry: meal(
    "chickpea_curry",
    "Chickpea curry",
    "chickpea-curry.webp",
    [
      ["chickpeas", 120],
      ["coconut_milk", 80],
      ["rice", 75],
      ["onion", 40],
      ["garlic", 5],
      ["curry_powder", 3],
      ["olive_oil", 10],
      ["salt", 1],
    ],
    { energyKcal: 750, proteinG: 18.8, carbsG: 102.2, fatG: 31.2 },
  ),
};

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
