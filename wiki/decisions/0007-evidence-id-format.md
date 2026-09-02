# 0007 — Evidence ID format

- **Date**: 2026-09-01
- **Status**: accepted

## Decision

A health, finance, environment, or prediction response carries
`evidence_id` in the form `{domain}:user-{user_id}:{range}`. The range
is `YYYY-MM` when the request covers exactly one whole calendar month.
Every other range uses `YYYY-MM-DD..YYYY-MM-DD`.

A compare response carries `compare:user-{user_id}:{span_first}_vs_{span_second}`.
It sorts the two spans by start date, then end date. Each span uses the
same month shorthand rule. `compare_periods` calls `build_evidence_id`
for each span and takes the text after the last colon.

## Options considered

1. Both compare spans, sorted and joined with `_vs_` — chosen.
2. One combined span from the first period start to the second period end.
3. The month shorthand only, with the range truncated to months.

## Reason

One combined span can run backward when callers pass period B first.
It also loses the boundary between two subranges in one month. The
two-span form gives every comparison a canonical, exact ID. The MVP
plan §6 keeps its whole-month shorthand for the four single-domain tools.

## Consequences

- Phase 6 evaluation strings MUST use the sorted two-span compare form.
  A change to this format breaks the evaluation set.
- Health, finance, environment, and prediction keep the existing
  whole-month shorthand.
- `build_evidence_id` keeps the month rule. The compare tool assembles
  the two spans from its output.

Related: [Phase 3](../phases/phase-3.md).
