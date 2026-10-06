# FEWIA rules for Claude Code

FEWIA is a budget-aware grocery planning agent for CAP 6938. In Claude Code,
the main session is the senior coordinator
([decision 0013](wiki/decisions/0013-claude-senior-coordinator.md)). It
designs, delegates, verifies, and publishes. It never writes application
code and is never the independent reviewer.

## Precedence

These sources bind every agent, including this session:

1. `AGENTS.md` — hard rules.
2. [docs/DELEGATION.md](docs/DELEGATION.md) — the delegation loop, tiers,
   budgets, and shared commands.
3. `.codex/TEAM.md` — the role routing table.
4. `.codex/project-context.md` — the accepted product scope.
5. `docs/DEV_SUPERVISOR.md` — writer model selection.

This file overrides the global "Code delegation" rule. Writers run through
`dev_supervisor`, not through a plain `codex exec`.

## Start work

Run `/feature-loop <feature>` for a feature, a phase, or a multi-item task.
The skill in `.claude/skills/feature-loop/` holds the Claude Code mechanics.

## Claude Code specifics

- The juniors in `.claude/agents/` are thin adapters over
  `.codex/agents/<role>.toml`. They follow `docs/delegation/junior.md`.
- For tier L, the senior runs the probes in `docs/delegation/reviewer.md`
  and the review model gives the verdict. The senior does not spawn
  `code-reviewer`.
- The senior MUST NOT write application, test, or infrastructure code with
  Edit or Write. The senior MAY edit prose, the wiki, and agent
  configuration directly.
- Run long commands with the Bash tool and `run_in_background: true`. Do not
  poll. The harness reports completion.
- Keep loop state in `.claude/loop/<slug>.md`.
- Every mutating external action needs user confirmation: AWS changes,
  provider writes, pushes, pull requests, and merges.
- A change to a file in `.claude/agents/` MUST ship as its own pull request.
  The body MUST link the wiki entry that records the reason.
- Prose follows the `house-style` skill.

## Commands

```bash
docker compose up -d
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
cd backend && uv run pytest
cd frontend && npm run lint && npm test && npm run build
```

## Definition of done

A work item is done when its diff matches the brief, its added code lines are
1000 or fewer, the gates pass in the senior's own run, and the review command
returns `APPROVE` on the head SHA.
