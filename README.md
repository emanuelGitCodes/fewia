# FEWIA

FEWIA is a budget-aware grocery planning chat for CAP 6938. It runs as a
local web chat. The stack is a React and TypeScript frontend, a FastAPI
backend, PostgreSQL, a background worker, and local Floci in Docker Compose.
It uses real Amazon Bedrock through the `LLMProvider` protocol in
`backend/app/agent/`. It uses Plaid Sandbox for spending data. It uses a
versioned sample price catalog. It supports ten meals, one to three (1-3)
meals per request, and one to eight (1-8) servings per meal. It creates
Instacart development shopping links. Every price estimate MUST carry this
exact notice: "Estimated from the demo price catalog. Instacart prices,
availability, taxes, delivery fees, and tips are not verified."

FEWIA does not submit a checkout. It does not submit payments. It does not
use live retailer prices. It does not train a health model. That
health-prediction scope is historical and retired. See
[wiki/decisions/0008-grocery-bot-pivot.md](wiki/decisions/0008-grocery-bot-pivot.md).

## Quick start

`docker compose up -d` starts `postgres`, `floci`, `bootstrap`, `api`,
`worker`, `sync-worker`, and `web`. Those names are the services in
[compose.yaml](compose.yaml). Read
[runbooks/durable-jobs.md](runbooks/durable-jobs.md) for background-job
operations.

## Checks

Run the backend gates from `backend/`:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Run the frontend gates from `frontend/`:

```bash
cd frontend
npm test
npm run build
```

## Repository map

- `backend/` — FastAPI app and tests
- `frontend/` — React and TypeScript web chat
- `infra/` — Bedrock and Floci bootstrap helpers
- `dev_supervisor/` — the CLI writer supervisor
- Evaluation code lives in `backend/app/evaluation_*.py` and
  `backend/tests/evaluation/`
- `wiki/` — decisions and the work log
- `docs/` — immutable course sources
- `runbooks/` — operational procedures
- `plans/` — working planning notes

## Agents

Read [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md),
[.codex/TEAM.md](.codex/TEAM.md), and
[docs/DEV_SUPERVISOR.md](docs/DEV_SUPERVISOR.md). A separate writer CLI
writes the code. Agents verify the result.
