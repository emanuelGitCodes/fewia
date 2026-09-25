# 0009 — Codex and Grok development review

- Date: 2026-09-06
- Status: accepted; amended by [0011](0011-dynamic-delegated-effort.md) and [0013](0013-claude-senior-coordinator.md)

## Decision

Use ChatGPT/Codex and Grok for development work. Claude Code is not an active
writer, reviewer, or required authentication dependency. This supersedes
[0006](0006-codex-writes-claude-verifies.md). Preserve prior records.

Writer defaults remain Grok 4.6 medium, Spark at its CLI model default, then
Luna xhigh. Explicit task models override the starting model. Model-only
requests forbid substitution. A separate Codex or Grok reviewer verifies the
current diff, required checks, and meaningful failure cases with read-only
ownership. Findings return to the writer for repair and renewed review.

## Consequences

The coordinator keeps broad context and sends bounded worker briefs.
Exploration can propose alternative designs within the assigned scope.
Implementation receives targeted integration sources. Graph queries are
available on demand. Review independence requires a separate agent, not a
separate vendor subscription. A writer's own test run does not replace review.

Keep historical `.claude/` files and wiki records. Do not uninstall apps, alter
accounts or subscriptions, or modify global configuration under this decision.
Local instructions do not activate a saved checkout or reload an open session.
