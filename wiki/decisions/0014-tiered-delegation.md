# 0014 — Tiered delegation and token budgets

- Date: 2026-09-25
- Status: accepted; amended by [0015](0015-writer-routing-by-difficulty.md), which replaces the tier L reviewer agent

## Decision

Every coordinator tool follows one rulebook,
[docs/DELEGATION.md](../../docs/DELEGATION.md). Claude Code, Codex, and
OpenCode keep only their own mechanics in thin adapters.

Each work item gets a tier from its complexity class:

- Tier S (`simple`): the coordinator runs the writer, the gates, and the
  review command. No subagents.
- Tier M (`standard`): one junior. The coordinator runs the review command.
- Tier L (`complex` or harder, security, or test-gate work): one junior,
  one reviewer agent, and the review command.

Three shared `dev_supervisor` commands carry the mechanics for all tools:
`gates`, `review`, and `usage`. Writers edit files only and run no
commands. Reports and briefs have line budgets. Each role reads a bounded
set of files.

This decision keeps the writer order from
[0011](0011-dynamic-delegated-effort.md) and the independent review from
[0009](0009-codex-grok-review.md). It keeps the coordinator seat from
[0013](0013-claude-senior-coordinator.md).

## Options considered

- Keep one flow for every item. Phase 1 used about 1.8 million subagent
  tokens for about 270 code lines. A one-line change cost about 150,000.
- Drop the reviewer agent everywhere. The reviewer agent found two defects
  in Phase 1 that the gates passed: a test that skipped instead of failing,
  and a security predicate that needed an exhaustive equivalence check.
  Tier L keeps it for that kind of work.
- Put the rules only in Claude Code files. Codex and OpenCode would not
  see them.

## Reason

Phase 1 of the tech-debt work showed six sources of waste:

1. The full agent chain ran for one-line items.
2. Writers tried commands that their permissions forbid.
3. Briefs cited outdated scope and missed repository facts.
4. The gates ran three times on the same SHA.
5. Reports pasted diffs and whole files, and some arrived twice.
6. Background watches and uncapped review runs kept tasks open.

## Consequences

- The coordinator probes repository facts before dispatch.
- Review verdicts arrive as a short summary and one JSON line.
- The usage ledger measures writer and review tokens per work item.
- The first loop after this decision measures its tokens against the
  Phase 1 baseline and records the result in `wiki/log.md`.
