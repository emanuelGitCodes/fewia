import { readJson } from "./api";
import {
  SAMPLE_ESTIMATE_NOTICE,
  SHAPE_ERROR,
  isNonemptyString,
  isRecord,
  isSafeInteger,
  type Diet,
  type GroceryBudget,
  type GroceryConfig,
  type SpendingSource,
} from "./apiTypes";
import { isBudget } from "./apiValidation";

export type TemplateRequest = {
  budget_period: string;
  monthly_limit_cents: number;
  plan_cap_cents: number | null;
  servings: number;
  diet: Diet;
  pantry_ingredients: string[];
  ingredient_exclusions: string[];
};

export type TemplateSuggestion = {
  template_id: string;
  recipe_ids: string[];
  servings: number;
  total_cents: number;
  catalog_version: string;
  notice: string;
};

export type TemplateSuggestions = {
  budget_period: string;
  spending_source: SpendingSource;
  budget: GroceryBudget;
  catalog_version: string;
  notice: string;
  suggestions: TemplateSuggestion[];
};

function fail(): never {
  throw new Error(SHAPE_ERROR);
}

function copySuggestion(
  value: unknown,
  config: GroceryConfig,
  request: TemplateRequest,
  availableCents: number,
  knownRecipes: ReadonlySet<string>,
  seenIds: Set<string>,
): TemplateSuggestion {
  if (!isRecord(value) || !isNonemptyString(value.template_id) || seenIds.has(value.template_id)) {
    fail();
  }
  if (!Array.isArray(value.recipe_ids) || value.recipe_ids.length < 1 || value.recipe_ids.length > 3) {
    fail();
  }
  const recipeIds: string[] = [];
  for (const recipeId of value.recipe_ids) {
    if (!isNonemptyString(recipeId) || !knownRecipes.has(recipeId)) {
      fail();
    }
    recipeIds.push(recipeId);
  }
  const servings = value.servings;
  const totalCents = value.total_cents;
  if (
    !isSafeInteger(servings) ||
    servings < 1 ||
    servings > 8 ||
    servings !== request.servings ||
    !isSafeInteger(totalCents) ||
    totalCents < 0 ||
    totalCents > availableCents ||
    value.catalog_version !== config.catalog_version ||
    value.notice !== SAMPLE_ESTIMATE_NOTICE
  ) {
    fail();
  }
  seenIds.add(value.template_id);
  return {
    template_id: value.template_id,
    recipe_ids: recipeIds,
    servings,
    total_cents: totalCents,
    catalog_version: config.catalog_version,
    notice: SAMPLE_ESTIMATE_NOTICE,
  };
}

export function parseTemplateSuggestions(
  value: unknown,
  config: GroceryConfig,
  request: TemplateRequest,
): TemplateSuggestions {
  if (
    !isRecord(value) ||
    value.budget_period !== request.budget_period ||
    value.budget_period !== config.budget_period ||
    value.spending_source !== config.source ||
    value.catalog_version !== config.catalog_version ||
    value.notice !== SAMPLE_ESTIMATE_NOTICE ||
    !isBudget(value.budget)
  ) {
    fail();
  }
  const cap = request.plan_cap_cents;
  if (cap !== null && value.budget.available_cents > cap) {
    fail();
  }
  if (!Array.isArray(value.suggestions) || value.suggestions.length > 6) {
    fail();
  }
  const knownRecipes = new Set(config.recipes.map((recipe) => recipe.id));
  const seenIds = new Set<string>();
  const availableCents = value.budget.available_cents;
  return {
    budget_period: request.budget_period,
    spending_source: config.source,
    budget: {
      available_cents: value.budget.available_cents,
      pending_cents: value.budget.pending_cents,
      stale: value.budget.stale,
      warnings: [...value.budget.warnings],
    },
    catalog_version: config.catalog_version,
    notice: SAMPLE_ESTIMATE_NOTICE,
    suggestions: value.suggestions.map((item) =>
      copySuggestion(item, config, request, availableCents, knownRecipes, seenIds),
    ),
  };
}

export async function fetchTemplates(
  request: TemplateRequest,
  config: GroceryConfig,
  signal?: AbortSignal,
): Promise<TemplateSuggestions> {
  const body = await readJson("/api/grocery/templates", {
    method: "POST",
    signal,
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
  });
  return parseTemplateSuggestions(body, config, request);
}
