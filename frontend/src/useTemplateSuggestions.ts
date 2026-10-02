import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "./api";
import { HTTP_ERROR, SHAPE_ERROR, type GroceryConfig } from "./apiTypes";
import type { FormState } from "./BudgetForm";
import { parseDollars } from "./money";
import { fetchTemplates, type TemplateSuggestion } from "./templateApi";

export type TemplateSuggestionView = {
  pending: boolean;
  error: string | null;
  suggestions: TemplateSuggestion[] | null;
};

type Snapshot = TemplateSuggestionView & { key: string };

const EMPTY: TemplateSuggestionView = { pending: false, error: null, suggestions: null };

function contextKey(config: GroceryConfig, form: FormState, servings: number): string {
  return JSON.stringify({
    monthly: form.monthly,
    cap: form.cap,
    meals: form.meals,
    diet: form.diet,
    pantry: form.pantry,
    exclusions: form.exclusions,
    servings,
    budget_period: config.budget_period,
    source: config.source,
    catalog_version: config.catalog_version,
    posted_cents: config.posted_cents,
    pending_cents: config.pending_cents,
    spending_refreshed_at: config.spending_refreshed_at,
    notice: config.notice,
    recipes: config.recipes.map((item) => ({ id: item.id, name: item.name })),
    ingredients: config.ingredients.map((item) => ({ id: item.id, name: item.name })),
  });
}

function requestError(caught: unknown): string {
  return caught instanceof Error && caught.message === SHAPE_ERROR ? SHAPE_ERROR : HTTP_ERROR;
}

function viewFor(snapshot: Snapshot, key: string): TemplateSuggestionView {
  return snapshot.key === key
    ? { pending: snapshot.pending, error: snapshot.error, suggestions: snapshot.suggestions }
    : EMPTY;
}

export function useTemplateSuggestions(
  config: GroceryConfig,
  form: FormState,
  servings: number,
): TemplateSuggestionView & { find: () => void } {
  const key = contextKey(config, form, servings);
  const [snapshot, setSnapshot] = useState<Snapshot>({ key, ...EMPTY });
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      generationRef.current += 1;
      abortRef.current?.abort();
    };
  }, [key]);

  const find = useCallback((): void => {
    const requestKey = contextKey(config, form, servings);
    generationRef.current += 1;
    abortRef.current?.abort();
    let monthlyLimitCents: number;
    let planCapCents: number | null;
    try {
      const monthly = parseDollars(form.monthly);
      planCapCents = parseDollars(form.cap, true);
      if (monthly === null) {
        throw new Error("Enter a non-negative dollar amount with at most two decimal places.");
      }
      monthlyLimitCents = monthly;
    } catch (caught: unknown) {
      abortRef.current = null;
      setSnapshot({
        key: requestKey,
        pending: false,
        error: caught instanceof Error ? caught.message : HTTP_ERROR,
        suggestions: null,
      });
      return;
    }
    const generation = generationRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    setSnapshot({ key: requestKey, pending: true, error: null, suggestions: null });
    void fetchTemplates(
      {
        budget_period: config.budget_period,
        monthly_limit_cents: monthlyLimitCents,
        plan_cap_cents: planCapCents,
        servings,
        diet: form.diet,
        pantry_ingredients: [...form.pantry],
        ingredient_exclusions: [...form.exclusions],
      },
      config,
      controller.signal,
    ).then(
      (result) => {
        if (generation !== generationRef.current || controller.signal.aborted) {
          return;
        }
        setSnapshot({
          key: requestKey,
          pending: false,
          error: null,
          suggestions: [...result.suggestions],
        });
      },
      (caught: unknown) => {
        if (generation !== generationRef.current || isAbortError(caught)) {
          return;
        }
        setSnapshot({
          key: requestKey,
          pending: false,
          error: requestError(caught),
          suggestions: null,
        });
      },
    );
  }, [config, form, servings]);

  return { ...viewFor(snapshot, key), find };
}
