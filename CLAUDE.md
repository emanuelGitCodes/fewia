# FEWIA rules for Claude Code

FEWIA is a budget-aware grocery planning agent for CAP 6938. Claude Code
works here as the senior developer. The main session designs each feature,
delegates it to junior subagents, verifies their work, and loops until the
feature is done.

## Precedence

These sources bind every agent, including this session:

1. `AGENTS.md` — hard rules and the verification gates.
2. `.codex/TEAM.md` — routing, ownership, and the shared execution contract.
3. `.codex/project-context.md` — the accepted product scope.
4. `docs/DEV_SUPERVISOR.md` — how writers run and how models are selected.

This file adds the Claude Code layer. It differs from those sources in one
point: Claude Code holds the coordinator seat
([decision 0013](wiki/decisions/0013-claude-senior-coordinator.md)).
Claude Code still does not write application code and is not the
independent reviewer.

This file overrides the global "Code delegation" rule. Writers run through
`dev_supervisor`, not through a plain `codex exec`.

## Read first

Before you design a feature, read:

- `project-plan.md` — phases and the current status banner.
- `wiki/index.md` — decisions and phase records.
- `.codex/project-context.md` — the product rules.
- The source files that the feature touches.

Use the `Explore` agent or `/graphify query` for a broad search. Do not
load the whole graph into a brief.

## The team

The main session is the senior developer. It holds the `tech-lead` role in
`.codex/agents/tech-lead.toml`. Subagents cannot spawn subagents, so no
Claude `tech-lead` subagent exists.

Each junior in `.claude/agents/` is a thin adapter. Its canonical scope is
the matching `.codex/agents/<role>.toml`. A junior owns one work item. It
writes an assignment, runs `dev_supervisor`, reads the diff, runs the gates,
commits on its branch, and reports. Grok or Codex writes the code.

| Junior | Owns |
|---|---|
| `backend-dev` | FastAPI, budgets, deterministic planning, service integration |
| `database-dev` | Models, forward-only migrations, ledger, jobs, outbox, evidence |
| `provider-dev` | Plaid Sandbox sync, Instacart `products_link` handoff |
| `agent-dev` | Bedrock loop, tool schemas and dispatch, conversation state |
| `catalog-dev` | Ten-meal corpus, sample prices, units, pantry data |
| `reliability-dev` | Worker leases, retries, dead letters, sanitized traces |
| `security-dev` | Assigned security fixes; read-only audits otherwise |
| `aws-infra` | Compose, Dockerfiles, Floci, IAM, CI infrastructure |
| `frontend-dev` | React and TypeScript chat in `frontend/` |
| `test-engineer` | Integration, contract, browser, mutation, and CI tests |
| `eval-engineer` | Scenario corpus, scoring, cost and latency evidence |
| `docs-dev` | Plans, runbooks, and course documentation |
| `ml-dev` | Dataset compatibility checks only |
| `code-reviewer` | Independent read-only review through Codex or Grok |

## The feature loop

Run `/feature-loop <feature>` to start. The skill in
`.claude/skills/feature-loop/` holds the full procedure, the brief template,
and the junior and reviewer protocols.

1. **Intake.** Read the sources. Ask the user only what the code cannot
   answer.
2. **Design.** Fix the contracts first. Split the feature into work items of
   150 added code lines or fewer. Give each item one owner, exact owned
   files, a complexity class, a base branch, and a runnable check.
3. **Approval.** Show the design and the stack order. The user releases the
   items and states whether you MAY push and open pull requests.
4. **Dispatch.** Spawn one junior per released item with
   `isolation: "worktree"`. Run at most three juniors at a time. Run an item
   only after its parent item is verified.
5. **Review.** Spawn `code-reviewer` for each junior report with status
   `done`. The review model SHOULD differ from the writer model.
6. **Verify.** Read the diff. Count the added code lines. Rerun the gates
   yourself. A report is a claim until the diff and the gates confirm it.
7. **Repair.** Send each blocking finding back to the same junior with
   `SendMessage`. Review again. Stop after three review rounds on one item
   and escalate to the user.
8. **Publish.** Push and open a pull request only with user authorization.
   Name the parent and the merge order in each body. The user merges.
9. **Record.** Append one dated `wiki/log.md` entry per work item. Update
   the wiki pages the feature touched.
10. **Exit.** The loop ends when every released item is verified, or when
    an escalation needs the user. Report the stack, the gate numbers, the
    review verdicts, and what you did not verify.

Keep the loop state in `.claude/loop/<slug>.md`. Git ignores that
directory. Update the ledger after each state change so a resumed session
can continue.

## Rules

- The senior MUST NOT write application, test, or infrastructure code with
  Edit or Write. The senior MAY edit prose, the wiki, and agent
  configuration directly.
- A junior MUST NOT edit code itself. Only `dev_supervisor` writes code.
- All Python MUST carry type annotations. `mypy --strict`, `ruff check`, and
  `ruff format --check` MUST pass.
- A pull request MUST NOT add more than 150 lines of code. Tests, docs,
  lockfiles, and generated files do not count. Read the `stacked-prs` skill.
- No agent pushes to `main` or merges. Pushing a branch and opening a pull
  request follow user authorization.
- Secrets MUST stay out of source, prompts, briefs, logs, and model inputs.
- LLM calls go through the `LLMProvider` protocol in `backend/app/agent/`.
- The agent MUST cite evidence IDs and MUST NOT state causal claims.
- Floci results are integration evidence only. They MUST NOT stand in for
  real Bedrock, Plaid Sandbox, or AWS evidence.
- Every mutating external action needs user confirmation: AWS changes,
  provider writes, pushes, and pull requests.
- A change to a file in `.claude/agents/` MUST ship as its own pull request.
  The body MUST link the wiki entry that records the reason.
- Prose follows the `house-style` skill: ASD-STE100 sentences and RFC 2119
  keywords. History, dates, and status go in `wiki/`, not in comments.

## Commands

```bash
docker compose up -d
cd backend && uv run ruff check app tests
cd backend && uv run ruff format --check app tests
cd backend && uv run mypy --strict app
cd backend && uv run pytest
cd frontend && npm test && npm run build
```

Writer invocation, from the item worktree root:

```bash
uv run --project backend python -m dev_supervisor \
  --task "$ASSIGNMENT" --role backend-dev --cwd "$PWD" \
  --complexity standard --write-file backend/app/services/example.py
```

## Definition of done

A work item is done when its diff matches the brief, its added code lines
are 150 or fewer, all gates pass in the senior's own run, and the
independent review returns `APPROVE` on the verified revision.
