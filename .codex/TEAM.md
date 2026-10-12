# Grocery bot agent team

Default coding delegation uses [the CLI supervisor](../docs/DEV_SUPERVISOR.md).
A Claude Code session uses the Claude Code ladder in
[docs/DELEGATION.md](../docs/DELEGATION.md) (decision 0021). The rules
below bind Codex and OpenCode sessions.
The coordinator picks the writer by difficulty from
[Writer selection](../docs/DELEGATION.md#writer-selection): Luna `xhigh` for
simple work, and Grok `low` or `medium` or Sol `medium` or `high` for harder work. Every writer run passes
`--only --model MODEL --effort LEVEL`. Spark MUST NOT write code.
The coordinator classifies each task before delegation.
Valid complexity values are `simple`, `standard`, `complex`, `exceptional`,
and `maximum`.
Grok 4.6 uses `low` for simple tasks.
Grok 4.6 uses `medium` for every harder automatic tier.
Grok 4.6 MUST NOT receive `high`, `xhigh`, or `max`.
Spark does not accept an effort override in this supervisor.
Luna and Sol support automatic selection through `max`.
The coordinator MUST NOT select `maximum` for ordinary tasks.
Explicit task models MUST be passed to the supervisor.
An explicit `--effort` override MUST stay within the model ceiling.
Model-only requests MUST disable substitution.
Native role files retain the Luna model.
They MUST NOT pin `model_reasoning_effort`.
Native dispatch MUST select effort from the complexity rubric.
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
| aws-infra | Compose, Floci provisioning, client isolation, CI infrastructure, `dev_supervisor` tooling |
| reliability-dev | Worker leases, retries, duplicate delivery, dead letters, observability |
| security-dev | Security implementation and threat review |
| frontend-dev | Web chat, plan controls, progress, evidence, accessibility |
| test-engineer | Contract, integration, browser, and mutation tests |
| code-reviewer | Independent read-only review of one work item |
| eval-engineer | Scenario corpus, scoring, baselines, cost and latency evidence |
| docs-dev | Maintained plans, runbooks, wiki, course evidence documentation |
| ml-dev | Compatibility role; routes data to catalog-dev and metrics to eval-engineer |

Use catalog-dev and eval-engineer for new tasks. ml-dev does not resume health training.

## Shared execution contract

The loop, the tiers, and the budgets live in
[docs/DELEGATION.md](../docs/DELEGATION.md). The coordinator reads root
`AGENTS.md`, `.codex/project-context.md`, and this guide before decomposition.
A junior reads its role file, `docs/delegation/junior.md`, and its brief. A
writer reads only its supervisor prompt. Follow the user's accepted scope over
older plans.

Assignments specify exact files, interfaces, dependencies, verification, and
completion evidence. Routing areas are not blanket write permission.
Agents are not alone: preserve other edits and coordinate overlapping files.
Serialize models, migrations, routers, dependency files, shared fixtures,
wiki indexes, and log writes. Assign one owner per shared file.

With four session slots, use at most three workers alongside the coordinator.
Spawn only for concrete independent tasks. Use explicit bases and integration
order for worktrees. Child agents MUST NOT switch branches in a shared checkout.

Each code PR MUST stay within 1000 added source lines. Tests and docs do not
count. Include tests with each behavior change. Agents MUST NOT push to main.
Writers and juniors MUST NOT merge; a coordinator merges only with explicit
user authorization for that stack. Other publication follows user authorization. Preserve old migrations
and data; do not delete branches or worktrees as routine cleanup.

The selected CLI writer writes code. A separate review model in the
`code-reviewer` role supplies independent verification with targeted context
and read-only ownership. Record the reviewed revision, commands, failure
cases, and remaining limits. Return defects to the owning writer, then rerun
review after repair. Claude Code MAY hold the coordinator seat under decision
0013. The Claude Code session is never a writer or the independent reviewer. Codex and
Grok sessions do not depend on it. Do not request Claude authentication.

Run `python -m dev_supervisor.gates` for code changes, plus relevant
integration checks. Report the RESULT line and each FAIL line. Do not invent CI, live API, or
deployment results. The coordinator appends one dated wiki entry per work item.

## Codex mechanics

The `tech-lead` role is the coordinator. For tier S it runs `dev_supervisor`,
`dev_supervisor.gates`, and `dev_supervisor.review` itself. For tier M it
dispatches one native role subagent per work item. For tier L it runs the
probes in `docs/delegation/reviewer.md` itself and passes the record to the
review command. The `code-reviewer` role supplies the review model's
instructions; it is not a subagent.
Native subagents MUST NOT spawn further agents.

## Loading and use

Standalone `.codex/agents/*.toml` files define project roles. Existing sessions
can retain their startup role list. Start a new session if a role is missing,
or dispatch a worker with the exact role instructions and explicit model/effort.
Do not claim hot-reload without verifying it. This configuration does not alter
global permissions or install MCP connections.

[Configuration reference](https://learn.chatgpt.com/docs/agent-configuration/subagents)
