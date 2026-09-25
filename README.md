# FEWIA

FEWIA is a budget-aware grocery planning chat for CAP 6938. It runs as a
local React and TypeScript chat with FastAPI, PostgreSQL, a worker, and
local Floci in Docker Compose. FEWIA uses real Amazon Bedrock through the
`LLMProvider` protocol in `backend/app/agent/` when you start the stack
with the Bedrock overlay. Plain `docker compose up -d` leaves chat
unconfigured. The demo uses fixture spending. Plaid Sandbox adapters exist
in the code. Live Plaid Sandbox evidence remains pending. It uses a
versioned sample price catalog. It supports ten meals, one to three
(1-3) meals per request, and one to eight (1-8) servings per meal.
FEWIA parks the Instacart development handoff. The adapter stays in the
code. The shopping-link button stays hidden while `instacart_configured`
is false. See
[wiki/decisions/0010-usda-spoonacular-overlay.md](wiki/decisions/0010-usda-spoonacular-overlay.md).
FEWIA stores nutrition facts from USDA FoodData Central. These facts are
not a medical claim. FEWIA shows a labeled Spoonacular
average-supermarket-cost overlay. That overlay is optional and off by
default. It appears only when `FEWIA_SPOONACULAR_KEY_FILE` is set.
Budget acceptance still uses the FEWIA sample-catalog cents, not the
Spoonacular cost. Every price estimate MUST carry this exact notice:
"Estimated from the demo price catalog. Instacart prices, availability,
taxes, delivery fees, and tips are not verified."

FEWIA does not check out or place orders. It does not submit payments. It
does not use live retailer prices. It does not train a health model. That
health-prediction scope is historical and retired. See
[wiki/decisions/0008-grocery-bot-pivot.md](wiki/decisions/0008-grocery-bot-pivot.md).

## Quick start

`docker compose up -d` starts `postgres`, `floci`, `bootstrap`, `api`,
`worker`, `sync-worker`, and `web` from [compose.yaml](compose.yaml).
Read [runbooks/durable-jobs.md](runbooks/durable-jobs.md) for jobs.

Start Bedrock with the overlay. It sets or requires
`FEWIA_BEDROCK_MODEL_ID`, `FEWIA_BEDROCK_REGION`, `FEWIA_AWS_PROFILE`,
and `FEWIA_BEDROCK_CREDENTIALS_FILE`. Read
[infra/bedrock/README.md](infra/bedrock/README.md) for credentials.

```bash
docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml up -d
```

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

`.github/workflows/` runs these checks in CI.

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
