import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";

export type Unit = "g" | "each";
export type RecipeId =
  | "bean_tacos"
  | "egg_fried_rice"
  | "chickpea_curry"
  | "lemon_salmon_rice"
  | "tofu_stir_fry"
  | "garlic_chicken_broccoli"
  | "spinach_parmesan_pasta"
  | "black_bean_quinoa_bowl"
  | "chicken_potato_bake"
  | "spinach_mushroom_omelette";
export type Diet = "vegan" | "vegetarian" | "pescatarian" | "keto" | "gluten_free";
export const DIET_LABELS: Record<Diet, string> = {
  vegan: "Vegan",
  vegetarian: "Vegetarian",
  pescatarian: "Pescatarian",
  keto: "Keto",
  gluten_free: "Gluten-free",
};
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
  image: string | null;
  diets: readonly Diet[];
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
export const MAX_MEALS = 3;
export const INITIAL_BUDGET_INPUT = "40";
export const INITIAL_BUDGET_CENTS = 4000;
export const INITIAL_PANTRY: readonly string[] = ["olive_oil", "salt", "cumin"];
export const RECIPE_ORDER: readonly RecipeId[] = [
  "bean_tacos",
  "egg_fried_rice",
  "chickpea_curry",
  "lemon_salmon_rice",
  "tofu_stir_fry",
  "garlic_chicken_broccoli",
  "spinach_parmesan_pasta",
  "black_bean_quinoa_bowl",
  "chicken_potato_bake",
  "spinach_mushroom_omelette",
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
  ["salmon", "salmon fillet", "g", 454, 999],
  ["lemon", "lemon", "each", 1, 69],
  ["tofu", "firm tofu", "g", 396, 229],
  ["broccoli", "broccoli", "g", 340, 249],
  ["chicken_breast", "chicken breast", "g", 680, 699],
  ["butter", "butter", "g", 454, 449],
  ["pasta", "pasta", "g", 454, 149],
  ["spinach", "spinach", "g", 283, 299],
  ["parmesan", "parmesan", "g", 142, 399],
  ["quinoa", "quinoa", "g", 340, 399],
  ["potatoes", "potatoes", "g", 2268, 399],
  ["mushrooms", "mushrooms", "g", 227, 249],
];

export const INGREDIENTS: Record<string, Ingredient> = {};
for (const [id, name, unit, packageQuantity, priceCents] of ROWS) {
  INGREDIENTS[id] = { id, name, unit, packageQuantity, priceCents };
}

function meal(
  id: RecipeId,
  name: string,
  file: string | null,
  ingredients: ReadonlyArray<readonly [string, number]>,
  nutrition: Nutrition,
  diets: readonly Diet[],
): Recipe {
  const image = file === null ? null : `/prototype/${file}`;
  return { id, name, image, diets, ingredients, nutrition };
}

// Recipe quantities use the same unit as packageQuantity. The nutrition values
// are per serving. The 3 original recipes use USDA values from
// backend/app/services/meal_nutrition.py; the other values are demo estimates.
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
    ["vegan", "gluten_free"],
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
    ["vegetarian"],
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
    ["vegan", "gluten_free"],
  ),
  lemon_salmon_rice: meal(
    "lemon_salmon_rice",
    "Lemon salmon and rice",
    null,
    [
      ["salmon", 150],
      ["rice", 75],
      ["lemon", 1],
      ["garlic", 5],
      ["olive_oil", 10],
      ["salt", 1],
    ],
    { energyKcal: 690, proteinG: 35.6, carbsG: 66.0, fatG: 30.4 },
    ["pescatarian", "gluten_free"],
  ),
  tofu_stir_fry: meal(
    "tofu_stir_fry",
    "Tofu stir-fry",
    null,
    [
      ["tofu", 150],
      ["mixed_vegetables", 100],
      ["rice", 75],
      ["soy_sauce", 15],
      ["garlic", 5],
      ["olive_oil", 10],
    ],
    { energyKcal: 665, proteinG: 35.5, carbsG: 80.3, fatG: 23.5 },
    ["vegan"],
  ),
  garlic_chicken_broccoli: meal(
    "garlic_chicken_broccoli",
    "Garlic chicken and broccoli",
    null,
    [
      ["chicken_breast", 170],
      ["broccoli", 150],
      ["butter", 15],
      ["garlic", 5],
      ["olive_oil", 10],
      ["salt", 1],
    ],
    { energyKcal: 460, proteinG: 42.4, carbsG: 11.6, fatG: 27.3 },
    ["keto", "gluten_free"],
  ),
  spinach_parmesan_pasta: meal(
    "spinach_parmesan_pasta",
    "Spinach parmesan pasta",
    null,
    [
      ["pasta", 100],
      ["spinach", 60],
      ["parmesan", 20],
      ["garlic", 5],
      ["olive_oil", 10],
      ["salt", 1],
    ],
    { energyKcal: 558, proteinG: 22.2, carbsG: 79.4, fatG: 16.9 },
    ["vegetarian"],
  ),
  black_bean_quinoa_bowl: meal(
    "black_bean_quinoa_bowl",
    "Black bean quinoa bowl",
    null,
    [
      ["quinoa", 60],
      ["black_beans", 120],
      ["salsa", 40],
      ["onion", 30],
      ["cumin", 1],
      ["olive_oil", 10],
      ["salt", 1],
    ],
    { energyKcal: 450, proteinG: 16.0, carbsG: 64.6, fatG: 14.4 },
    ["vegan", "gluten_free"],
  ),
  chicken_potato_bake: meal(
    "chicken_potato_bake",
    "Chicken potato bake",
    null,
    [
      ["chicken_breast", 150],
      ["potatoes", 250],
      ["onion", 40],
      ["garlic", 5],
      ["olive_oil", 15],
      ["salt", 1],
    ],
    { energyKcal: 528, proteinG: 39.5, carbsG: 49.1, fatG: 19.2 },
    ["gluten_free"],
  ),
  spinach_mushroom_omelette: meal(
    "spinach_mushroom_omelette",
    "Spinach mushroom omelette",
    null,
    [
      ["eggs", 3],
      ["spinach", 40],
      ["mushrooms", 60],
      ["butter", 10],
      ["salt", 1],
    ],
    { energyKcal: 310, proteinG: 21.9, carbsG: 4.5, fatG: 22.6 },
    ["vegetarian", "keto", "gluten_free"],
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
