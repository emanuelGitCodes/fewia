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

## Operating context

The application runs locally through Docker Compose. The budget starts from
a user-entered amount and fixture spending. Plaid Sandbox work is paused; the
adapters stay in the code. The Instacart handoff is parked, and the
shopping-link button stays hidden
([decision 0010](wiki/decisions/0010-usda-spoonacular-overlay.md)).
Nutrition facts come from USDA FoodData Central. An optional overlay shows
the Spoonacular average supermarket cost. Budget acceptance still uses the
sample catalog. Evidence labels distinguish fixtures, emulator behavior,
Sandbox behavior, and real model calls.

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
ten supported meals with explicit quantities and dietary facts.
