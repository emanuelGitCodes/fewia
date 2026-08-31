# 0004 — Six-agent team with a delegating tech lead

- **Date**: 2026-08-31
- **Status**: accepted

## Decision

Work routes through six project agents in `.claude/agents/`:
`tech-lead`, `backend-dev`, `ml-dev`, `aws-infra`, `test-engineer`, and
`frontend-dev`. `tech-lead` decomposes a phase into PR-sized work
items, spawns the specialists, verifies their reports, and states the
merge order. `tech-lead` MUST NOT write application code.

## Reason

The user's secondary goal is to learn multi-agent delegation. Domain
ownership per agent gives each spawn a small, self-contained prompt.
A delegator that also codes reviews its own work; the split keeps
review independent.

## Consequences

- Each agent starts cold. Every assignment must carry the goal, files,
  interfaces, verification command, and branch name.
- Parallel work uses worktree isolation so edits do not collide.
- `docs/DELEGATION.md` documents the hand-off mechanics for the user.

Related: [0003](0003-private-github-stacked-prs.md),
[phase 0](../phases/phase-0.md).
