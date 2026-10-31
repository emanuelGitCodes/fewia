# 0024 — Store-neutral estimate notice and grocery-eval-v1.1

- Date: 2026-10-30
- Status: accepted
- Follows: [0023](0023-retire-instacart-adapter.md)

## Decision

The fixed estimate notice is:

> Estimated from the demo price catalog. Store prices, availability, taxes,
> delivery fees, and tips are not verified.

It replaces the notice that named Instacart. The notice does not name
Kroger, because the prose validator rejects a reply that contains
"kroger" (`store_price`).

The benchmark corpus holds the notice in its gold answers. The corpus
version becomes `grocery-eval-v1.1`. It keeps the same 30 scenarios and
138 slots. Only the notice text changes.

## Rules

- One change sets the notice in `backend/app/domain/grocery.py`, the
  frontend constant, the baseline system prompt, the corpus gold answers,
  the corpus version check, and the maintained docs.
- Archived evaluation artifacts in `eval/results/artifacts/` MUST NOT
  change. They record the notice that was in force when they ran.
- A `grocery-eval-v1.1` batch MUST NOT be compared with a
  `grocery-eval-v1` batch as the same measurement.

## Basis

- Design decision D13 in
  [docs/design/chat-architecture-proposal.md](../../docs/design/chat-architecture-proposal.md):
  the owner approves the new wording, and one change updates every copy.
- Owner choice, 2026-10-30: the "Store prices" wording and the
  `grocery-eval-v1.1` label.

## Consequences

- The corpus hash and the baseline system prompt hash change.
- The Oct 3 and Oct 5 benchmark batches stay valid records of
  `grocery-eval-v1`.
