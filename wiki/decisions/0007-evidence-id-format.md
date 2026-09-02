# 0007 — Evidence ID format

- **Date**: 2026-09-01
- **Status**: accepted

## Decision

A health, finance, environment, or prediction response carries
`evidence_id` in the form `{domain}:user-{user_id}:{range}`. The range
is `YYYY-MM` when the request covers exactly one whole calendar month.
Every other range uses `YYYY-MM-DD..YYYY-MM-DD`.

A compare response carries `compare:user-{user_id}:{span_a}_vs_{span_b}`.
The first span is period A. The second span is period B. The ID identifies
the direction of the comparison. Each span uses the same month shorthand
rule.

## Options considered

1. Both compare spans in caller order, joined with `_vs_` — chosen.
2. Both compare spans, sorted and joined with `_vs_`.
3. One combined span from the first period start to the second period end.

## Reason

One combined span can run backward when callers pass period B first. It
also loses the boundary between two subranges in one month. A sorted ID
does not identify the signs of the returned deltas. The two-span form in
caller order identifies the comparison direction. The MVP plan §6 keeps
its whole-month shorthand for the four single-domain tools.

## Consequences

- Phase 6 evaluation strings MUST use period A first and period B second.
  The evidence ID identifies the comparison direction.
- Health, finance, environment, and prediction keep the existing
  whole-month shorthand.
- `build_compare_evidence_id` applies the month rule to both spans.

Related: [Phase 3](../phases/phase-3.md).
