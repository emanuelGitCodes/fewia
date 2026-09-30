# Delegation guide

This guide is the single rulebook for delegated FEWIA work. Claude Code,
Codex, and OpenCode follow the same rules. Each tool keeps only its own
mechanics in a thin adapter:

| Tool | Coordinator | Adapter files |
|---|---|---|
| Claude Code | The main session | `CLAUDE.md`, `.claude/skills/feature-loop/`, `.claude/agents/` |
| Codex | The `tech-lead` role | `.codex/TEAM.md`, `.codex/agents/` |
| OpenCode | The `tech-lead` primary agent | `.opencode/skills/fewia-workflow/`, `.opencode/agents/` |

The role map lives in [.codex/TEAM.md](../.codex/TEAM.md). Writer model
selection lives in [DEV_SUPERVISOR.md](DEV_SUPERVISOR.md). Decision
[0014](../wiki/decisions/0014-tiered-delegation.md) records why these rules
exist.

## Roles in the loop

- **Coordinator.** Reads broadly, designs, picks the tier, briefs, verifies,
  and publishes. The coordinator never writes application code.
- **Junior.** One role subagent per work item. It drives the writer, runs
  the gates, and reports. It follows [delegation/junior.md](delegation/junior.md).
- **Writer.** A Grok or Codex CLI that `dev_supervisor` starts. The writer
  edits files only. It runs no commands.
- **Review model.** A separate Codex model that `dev_supervisor.review`
  starts read-only. It is the independent reviewer. When Codex is
  unavailable, a separate read-only Grok session reviews the diff instead,
  and the coordinator records the deviation.
- **Reviewer agent.** Tier L only. It runs probes and mutation checks and
  follows [delegation/reviewer.md](delegation/reviewer.md).

## Tiers

The coordinator picks one tier per work item from its complexity class.

| Tier | Use it for | Flow |
|---|---|---|
| S | `simple`: configuration or a narrow change, no new contract, no security surface | The coordinator runs the writer, the gates, and the review command. No subagents. |
| M | `standard` | One junior drives the writer and the gates. The coordinator runs the review command. |
| L | `complex` or harder, a security boundary, or tests that guard other code | One junior, one reviewer agent, and the review command. |

A security boundary or a test-gate deliverable is tier L at any size.
When the tier is unclear, the coordinator SHOULD pick the higher tier.

## Writer selection

The coordinator picks one writer model and one effort per work item.
Decision [0015](../wiki/decisions/0015-writer-routing-by-difficulty.md)
records the rule.

The writers form one ladder. The score is the Artificial Analysis
Intelligence Index v4.3.2. Pick the lowest rung that fits the work item.

| Rung | Writer | Effort | Score | Use it for | `--complexity` |
|---|---|---|---|---|---|
| 1 | `gpt-6-luna` | `xhigh` | 34 | Simple: configuration, one narrow change, no new contract | `simple` |
| 2 | `grok-4.6` | `low` | 35 | A small mechanical change that follows a pattern in the repository | `standard` |
| 3 | `grok-4.6` | `medium` | 43 | Standard work that the brief fully specifies | `standard` |
| 4 | `gpt-6.1-sol` | `medium` | 48 | Ambiguous or cross-cutting work, a new contract, or debugging | `complex` |
| 5 | `gpt-6.1-sol` | `high` | 50 | Security, test-gate work, or the hardest cross-system work | `complex` or harder |

- Every writer run MUST pass `--only --model MODEL --effort LEVEL`.
- Only the five rungs above write code. Grok MUST NOT receive `high` or
  above. Sol MUST NOT receive `low`, `xhigh`, or `max`. Luna MUST use
  `xhigh`. `gpt-5.3-codex-spark` and Sonnet MUST NOT write code.
- When the rung is unclear, the coordinator SHOULD pick the higher rung.
- `--complexity` still sets the tier and the review effort.

Fallback on a provider outcome (`unavailable`, `quota`, `rate_limit`, or
`stalled`): Luna goes to Grok `medium`, Grok goes to Sol `medium`, and Sol
goes to Grok `medium`. A failed task does not trigger fallback.

A repair keeps the same writer. After two repair rounds with no progress,
the coordinator MAY move the item up the ladder. Luna moves to rung 3,
because rung 2 scores almost the same as Luna. The ledger records each
change of writer.

## The loop

1. **Intake.** Read `project-plan.md`, `wiki/index.md`, the newest
   decisions in `wiki/decisions/`, and the source files in the path. Use a
   search agent or `/graphify query` for broad questions. Do not load the
   whole graph into a brief.
2. **Probe.** For each acceptance criterion that depends on a repository
   fact, run one cheap check before dispatch. Examples: a `grep` for a
   `downgrade()` body, `docker inspect` for a built-in healthcheck, or
   the current lint output.
3. **Design.** Fix the shared contracts. Split the work into items of 150
   added code lines or fewer. Give each item one owner, exact owned files,
   a complexity class, a tier, a base branch, and a runnable check.
