# 0007 — Evidence ID format

- **Date**: 2026-09-01
- **Status**: accepted

## Decision

A tool response carries `evidence_id` in the form
`{domain}:user-{user_id}:{range}`. The domain is `health`, `finance`,
`environment`, `compare`, or `prediction`. The range is `YYYY-MM` when
the request covers exactly one whole calendar month. Every other range
uses `YYYY-MM-DD..YYYY-MM-DD`. `compare_periods` carries its own
`evidence_id` and the two child values.

One helper, `build_evidence_id` in `backend/app/tools/base.py`, builds
the string. No other module writes it.

## Options considered

1. The month shorthand for a whole month, the span form otherwise —
   chosen.
2. The span form for every range.
3. The month shorthand only, with the range truncated to months.

## Reason

The MVP plan §6 shows `health:user-1:2026-08`, so option 2 breaks the
example the plan states. Option 3 loses the exact range and makes an
evidence ID ambiguous. Option 1 keeps the plan's example and stays
exact for every other range.

## Consequences

- Phase 6 evaluation questions assert these strings. A change to the
  format breaks the evaluation set.
- A whole-month request and a request for the same days stated as a
  span produce the same ID, because the ranges are the same.
- `build_evidence_id` is the single writer. A new domain adds a value
  there, not a new format.

Related: [Phase 3](../phases/phase-3.md).
