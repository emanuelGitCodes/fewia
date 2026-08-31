# 0005 — Human-gated agent learning

- **Date**: 2026-08-31
- **Status**: accepted

## Decision

The agents learn in three layers. Facts land in the wiki, which every
spawn reads. Behavioral lessons change an agent file through a
dedicated pull request that links the triggering wiki entry; the user
reviews and merges. Mechanical rules become hooks. An agent MUST NOT
edit its own definition outside this flow.

## Options considered

1. Human-gated learning in three layers — chosen.
2. Agents rewrite their own definitions directly.
3. No learning; agent files frozen.

## Reason

Silent self-editing invites prompt drift, bakes wrong lessons into
every future spawn, and lets a written instruction steer all future
agents without review. Frozen files discard real lessons, such as the
Phase 1 merge-order failure. The gated flow keeps the audit trail in
git and the review boundary with the user.

## Consequences

- The tech-lead process gains a retro step after each phase merge.
- `CLAUDE.md` requires a dedicated PR for any `.claude/agents/` change.
- Hook proposals go to `.claude/settings.json`, not to prompt prose.

Related: [0004](0004-agent-team-delegation.md),
[phase 1](../phases/phase-1.md).
