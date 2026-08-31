# Delegation guide

This guide shows how to hand FEWIA work to the agent team in
`.claude/agents/`.

## The team

| Agent | Owns | Use for |
|---|---|---|
| `tech-lead` | nothing (delegates) | A whole phase or any multi-part task |
| `backend-dev` | `backend/` | FastAPI, SQLAlchemy, tools, agent loop |
| `ml-dev` | `backend/app/synth`, `backend/app/ml` | Data, models, metrics |
| `aws-infra` | `compose.yaml`, `infra/`, AWS | Docker, Floci, Bedrock, deploy |
| `test-engineer` | `backend/tests/`, `eval/`, CI | Test suites, eval harness, review |
| `frontend-dev` | `frontend/` | React app (Phase 7) |

## Hand off one task

Name the agent in your message:

> Use the backend-dev agent to build `get_health_context` and its
> endpoint on branch `feat/health-context`.

Claude spawns the agent with the Agent tool. The agent starts cold, so
the prompt must be self-contained: goal, files, interface, verification
command, branch name.

## Hand off a phase

Give the phase to `tech-lead`:

> Use the tech-lead agent to run Phase 3 of the plan.

`tech-lead` decomposes the phase, spawns the specialists, verifies their
reports, and states the PR merge order. You review and merge.

## Run agents in parallel

Independent tasks can run at the same time. Ask for it directly:

> Run ml-dev on the synthetic generator and backend-dev on the health
> tool in parallel, each in its own worktree.

Worktree isolation gives each agent its own copy of the repository, so
parallel edits do not collide. Each agent delivers its own branch.

## Continue an agent

A finished agent keeps its context. Send a follow-up instead of a new
spawn:

> Tell the backend-dev agent to also add the missing-data warning.

A new spawn starts cold; a follow-up message does not.

## Codex as the writer

Codex writes the code; Claude verifies it. `AGENTS.md` binds Codex to
the same rules as `CLAUDE.md`.

The loop, driven by Claude:

1. Claude decomposes the work item and starts Codex non-interactively:
   `codex exec "<self-contained assignment>"`. The assignment names the
   goal, files, interfaces, verification command, and branch.
2. Codex writes the code on the branch and runs the checks.
3. Claude verifies independently: reads the diff, reruns the checks,
   and tests whether the tests catch a regression.
4. Findings go back to Codex with `codex exec resume --last`. The loop
   repeats until the findings are closed.
5. Claude reports the reviewed PR. You merge.

The verifier MUST NOT fix the code it reviews. Claude reports findings;
Codex or the user applies them. This keeps the review independent.

## Retro: how the agents learn

The agent files stay thin and stable. Lessons land in three layers:

1. **Facts** go in the wiki. Every spawn reads `CLAUDE.md` and the wiki,
   so a recorded lesson reaches every future agent.
2. **Behavior** changes an agent file. After a phase merges, tech-lead
   proposes the diff as its own pull request that links the wiki entry
   for the triggering incident. You review and merge. An agent MUST NOT
   edit its own definition outside this flow.
3. **Mechanical rules** become hooks in `.claude/settings.json`. A hook
   enforces a rule regardless of any prompt.

## Review and merge

1. Each agent delivers a branch and a pull request. A PR MUST NOT add
   more than 150 lines of code; a larger change ships as a stack with
   the merge order in each PR body.
2. Review with the `/code-review` skill or the test-engineer agent.
3. You merge. Agents MUST NOT merge or push to `main`.
4. After a phase merges, run `/graphify` to refresh the knowledge graph.
