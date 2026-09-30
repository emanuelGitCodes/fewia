import type { CatalogItem, MacroTotals, MealPlanNutrition } from "./apiTypes";

function formatGrams(mg: number): string {
  return `${(Math.round(mg / 100) / 10).toFixed(1)} g`;
}

function formatMacros(macros: MacroTotals): string {
  return `${macros.energy_kcal} kcal, ${formatGrams(macros.protein_mg)} protein, ${formatGrams(macros.carbohydrate_mg)} carbohydrate, ${formatGrams(macros.fat_mg)} fat`;
}

export function Nutrition(props: {
  nutrition: MealPlanNutrition;
  recipes: CatalogItem[];
}): JSX.Element {
  const { nutrition, recipes } = props;
  return (
    <section className="nutrition" aria-labelledby="nutrition-heading">
      <h3 id="nutrition-heading">Estimated nutrition</h3>
      {nutrition.total !== null ? (
        <p className="nutrition-plan-total">{`Plan total ${formatMacros(nutrition.total)}`}</p>
      ) : null}
      <ul className="nutrition-meals">
        {nutrition.meals.map((meal) => {
          const name =
            recipes.find((item) => item.id === meal.recipe_id)?.name ?? meal.recipe_id;
          return (
            <li key={`${meal.recipe_id}-${String(meal.servings)}`} className="nutrition-meal">
              <p className="nutrition-meal-name">{name}</p>
              <p className="nutrition-meal-servings">{`${meal.servings} ${meal.servings === 1 ? "serving" : "servings"}`}</p>
              <p className="nutrition-meal-per-serving">{`Per serving ${formatMacros(meal.per_serving)}`}</p>
              <p className="nutrition-meal-total">{`Meal total ${formatMacros(meal.total)}`}</p>
            </li>
          );
        })}
      </ul>
      <p className="nutrition-notice">{nutrition.notice}</p>
      <p className="nutrition-portion-notice">{nutrition.portion_notice}</p>
    </section>
  );
}