4. **Approve.** Show the design to the user. Dispatch only released items.
5. **Dispatch.** Write one brief per item from
   [delegation/brief.md](delegation/brief.md). Run at most three subagents
   at a time. Review commands and gates do not count toward that limit.
6. **Review.** Commit, run the gates on the committed head, then run the
   review command on that head. The review prompt then includes the gates
   record. Tier L also gets a reviewer agent.
7. **Verify.** Read the diff. Run `dev_supervisor.gates --reuse` on the
   reviewed SHA; it reruns the gates when the record is missing or the tree
   changed. Confirm the reviewed SHA equals the head SHA.
8. **Repair.** Write a repair brief with the blocking findings from the
   review command and from the coordinator's own diff read and checks.
   Send it back to the owner. Stop an item after three review rounds and
   escalate to the user.
9. **Publish and record.** Publish only with user authorization. Record
   tokens and time per item in the loop ledger and the wiki log. Update the
   wiki pages that the work touched.

## Commands

Run every command from the item worktree root.

```bash
# Writer: edits files only. Pick the model and effort from "Writer selection".
uv run --project backend python -m dev_supervisor \
  --task "$BRIEF_FILE" --role backend-dev --cwd "$PWD" \
  --complexity standard --only --model gpt-6.1-sol --effort medium \
  --write-file backend/app/example.py \
  --work-item fewia-42 --phase implement

# Gates: selects checks from the changed paths and records them by SHA.
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main

# Review: independent, read-only, time-capped, short output.
uv run --project backend python -m dev_supervisor.review --cwd "$PWD" \
  --base main --brief "$BRIEF_FILE" --complexity standard \
  --writer-model gpt-6.1-sol --work-item fewia-42

# Usage: token and time totals per work item.
uv run --project backend python -m dev_supervisor.usage --work-item fewia-42
```

`--task` and `--brief` take a file path. The review command exits 0 for
`APPROVE`, 1 for `REQUEST_CHANGES`, and 2 for `BLOCKED`.

## Budgets

| Item | Limit |
|---|---|
| Brief | About 60 lines. List file paths. Do not paste file contents. |
| Report | 40 lines in the fixed format. Name the SHA. Do not paste diffs or files. Send it once. |
| Review model effort | `low` for S, `medium` for M, `high` for L |
| Review model time | 900 seconds |
| Gate runs per SHA | The junior runs them once. The coordinator runs them once. The reviewer agent does not rerun them. |
| Review rounds per item | Three, then escalate |

Reading per role:

- The coordinator reads what intake needs.
- A junior reads its role file, `delegation/junior.md`, the brief, and the
  files that the brief names.
- A writer reads the supervisor prompt only.
- A reviewer agent reads `delegation/reviewer.md`, the brief, and the diff.

## Rules that prevent known waste

- The writer MUST NOT run commands. Grok has file permissions only, and a
  command ends its run as `task_failed`. Codex writers have no network.
- The junior runs every install, lint, test, and build.
- A `task_failed` outcome does not prove the edits are wrong. The junior
  MUST inspect the diff before deciding.
- A brief for documentation MUST cite the newest decisions, not only
  `.codex/project-context.md`.
- Every agent MUST stop its background processes before it reports.
- Every long command MUST run with a timeout.
- A review model verdict covers code findings only. A `BLOCKED` verdict
  that cites only sandbox limits is not a code finding.
- An `APPROVE` MUST come from a completed review model run.
- Code MUST NOT be compressed to fit the 150-line cap. File-level lint
  suppressions, `# fmt: off` blocks, joined statements, and encoded tables
  defeat the review. Split the item instead.

## Measure

`dev_supervisor` records writer and review tokens in one ledger per
repository. `dev_supervisor.usage` prints the totals. The coordinator adds
subagent tokens from its own tool, then records one line per work item in
the loop ledger and one total per loop in `wiki/log.md`.

## Retro: how the agents learn

The agent files stay thin and stable. Lessons land in three layers:

1. **Facts** go in the wiki. The coordinator selects relevant facts for
   bounded briefs. Workers can request more context.
2. **Behavior** changes this guide or an agent file. The change ships as
   its own pull request that links the wiki entry for the incident. An
   agent MUST NOT edit its own definition outside this flow.
3. **Mechanical rules** become tested `dev_supervisor` checks or CI checks.
   Installing global hooks is outside this workflow.

## Review and merge

1. Each work item delivers a branch and a pull request. A pull request
   MUST NOT add more than 150 lines of code. A larger change ships as a
   stack with the merge order in each pull request body.
2. Agents MUST NOT push to `main`. Writers and juniors MUST NOT merge. A
   coordinator merges only when the user explicitly authorizes merging for
   that stack. Otherwise the user merges.
3. Prose in documents, comments, and commit messages follows ASD-STE100.
   Requirement words are MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY.
4. After a stack merges, run `/graphify` to refresh the knowledge graph.
