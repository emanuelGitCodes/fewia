# 0011 — Dynamic delegated effort

- Date: 2026-09-18
- Status: accepted

## Decision

This decision supersedes only the fixed writer-effort defaults in
[0009](0009-codex-grok-review.md). It preserves the independent Codex or
Grok review requirement from 0009.

The coordinator classifies each task as `simple`, `standard`, `complex`,
`exceptional`, or `maximum`. Those values map to `low`, `medium`, `high`,
`xhigh`, and `max`.

Grok 4.6 uses `low` for simple tasks. Grok 4.6 has a hard `medium`
ceiling. Grok 4.6 MUST NOT receive `high`, `xhigh`, or `max`.

Spark uses its CLI model default. Spark does not accept an effort
override in this supervisor.

Luna and Sol support automatic selection through `max`.

Native `.codex/agents/*.toml` files keep the Luna model. They MUST NOT
pin `model_reasoning_effort`. Native dispatch MUST select effort from
the complexity rubric.

Explicit effort is allowed only when the selected model supports it.
The supervisor MUST skip incompatible fallback models. It MUST NOT
downgrade the requested effort. An explicitly selected incompatible
model MUST stop with an error.

Built-in model capabilities are immutable. A registry MUST NOT replace
them.

The coordinator MUST reserve `maximum` for the hardest cross-system
work. That work has substantial ambiguity, interacting failures, or
major security, reliability, or data-loss risk.

## Options considered

1. Keep the fixed Grok 4.6 medium, Spark default, and Luna xhigh
   writer defaults from 0009.
2. Classify each task and map complexity to effort with model ceilings
   — chosen.
3. Pin `model_reasoning_effort` in native role files.
4. Allow a registry to replace built-in model capabilities.

## Reason

Fixed writer effort wastes `medium` on simple Grok tasks. A fixed
default cannot adapt to task difficulty. An uncapped dynamic policy
could request unsupported effort. The user observed that
Grok showed no benefit above medium. Dynamic classification matches each
model's supported range. Native role files keep Luna. They do not pin
effort. Explicit effort stays at the requested level or stops.

## Consequences

`AGENTS.md`, `.codex/TEAM.md`, and `docs/DEV_SUPERVISOR.md` record the
same mapping. Independent Codex or Grok review remains required. A
writer cannot certify its own review. Claude Code remains inactive.

The coordinator MUST NOT select `maximum` for ordinary tasks. Model-only
requests still forbid substitution. Preserve prior records in 0009.

Related: [0009](0009-codex-grok-review.md).
