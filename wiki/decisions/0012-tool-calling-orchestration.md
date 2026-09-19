# 0012 — Tool calling as the orchestration boundary

- Date: 2026-09-18
- Status: accepted

## Decision

The Bedrock model will interpret conversation and select a small set of
high-level typed tools. The model will pass structured user intent. Backend
services will own identity, provider data, arithmetic, planning, validation,
and evidence.

`plan_groceries` MUST load the authenticated budget, catalog, pantry, and
nutrition context. It MUST run the deterministic checks before it returns a
plan. The model MUST NOT receive raw bank transactions. The model MUST NOT
calculate the remaining grocery budget.

Plaid synchronization MUST remain a background process or an explicit user
action. The model MUST NOT control bank connections, credentials, transaction
synchronization, checkout, or payment actions.

The initial tool surface stays small:

- `plan_groceries` creates and revises plans.
- A read-only budget-summary tool MAY support direct budget questions.
- A comparison tool MAY follow after evaluation shows a measured need.

## Current state

`run_chat()` registers the `plan_groceries` tool specification and dispatches
structured calls. The ledger service aggregates Plaid transaction rows into a
spending snapshot. The current demo uses fixture spending. Live Plaid Sandbox
evidence remains pending.

The USDA overlay reports facts per 100 g. Quantity-scaled nutrition totals
remain proposed work.

## Evaluation

The evaluation will measure tool selection, argument validity, unnecessary
calls, task success, constraint violations, supported claims, latency, and
estimated model cost. The no-tool condition will use the same model, catalog,
and task facts.

## Consequences

The model acts as an orchestrator. Deterministic services remain the source of
truth for money, quantities, restrictions, and nutrition calculations.

The application needs versioned schemas, authorization checks, bounded tool
loops, typed errors, idempotent execution, and evidence records. Tool failures
remain visible to the user.
