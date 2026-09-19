# Grocery bot agent team

Default coding delegation uses [the CLI supervisor](../docs/DEV_SUPERVISOR.md).
Hard rules, model selection, effort ceilings, and reviewer gates live in
`AGENTS.md` and `docs/DEV_SUPERVISOR.md`. Preserve those model constraints
by following those files. Do not copy the rubric here.

Native role files retain the Luna model.
They MUST NOT pin `model_reasoning_effort`.
Native dispatch MUST select effort from the complexity rubric.
Native dispatch starts a fresh task context.
Native bounded agents MUST set `fork_turns` to none.
They MUST NOT spawn recursive workers.
They do not implement provider fallback. Bedrock application routing is separate.

## Routing

| Role | Responsibility |
|---|---|
| tech-lead | Contracts, decomposition, scoped parallel assignments, integration |
| backend-dev | FastAPI, budgets, deterministic planning, service integration |
| database-dev | Schema, migrations, ledger, durable jobs and outbox |
| provider-dev | Plaid REST synchronization and Instacart list handoff |
| agent-dev | Bedrock adapter, tools, conversation state, bounded execution |
| catalog-dev | Recipes, sample prices, units, substitutions, pantry data |
| aws-infra | Compose, Floci provisioning, client isolation, CI infrastructure |
| reliability-dev | Worker leases, retries, duplicate delivery, dead letters, observability |
| security-dev | Security implementation and threat review |
| frontend-dev | Web chat, plan controls, progress, evidence, accessibility |
| test-engineer | Contract, integration, browser, and mutation tests |
| eval-engineer | Scenario corpus, scoring, baselines, cost and latency evidence |
| docs-dev | Maintained plans, runbooks, wiki, course evidence documentation |
| ml-dev | Compatibility role; routes data to catalog-dev and metrics to eval-engineer |

Use catalog-dev and eval-engineer for new tasks. ml-dev does not resume health training.

Dispatch the owning role for routine work. Use tech-lead only when the
work needs multi-role decomposition. Do not insert a coordinator hop for
a single bounded assignment.

## Shared execution contract

Hard rules live in `AGENTS.md`. Writer workflow lives in
`docs/DEV_SUPERVISOR.md`. The coordinator reads this guide and that
workflow when dispatching. Workers receive the selected role, a bounded
assignment, `.codex/project-context.md` product constraints, and
relevant integration context.
Workers MUST NOT load this guide or historical project-plan and course
docs unless the assignment needs them.

Assignments specify exact files, interfaces, dependencies, verification, and
completion evidence. Routing areas are not blanket write permission.
Agents are not alone: preserve other edits and coordinate overlapping files.
Serialize models, migrations, routers, dependency files, shared fixtures,
wiki indexes, and log writes. Assign one owner per shared file.

With four session slots, use at most three workers alongside the coordinator.
Spawn only for concrete independent tasks. Use explicit bases and integration
order for worktrees. Child agents MUST NOT switch branches in a shared checkout.

Each code PR MUST stay within 150 added source lines. Tests and docs do not
count. Include tests with each behavior change. Agents MUST NOT merge or push
to main. Other publication follows user authorization. Preserve old migrations
and data; do not delete branches or worktrees as routine cleanup.

The selected CLI writer writes code. A separate Codex or Grok agent supplies
independent verification with targeted context and read-only ownership. Record
the reviewed revision, commands, failure cases, and remaining limits. Return
defects to the owning writer, then rerun review after repair. Repair MUST reuse
the owning worker and the explicit task context. Do not use `resume --last`.
Claude Code is not an active dependency. Do not request Claude authentication.

Writer and reviewer testing policy lives in `AGENTS.md`. Wiki logging follows
`AGENTS.md`. Do not invent CI, live API, or deployment results.

## Loading and use

Standalone `.codex/agents/*.toml` files define project roles. Existing sessions
can retain their startup role list. Start a new session if a role is missing,
or dispatch a worker with the exact role instructions and explicit model/effort.
Do not claim hot-reload without verifying it. This configuration does not alter
global permissions or install MCP connections.

[Configuration reference](https://learn.chatgpt.com/docs/agent-configuration/subagents)
