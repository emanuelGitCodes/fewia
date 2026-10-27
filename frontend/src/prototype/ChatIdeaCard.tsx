import { useId, type JSX } from "react";
import { formatDollars } from "../money";
import { MealPhoto } from "./PlanMeals";
import { planCost, planIncomplete, previewAdd, type PlanState } from "./planModel";
import { planFitLine } from "./PlanSummary";
import { DIET_LABELS, MAX_MEALS, RECIPES, isKnownRecipe } from "./prototypeData";
import { formatMacro } from "./prototypeModel";

function joinNames(names: string[]): string {
  const lower = names.map((name) => name.toLowerCase());
  if (lower.length <= 1) {
    return lower.join("");
  }
  return `${lower.slice(0, -1).join(", ")} and ${lower[lower.length - 1] ?? ""}`;
}

export function ChatIdeaCard(props: {
  recipeId: string;
  servings: number;
  state: PlanState;
  onToggle: (recipeId: string, servings: number, inPlan: boolean) => void;
}): JSX.Element | null {
  const { recipeId, state } = props;
  const uid = useId();
  if (!isKnownRecipe(recipeId)) {
    return null;
  }
  const recipe = RECIPES[recipeId];
  const preview = previewAdd(state, recipeId, props.servings);
  const { inPlan } = preview;
  // The preview holds the servings the plan shows or addMeal would use.
  const servings = preview.servings;
  const full = preview.blocked === "plan_full";
  const over = !planIncomplete(preview.lines) && planCost(preview.lines) > state.budgetCents;
  const nameId = `${uid}-name`;
  const noteId = `${uid}-note`;
  const diets = recipe.diets.map((d) => DIET_LABELS[d]).join(" · ");
  const count = `${String(servings)} ${servings === 1 ? "serving" : "servings"}`;
  const delta = `${preview.deltaCents < 0 ? "−" : "+"}${formatDollars(Math.abs(preview.deltaCents))}`;
  const label = inPlan
    ? `Remove ${recipe.name} from plan`
    : `Add ${recipe.name}, ${count}, plus ${formatDollars(preview.deltaCents)}, to plan`;
  const buttonText = full ? `Plan has ${String(MAX_MEALS)} meals` : inPlan ? "In your plan" : "Add to plan";
  return (
    <article
      className={inPlan ? "tonight-idea-card is-selected" : "tonight-idea-card"}
      aria-labelledby={nameId}
    >
      <MealPhoto src={recipe.image} alt="" className="tonight-thumb" />
      <h3 id={nameId}>{recipe.name}</h3>
      {diets !== "" ? <p className="tonight-diets">{diets}</p> : null}
      <p className="tonight-idea-facts">
        {`${count} · ${formatMacro(recipe.nutrition.proteinG)} g protein each`}
      </p>
      <p className="tonight-idea-delta">
        <strong>{delta}</strong>
        <span className={over ? "tonight-idea-over" : undefined}>
          {planFitLine(preview.lines, state.budgetCents)}
        </span>
      </p>
      {preview.sharedIngredientNames.length > 0 ? (
        <p className="tonight-idea-why">
          {`Shares ${joinNames(preview.sharedIngredientNames)} with your plan.`}
        </p>
      ) : null}
      <button
        type="button"
        className="tonight-idea-btn"
        aria-pressed={inPlan}
        aria-label={full ? undefined : label}
        aria-describedby={full ? noteId : undefined}
        disabled={full}
        onClick={() => { props.onToggle(recipeId, servings, inPlan); }}
      >
        {buttonText}
      </button>
      {full ? <p id={noteId} className="tonight-idea-why">Remove a meal to add this one.</p> : null}
    </article>
  );
}
