# Delegation guide

This guide shows how to hand FEWIA work to the agent team in
`.codex/agents/`.

## The team

The current role map lives in [.codex/TEAM.md](../.codex/TEAM.md).
Role areas are routing hints, not blanket write permission. Each assignment
MUST name exact owned files and relevant contracts.

## Hand off one task

Name the agent in your message:

> Use backend-dev to implement the assigned grocery budget endpoint
> on an isolated branch. Own only the files named in the task brief.

The coordinator invokes the writer supervisor. The bounded brief names the
goal, files, interfaces, verification command, and branch. A separate Codex or
Grok reviewer receives the current diff and targeted acceptance criteria.

## Hand off a phase

Give the phase to `tech-lead`:

> Use tech-lead to decompose the authorized grocery work item.

`tech-lead` decomposes the phase, spawns the specialists, verifies their
reports, and states the PR merge order. You review and merge.

## Run agents in parallel

Independent tasks can run at the same time. Ask for it directly:

> Run catalog-dev on the assigned recipe data and backend-dev on the
> assigned budget endpoint, each in its own worktree.

Worktree isolation gives each agent its own copy of the repository, so
parallel edits do not collide. Each agent delivers its own branch.

## Continue an agent

A native coordinator or reviewer may retain session context. Supervised CLI
writers use new bounded assignments and explicit checkpoints. Carry the task
scope, completed checks, remaining work, and model constraints into repairs.
Do not assume an ephemeral CLI session can resume by name or `--last`.

## Supervised CLI writers

Use [the development supervisor](DEV_SUPERVISOR.md) for coding assignments.
The default order is Grok 4.6, Spark at its CLI default effort, then Luna.
The coordinator classifies each task before delegation.
Grok 4.6 uses `low` for simple tasks.
Grok 4.6 uses `medium` for every harder automatic tier.
Grok 4.6 MUST NOT receive `high`, `xhigh`, or `max`.
Spark does not accept an effort override in this supervisor.
Luna and Sol support automatic selection through `max`.
The coordinator MUST NOT select `maximum` for ordinary tasks.
Explicit models override the starting model.
An explicit `--effort` override MUST stay within the model ceiling.
Model-only requests forbid substitution.
Native role files keep the Luna model.
They MUST NOT pin `model_reasoning_effort`.
Native dispatch MUST select effort from the complexity rubric.
Native role pins do not select Grok.

The coordinator decomposes the assignment.
The coordinator invokes the supervisor with its role, worktree, task file, and
`--complexity`. The writer implements and checks. A separate Codex or Grok
reviewer reads the diff, reruns checks, and tests failure paths.
The reviewer MUST NOT fix reviewed code. Findings return to the owning writer
with the same model constraints. You merge. In a Claude Code session, the main
session is the coordinator (decision 0013); Claude Code never writes code.

## Retro: how the agents learn

The agent files stay thin and stable. Lessons land in three layers:

1. **Facts** go in the wiki. The coordinator selects relevant facts for
   bounded task briefs. Workers can request more context.
2. **Behavior** changes an agent file. After a phase merges, tech-lead
   proposes the diff as its own pull request that links the wiki entry
   for the triggering incident. You review and merge. An agent MUST NOT
   edit its own definition outside this flow.
3. **Mechanical rules** become tested supervisor checks or repository CI
   checks. Installation of global hooks is outside this workflow.

## Review and merge

1. Each agent delivers a branch and a pull request. A PR MUST NOT add
   more than 150 lines of code; a larger change ships as a stack with
   the merge order in each PR body.
2. Review with the `/code-review` skill or the test-engineer agent.
3. You merge. Agents MUST NOT merge or push to `main`.
4. After a phase merges, run `/graphify` to refresh the knowledge graph.
