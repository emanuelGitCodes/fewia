import type { MacroTotals, MealPlanNutrition } from "./nutritionTypes";
import "./nutrition.css";

export type NutritionProps = {
  nutrition: MealPlanNutrition | undefined;
  dirty: boolean;
};

const USDA_HREF = "https://fdc.nal.usda.gov/";
const PREP_CAVEAT =
  "Estimates use recipe ingredients. Actual sizes and preparation vary.";

function kcal(value: number): string {
  return `${value.toLocaleString("en-US")} kcal`;
}

function grams(mg: number): string {
  return `${(mg / 1000).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} g`;
}

function recipeLabel(recipeId: string): string {
  return recipeId.split("_").filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function MacroList({ values }: { values: MacroTotals }): JSX.Element {
  const rows: Array<[string, string]> = [
    ["Calories (kcal)", kcal(values.energy_kcal)],
    ["Protein (g)", grams(values.protein_mg)],
    ["Carbs (g)", grams(values.carbohydrate_mg)],
    ["Fat (g)", grams(values.fat_mg)],
  ];
  return (
    <dl className="nutrition-macros">
      {rows.map(([label, value]) => (
        <div className="nutrition-macro" key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Nutrition({ nutrition, dirty }: NutritionProps): JSX.Element {
  const heading = dirty ? "Nutrition for previous plan" : "Estimated nutrition";
  if (nutrition === undefined) {
    return (
      <section className="nutrition" aria-labelledby="nutrition-heading">
        <h3 id="nutrition-heading">{heading}</h3>
        <p className="nutrition-status" role="status" aria-live="polite">
          Rebuild this plan to see nutrition.
        </p>
      </section>
    );
  }
  if (nutrition.total === null) {
    return (
      <section className="nutrition" aria-labelledby="nutrition-heading">
        <h3 id="nutrition-heading">{heading}</h3>
        <p className="nutrition-status" role="status" aria-live="polite">
          Nutrition is unavailable for this plan.
        </p>
      </section>
    );
  }
  return (
    <section className="nutrition" aria-labelledby="nutrition-heading">
      <h3 id="nutrition-heading">{heading}</h3>
      {dirty ? (
        <p className="nutrition-status" role="status" aria-live="polite">
          These values belong to the last saved plan.
        </p>
      ) : null}
      <h4 className="nutrition-subheading">Total for selected plan</h4>
      <MacroList values={nutrition.total} />
      {nutrition.meals.map((meal, index) => (
        <article className="nutrition-meal" key={`${meal.recipe_id}-${index}`}>
          <h4 className="nutrition-subheading">{recipeLabel(meal.recipe_id)}</h4>
          <p className="nutrition-servings">{`${meal.servings} ${meal.servings === 1 ? "serving" : "servings"}`}</p>
          <p className="nutrition-per-serving">Per serving</p>
          <MacroList values={meal.per_serving} />
        </article>
      ))}
      <p className="nutrition-notice">{nutrition.notice}</p>
      <a className="nutrition-usda" href={USDA_HREF} rel="noopener noreferrer" target="_blank">
        USDA FoodData Central
      </a>
      <details className="nutrition-notes">
        <summary>Portion and preparation notes</summary>
        <p>{nutrition.portion_notice}</p>
        <p>{PREP_CAVEAT}</p>
      </details>
    </section>
  );
}
