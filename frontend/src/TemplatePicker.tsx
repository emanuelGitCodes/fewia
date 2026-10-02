import { useState, type Dispatch, type JSX, type SetStateAction } from "react";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryConfig } from "./apiTypes";
import type { FormState } from "./BudgetForm";
import { formatDollars } from "./money";
import type { TemplateSuggestion } from "./templateApi";
import { useTemplateSuggestions } from "./useTemplateSuggestions";

const SERVINGS = [1, 2, 3, 4, 5, 6, 7, 8];
const GUIDANCE = "Use Build my estimate after choosing meals.";

type Props = {
  config: GroceryConfig;
  form: FormState;
  onChange: Dispatch<SetStateAction<FormState>>;
  disabled: boolean;
};

function recipeNames(config: GroceryConfig, ids: string[]): string[] {
  const names = new Map(config.recipes.map((item) => [item.id, item.name]));
  return ids.flatMap((id) => {
    const name = names.get(id);
    return name === undefined ? [] : [name];
  });
}

export function TemplatePicker({ config, form, onChange, disabled }: Props): JSX.Element {
  const [servings, setServings] = useState(2);
  const { pending, error, suggestions, find } = useTemplateSuggestions(
    config,
    form,
    servings,
  );
  const requestIdeas = (): void => {
    if (disabled || pending) {
      return;
    }
    find();
  };
  const apply = (suggestion: TemplateSuggestion): void => {
    if (disabled) {
      return;
    }
    onChange((current) => ({
      ...current,
      meals: suggestion.recipe_ids.map((recipe_id) => ({
        recipe_id,
        servings: suggestion.servings,
      })),
    }));
  };
  return (
    <fieldset disabled={disabled}>
      <legend>Meal ideas</legend>
      <label htmlFor="template-servings">Servings per meal</label>
      <select
        id="template-servings"
        value={servings}
        onChange={(event) => {
          setServings(Number(event.target.value));
        }}
      >
        {SERVINGS.map((count) => (
          <option key={count} value={count}>
            {count}
          </option>
        ))}
      </select>
      <button type="button" disabled={disabled || pending} onClick={requestIdeas}>
        Find meal ideas
      </button>
      <p>{GUIDANCE}</p>
      {pending ? (
        <p role="status" aria-live="polite">
          Finding meal ideas.
        </p>
      ) : null}
      {error !== null ? (
        <>
          <p role="alert">{error}</p>
          <button type="button" onClick={requestIdeas}>
            Retry meal ideas
          </button>
        </>
      ) : null}
      {suggestions !== null && suggestions.length === 0 ? (
        <p role="status">No meal idea fits these restrictions. Choose meals manually.</p>
      ) : null}
      {suggestions !== null && suggestions.length > 0 ? (
        <>
          <ul>
            {suggestions.map((suggestion) => {
              const names = recipeNames(config, suggestion.recipe_ids);
              if (names.length !== suggestion.recipe_ids.length) {
                return null;
              }
              return (
                <li key={suggestion.template_id}>
                  <p>{names.join(", ")}</p>
                  <p>{`${suggestion.servings} servings`}</p>
                  <p>{formatDollars(suggestion.total_cents)}</p>
                  <button
                    type="button"
                    aria-label={`Use these meals: ${names.join(", ")}`}
                    onClick={() => {
                      apply(suggestion);
                    }}
                  >
                    Use these meals
                  </button>
                </li>
              );
            })}
          </ul>
          <p>{SAMPLE_ESTIMATE_NOTICE}</p>
        </>
      ) : null}
    </fieldset>
  );
}
