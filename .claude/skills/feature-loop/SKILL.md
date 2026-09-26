---
name: feature-loop
description: Build a FEWIA feature as the senior coordinator with the tiered delegation loop. Design, probe, pick tier S, M, or L per item, run the writer, gates, and review commands, verify, repair, and publish. Use when the user gives a feature, a phase, or a multi-item task, or says "resume" with a loop slug.
argument-hint: "<feature description> | resume <slug>"
---

# Feature loop

The rulebook is [docs/DELEGATION.md](../../../docs/DELEGATION.md). Follow it
step by step. This skill adds only the Claude Code mechanics.

## Start or resume

- New feature: pick a kebab-case slug. Copy
  `references/ledger-template.md` to `.claude/loop/<slug>.md`. Git ignores
  that directory.
- `resume <slug>`: read the ledger. Check branches with `git branch --list`
  and worktrees with `git worktree list`. Continue from the first item that
  is not `verified`.

Update the ledger after each state change.

## Tier mechanics in Claude Code

**Tier S.** Use no subagent.

1. Create a worktree: `git worktree add .claude/worktrees/<slug>-NN -b claude/<slug>-NN <base>`.
2. Write the brief to a file in the scratchpad directory.
3. Run the writer with the Bash tool and `run_in_background: true`. Pass
   `--work-item <slug>-NN --phase implement`.
4. Run `ruff format` on the owned files. Commit on the work branch.
5. Run `dev_supervisor.gates` on the committed head. It records the result
   under the head SHA, so the review prompt includes it. On `FAIL`, repair
   and commit again.
6. Run `dev_supervisor.review` on the same head with
   `run_in_background: true` and `--work-item <slug>-NN`. Read only its
   final lines.

**Tier M.** Spawn one junior from `.claude/agents/` with
`isolation: "worktree"` and `run_in_background: true`. The brief is the
prompt. When the junior reports `done`, run `dev_supervisor.review` yourself
in the background.

**Tier L.** Do tier M. Also spawn `code-reviewer` without isolation. Give it
the worktree path, the base, the head SHA, the brief, and the probes to run.

At most three subagents run at a time. Background Bash commands do not
count toward that limit.

## Repairs

Send findings to the same junior with `SendMessage`. The junior keeps its
context. For tier S, write a repair brief and run the writer with
`--phase repair`. Commit the repair, run the gates, and run the review
command again on the new head. Stop after three review rounds.

## Verify

Read the diff. Run `dev_supervisor.gates --reuse` when the junior's record
matches the head SHA and the tree is clean. Otherwise run the gates. Confirm
that the review verdict names the head SHA.

## Measure

Each subagent notification reports `subagent_tokens`. Record that number per
item in the ledger. Add `dev_supervisor.usage --work-item <item>` for the
writer and review tokens. Record the loop total in `wiki/log.md`.

## Publish

Publish only with user authorization. Push the work branch, open the pull
request with `gh pr create`, and bind it with the `ccd_pr` tools. The body
states the parent, the merge order, the lines, the gates result, the review
verdict and model, and what you did not verify.
