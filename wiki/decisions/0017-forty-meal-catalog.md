# 0017 — Forty-meal sample catalog

- Date: 2026-10-02
- Status: accepted
- Amends: the planning rules in [`.codex/project-context.md`](../../.codex/project-context.md)

## Decision

The planner supports 40 meals. The ten original meals stay with the same
quantities and prices. The authoritative list is
`backend/app/domain/catalog_recipes.json`. `SUPPORTED_RECIPE_IDS` in
`backend/app/domain/grocery.py` holds the same 40 IDs.

The catalog version is `sample-prices-v2`. An evaluation MUST freeze this
version with the model and the prompts.

Every new meal uses only the 22 existing ingredients. Each ingredient has a
sample price, a USDA FoodData Central record, and a Spoonacular ID. A meal
is vegan or vegetarian only when every ingredient is. The planner derives
the diet from the ingredients. No meal carries its own diet label.

The other planning rules do not change: one to three meals, one to eight
servings for each meal, and supported alternatives for other requests.

## Why

Ten meals left many common requests outside the catalog, for example
chicken curry or egg fried rice. The chat then had to refuse or offer an
alternative for ordinary requests. More meals that reuse the 22 priced
ingredients give more choices with no new price, nutrition, or Spoonacular
data.

## How it works

| Part | Location |
|---|---|
| Meal list and quantities | `backend/app/domain/catalog_recipes.json` |
| Supported IDs | `SUPPORTED_RECIPE_IDS` in `backend/app/domain/grocery.py` |
| Catalog version | `CATALOG_VERSION` in `backend/app/domain/catalog.py` |
| Meal names in the UI | `GET /grocery/config`, from the recipe ID |
| Evaluation corpus | `backend/tests/evaluation/scenarios.json` |

Pull request [#233](https://github.com/emanuelGitCodes/fewia/pull/233)
adds the 30 new meals. Pull request
[#244](https://github.com/emanuelGitCodes/fewia/pull/244) updates
`.codex/project-context.md` to match.

## Options considered

- Keep ten meals. The catalog stays small, and more requests need an
  alternative.
- Add meals with new ingredients. Each new ingredient needs a sample
  price, a USDA record, and a Spoonacular ID.

## Consequences

- An evaluation result for `sample-prices-v1` does not compare directly
  with a result for `sample-prices-v2`.
- Until #244 merges, `.codex/project-context.md` still lists ten meals.
  This decision overrides that list.
