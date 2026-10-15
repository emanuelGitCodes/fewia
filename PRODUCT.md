# FEWIA product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

The accepted project uses React and TypeScript, FastAPI, PostgreSQL, and local
Floci services. Real model calls use Amazon Bedrock. The shared scope lives in
[the project context](.codex/project-context.md).

## Users and purpose

The first release serves one local demo user who plans one to three meals
within a declared grocery budget. Each meal supports one to eight servings.
The user can declare pantry ingredients, exclusions, and a dietary preference.

The visual prototype targets adults aged 18 to 25. Its first task is to
choose a meal for tonight and read its grocery cost and nutrition facts.
The user approved the Familiar and Pantry Edit combination. The prototype
uses self-contained demo data at `/prototype`; the existing application
stays at `/`.

## Operating context

The application runs locally through Docker Compose. The default spending
source is `manual`. The monthly limit that the user enters is the whole
budget. Fixture spending stays optional. Plaid Sandbox work is last; the
adapters stay in the code
([decision 0016](wiki/decisions/0016-spoonacular-read-time-overlay.md)).
The Instacart handoff is parked, and the shopping-link button stays hidden
([decision 0010](wiki/decisions/0010-usda-spoonacular-overlay.md)).
Nutrition facts come from USDA FoodData Central. An optional overlay shows
the Spoonacular average supermarket cost. Budget acceptance still uses the
sample catalog. Evidence labels distinguish fixtures, emulator behavior,
Sandbox behavior, and real model calls. `POST /grocery/templates` holds a library of six preset combinations.
The service filters that library for budget, diet, pantry, and
exclusions. The endpoint returns up to six eligible suggestions. An
empty list is possible. Prices on those suggestions are labeled sample
estimates. The presets do not reserve money. `get_budget_summary` returns
read-only budget facts. Pending cents and stale-spending warnings stay
separate.

## Constraints

- Prices are versioned sample estimates, not verified retailer quotes.
- Pending spending remains separate from posted net spending.
- Stale spending requires refresh or an explicit temporary cap.
- The application MUST preserve requested servings and required ingredients.
- Pantry removal requires explicit user input.
- The application MUST NOT submit purchases, orders, or payments.
- Credentials and raw provider responses MUST stay out of model inputs.

## Evidence

The wiki records completed implementation and verification. Local tests do not
establish live-provider access or release readiness. The recipe catalog holds
40 supported meals with explicit quantities and dietary facts. The
authoritative list is `backend/app/domain/catalog_recipes.json`.
