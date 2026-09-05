# 0008 — Grocery bot with local Floci services

- Date: 2026-09-05
- Status: accepted

## Decision

Build a local web chat that uses Plaid Sandbox spending and Instacart
development shopping-list links. Use a versioned recipe and sample-price
catalog. Show price estimates as unverified retailer quotes.

Use Floci SQS for background jobs and Floci S3 for sanitized evaluation exports.
Keep PostgreSQL as the durable application store. Real Bedrock provides the
model; Floci responses do not prove model behavior.

## Consequences

The first release includes web chat. This supersedes the frontend timing in
[0002](0002-frontend-after-mvp-checkpoint.md). The
[real Bedrock boundary](0001-real-bedrock-from-day-one.md) remains in effect.

The agent team uses [.codex/project-context.md](../../.codex/project-context.md)
as the accepted product brief. The old health-prediction experiment is outside
the active scope. Preserve old migrations and data. Table removal requires a
separate retention decision.

Provider fakes allow work while account access is pending. Final release
requires real Plaid Sandbox, Instacart development, and Bedrock evidence.
No automatic checkout or payment belongs in this application.
