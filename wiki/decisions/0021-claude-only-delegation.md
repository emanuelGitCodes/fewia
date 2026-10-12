# 0021 — Claude-only delegation in Claude Code sessions

- Date: 2026-10-12
- Status: accepted

## Decision

A Claude Code session delegates to Claude models only. Sonnet writes the
code. Opus judges it. Haiku reads the repository. Fable advises the
coordinator at decision points. No Grok or GPT model runs from a Claude
Code session.

This decision amends [0015](0015-writer-routing-by-difficulty.md) for
Claude Code sessions only. Codex and OpenCode coordinators keep the 0015
ladder. The loop, the tiers, and the budgets from
[0014](0014-tiered-delegation.md) do not change. The coordinator still
never writes code and is still never the independent reviewer
([0013](0013-claude-senior-coordinator.md)).

## Who does what

| Role | Model | Effort | Mechanism |
|---|---|---|---|
| Design and plan | Opus 5.5 | `high` | The session model is `opusplan`. Plan mode runs on Opus. |
| Coordinate: brief, run commands, verify | Sonnet 5.5 | `medium` | `opusplan` switches to Sonnet when the plan is approved. |
| Advise the coordinator | Fable 5.1 | — | `advisorModel: "fable"`. The coordinator consults it at the three moments below. |
| Read and search the repository | Haiku 5.5 | `low` | A project `Explore` subagent with `model: haiku` replaces the built-in one. |
| Write code | Sonnet 5.5 | By rung | `dev_supervisor` starts `claude -p` as a writer. |
| Judge the diff | Opus 5.5 | By tier | `dev_supervisor.review` starts `claude -p` read-only. |
| Escalate by hand | Fable 5.1 | `high` | `/model fable`, then `/model opusplan` when done. |
| Context guard | — | — | `autoCompactWindow` is 140000 tokens for every model. |

The coordinator MUST consult the advisor at three moments and SHOULD NOT
consult it elsewhere: before it commits to a design, after the same gate or
review finding fails twice, and before it marks an item `verified`. Each
consult reads the whole transcript at Fable prices, so the moments stay few.

## Writer ladder

The writers form one ladder. Pick the lowest rung that fits the item.

| Rung | Writer | Effort | Advisor | Use it for | `--complexity` |
|---|---|---|---|---|---|
| 1 | `claude-sonnet-5-5` | `low` | none | Configuration or one narrow change, no new contract | `simple` |
| 2 | `claude-sonnet-5-5` | `medium` | none | Standard work that the brief fully specifies | `standard` |
| 3 | `claude-sonnet-5-5` | `high` | none | Ambiguous or cross-cutting work, a new contract, or debugging | `complex` |
| 4 | `claude-sonnet-5-5` | `high` | `claude-opus-5-5` | Security, test-gate work, or the hardest cross-system work | `complex` or harder |

- Every writer run MUST pass `--only --model claude-sonnet-5-5 --effort LEVEL`.
- Rung 4 adds `--advisor claude-opus-5-5`. Every other rung runs with the
  advisor off.
- Opus writes code only as the one-time fallback below. The review model
  MUST differ from the writer model: Opus reviews a Sonnet writer, and
  Fable reviews an Opus writer.
- Fallback on a provider outcome (`unavailable`, `quota`, `rate_limit`,
  or `stalled`): Sonnet goes to `claude-opus-5-5` at `medium`, once. Opus
  has no fallback; the coordinator marks the item `blocked`.

## Review model

The review model is `claude-opus-5-5`. Its effort follows `--complexity`:
`low` for `simple`, `medium` for `standard`, and `high` for `complex`,
`exceptional`, and `maximum`. The tiers map to those classes. The review prompt tells the model to assume
the change is wrong and to report one line per finding. The verdict
contract, the record under `.fewia-supervisor-reviews/`, and the exit codes
do not change. When the writer is Opus by explicit request, the review model
is `claude-fable-5-1`.

## Writer and reviewer commands

`dev_supervisor` gains a `claude` provider. It starts the writer with:

```text
claude -p --safe-mode --model claude-sonnet-5-5 --effort LEVEL
  --output-format stream-json --verbose --no-session-persistence
  --tools Read,Edit,Write,Glob,Grep --permission-mode default
  --permission-prompts none --max-turns 30
  [--advisor claude-opus-5-5] [--max-budget-usd N]
  --allowedTools "Edit(//ABS/OWNED/FILE)" ... "Edit(//ABS/progress.md)"
```

The `--allowedTools` list is variadic, so it MUST come last.

The prompt arrives on stdin. `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` is set
unless `--advisor` is given. `--safe-mode` keeps the project `CLAUDE.md`,
hooks, skills, and custom agents out of the writer. The `Edit(//path)` rule
covers `Write` on the same path; a path with a gitignore pattern character
is rejected before launch. An edit outside the owned files is denied and
the writer is told not to retry it.

`dev_supervisor.review` starts the reviewer with the same leading flags,
then `--tools Read,Glob,Grep --max-turns 20`. It passes no advisor,
budget, or allowed-tools flags. The diff is in the prompt, so the
reviewer needs no shell. The report is the `result` text of the final
stream event.

The `result` event carries `usage` in the shape the Grok parser already
reads, plus `output_tokens_details.thinking_tokens`. The ledger records it
with provenance `claude.result`.

## Options considered

- Keep the 0015 ladder and add Claude models beside it. The user asked to
  stop Grok and GPT calls from Claude Code.
- Let Claude Code subagents with Edit and Write tools be the writers. A
  subagent's output lands in the coordinator context, and the
  `.fewia-supervisor-*` records that the hooks check would not exist.
- Replace `dev_supervisor` with native subagents and drop the ledger. The
  ledger, the lease, the stall detection, and the per-SHA review record
  are tested and the hooks depend on them.
- Opus as the writer for the hardest items. The review model MUST differ
  from the writer, and Fable as the routine reviewer costs more than an
  Opus advisor on a Sonnet writer.

## Reason

The usage backfill in `wiki/log.md` shows the coordinator sessions hold 4.7
times the input tokens of every writer and review run together. Sonnet
during execution halves that cost, and Opus keeps plan quality. Fable at
decision points costs a few whole-transcript reads instead of every turn.
Haiku costs one twentieth of Opus per read. Claude Code validates every
executor and advisor pair before it sends a request.

## Consequences

- The Claude Code CLI MUST be 2.1.293 or later for Haiku 5.5.
- The coordinator runs `/advisor fable` once in a terminal session to
  confirm Fable access. When the plan refuses it, `advisorModel` becomes
  `opus`.
- `.claude/settings.json` sets `model`, `advisorModel`, `modelSettings`,
  and `autoCompactWindow`. The desktop app model menu MAY override `model`.
- `.claude/agents/` gains `Explore.md`. The junior files name the Sonnet
  writer. That change ships as its own pull request, after this page,
  so `Explore` runs on Haiku only once that pull request merges.
- `docs/DELEGATION.md`, `docs/DEV_SUPERVISOR.md`, `CLAUDE.md`,
  `AGENTS.md`, and the `feature-loop` skill carry the new ladder.
- The first loop after this decision records its tokens per phase in
  `wiki/log.md` against the backfill baseline.
