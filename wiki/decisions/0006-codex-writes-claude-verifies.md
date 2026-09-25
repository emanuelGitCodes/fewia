# 0006 — Codex writes, Claude verifies

- **Date**: 2026-08-31
- **Status**: superseded by [0009](0009-codex-grok-review.md)

## Decision

Codex (CLI 0.151.0) writes the application code. Claude drives it
non-interactively with `codex exec`, then verifies the result: reads
the diff, reruns the checks, and reports findings back to Codex until
they close. The verifier MUST NOT fix the code it reviews. `AGENTS.md`
binds Codex to the same rules as `CLAUDE.md`.

## Options considered

1. Claude drives Codex through `codex exec` and verifies — chosen.
2. The user drives Codex; Claude verifies each PR on request.
3. Claude both writes and verifies.

## Reason

A writer that reviews its own work gives a shallow review; separate
models keep the review independent. Driving Codex from Claude gives one
loop per work item instead of manual hand-offs. Option 2 stays
available when the user wants to watch Codex work.

## Consequences

- `AGENTS.md` exists at the repo root and mirrors the `CLAUDE.md`
  contract.
- The specialist Claude agents move to review, infra, and eval duties;
  Codex takes the code-writing assignments.
- Claude reports findings; Codex or the user applies them.

Related: [0004](0004-agent-team-delegation.md),
[0005](0005-human-gated-agent-learning.md).
