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

## Review and merge

1. Each agent delivers a branch and a pull request. A PR MUST NOT add
   more than 150 lines of code; a larger change ships as a stack with
   the merge order in each PR body.
2. Review with the `/code-review` skill or the test-engineer agent.
3. You merge. Agents MUST NOT merge or push to `main`.
4. After a phase merges, run `/graphify` to refresh the knowledge graph.
