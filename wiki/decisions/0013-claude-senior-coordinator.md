# 0013 — Claude Code as senior coordinator

- Date: 2026-09-25
- Status: accepted; amended by [0015](0015-writer-routing-by-difficulty.md), which retires the Claude Code and OpenCode `code-reviewer` subagents

## Decision

In a Claude Code session, the main session holds the coordinator seat. It
acts as the senior developer. It designs each feature, splits it into
stacked work items, delegates each item, verifies the result, and loops
until every released item is done.

This decision amends [0009](0009-codex-grok-review.md) for the coordinator
seat only. Claude Code is not a writer. Claude Code is not the independent
reviewer. Writers still run through `dev_supervisor` with the order in
[0011](0011-dynamic-delegated-effort.md). A separate Codex or Grok agent
still reviews each change.

Junior subagents in `.claude/agents/` drive one work item each. Each junior
is a thin adapter over its `.codex/agents/<role>.toml` file. A junior writes
the assignment, runs `dev_supervisor`, checks the diff, runs the gates,
commits on its branch, and reports. A junior has no Edit or Write tool.

A new `code-reviewer` role exists in `.codex/agents/`, `.opencode/agents/`,
and `.claude/agents/`. The Claude adapter runs a read-only Codex review and
reruns the gates itself.

The `/feature-loop` skill in `.claude/skills/feature-loop/` holds the
procedure. The Claude `tech-lead` subagent is removed. Claude Code
subagents cannot spawn subagents, so the main session holds that role.

## Options considered

- Keep Claude Code inactive. The user wants a senior and junior loop in
  Claude Code, so this option does not meet the goal.
- Let Claude juniors write code with Edit and Write. This option breaks
  0009 and the global rule that Codex or Grok writes the code.
- Let the senior call `dev_supervisor` directly. This option fills the
  senior context with writer output and gate logs.

## Reason

The senior keeps broad context and makes decisions. Juniors keep bounded
context and absorb the long writer and gate output. The existing writer and
reviewer rules stay intact.

## Consequences

- The user approves the design and the released items before dispatch.
- Pushes and pull requests need user authorization per feature. The user
  merges.
- Each item gets at most three review rounds before escalation.
- Loop state lives in `.claude/loop/<slug>.md`. Git ignores it.
- Codex and OpenCode sessions keep their own `tech-lead` coordinator.
