# 0016 — Spoonacular prices at read time, user-entered budget

- Date: 2026-09-27
- Status: accepted
- Amends: [0010](0010-usda-spoonacular-overlay.md)

## Decision

The application shows a Spoonacular average for each purchased line and
for the plan total. Sample-catalog cents stay the budget figure. Plan
acceptance and `total_cents` MUST use sample-catalog cents.

The application MUST NOT store Spoonacular cents. That rule covers
PostgreSQL job rows, evidence records, and chat history. The API computes
the overlay when it serves a succeeded grocery or chat job. One provider
per API process keeps the one-hour in-memory cache.

The default spending source is `manual`. The monthly limit that the user
enters is the whole budget: 0 posted cents and 0 pending cents. `fixture`
and `plaid_sandbox` stay valid settings. Plaid work is the last feature
of the project.

USDA nutrition stays in `backend/app/domain/nutrition_catalog.py`. The
operator command `python -m app.usda_refresh` compares the stored facts to
FoodData Central. It writes no files.

## Why

Spoonacular terms allow a one-hour cache and forbid long-term storage of
prices. Before this decision, the worker wrote the Spoonacular total into
`jobs.result`. A read-time overlay keeps the terms and still shows the
price.

Spoonacular cost is a national average for the needed amount. It changes
over time and depends on a daily point quota. Budget acceptance on
Spoonacular cents would make evaluation results change between runs, and
an exhausted quota would block every plan.

The fixture spending source subtracted 18,000 posted cents. A user who
entered $100 saw $0 available.

## How it works

| Part | Location |
|---|---|
| Per-line overlay | `estimate_supermarket_cost`, `SupermarketLine` |
| Attach to a stored result | `attach_supermarket_estimate` in `backend/app/services/supermarket_overlay.py` |
| Provider per process | `get_supermarket_estimator` in `backend/app/deps.py` |
| Key file in Compose | `compose.spoonacular.yaml`, `api` only |
| UI | `estimate-line-spoonacular` rows in `frontend/src/Estimate.tsx` |
| Spending source | `SpendingSource` in `backend/app/domain/budget.py` |

The USDA command requests `format=full`. The `abridged` format rounds
values: black beans carbohydrate is 23.7 g there and 23.71 g in `full`.

## Consequences

- The Spoonacular line needs `-f compose.spoonacular.yaml` and a key file.
- Each first read of a finished job can call Spoonacular once per
  purchased line. Later reads within one hour use the cache.
- Local job rows written before this decision can still hold a stored
  Spoonacular total. Deleting them needs a separate retention decision.

This decision MUST NOT be read as a claim of live store prices.
