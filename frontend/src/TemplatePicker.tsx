import { useRef, useState, type Dispatch, type JSX, type SetStateAction } from "react";
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
  const findButtonRef = useRef<HTMLButtonElement>(null);
  const { pending, error, suggestions, find } = useTemplateSuggestions(
    config,
    form,
    servings,
  );
  const renderedSuggestions = (suggestions ?? []).flatMap((suggestion) => {
    const names = recipeNames(config, suggestion.recipe_ids);
    return names.length === suggestion.recipe_ids.length ? [{ suggestion, names }] : [];
  });
  let status = "";
  if (pending) {
    status = "Finding meal ideas.";
  } else if (suggestions !== null) {
    const count = renderedSuggestions.length;
    status = count === 0
      ? "No meal idea fits these restrictions. Choose meals manually."
      : `${count} meal ${count === 1 ? "idea" : "ideas"} found.`;
  }
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
      <button
        ref={findButtonRef}
        type="button"
        disabled={disabled}
        aria-disabled={pending}
        onClick={requestIdeas}
      >
        Find meal ideas
      </button>
      <p>{GUIDANCE}</p>
      <p
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className={status === "" ? "visually-hidden" : undefined}
      >
        {status}
      </p>
      {error !== null ? (
        <>
          <p role="alert">{error}</p>
          <button
            type="button"
            onClick={() => {
              if (disabled || pending) {
                return;
              }
              findButtonRef.current?.focus();
              requestIdeas();
            }}
          >
            Retry meal ideas
          </button>
        </>
      ) : null}
      {renderedSuggestions.length > 0 ? (
        <>
          <ul>
            {renderedSuggestions.map(({ suggestion, names }) => {
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
