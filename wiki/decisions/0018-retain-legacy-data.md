# 0018 — Retain legacy data for now

- Date: 2026-10-03
- Status: accepted
- Relates to: [0016 — Spoonacular prices at read time](0016-spoonacular-read-time-overlay.md)

## Decision

Keep existing stored Spoonacular totals and retired health tables in place
for now. This decision covers retention of existing records only.

Decision 0016 remains in force. The application MUST NOT store new
Spoonacular prices. The API computes Spoonacular estimates at read time.
Sample-catalog cents remain the budget figure.

Future work MUST NOT revive retired routes or treat legacy totals as current
price evidence.

## Why

Retain these records to preserve evidence until a separate retention and
migration review.

## Migration plan

No migration runs under this decision. A later deletion decision MUST define
the scope, backup and retention expectations, a forward-only migration,
verification, and owner approval.

This decision does not include inventory, export, or deletion of records.
