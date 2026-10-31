# FEWIA

FEWIA is a budget-aware grocery planning chat for CAP 6938. It runs as a
local React and TypeScript chat with FastAPI, PostgreSQL, a worker, and
local Floci in Docker Compose. FEWIA uses real Amazon Bedrock through the
`LLMProvider` protocol in `backend/app/agent/` when you start the stack
with the Bedrock overlay. Plain `docker compose up -d` leaves chat
unconfigured. The default spending source is `manual`. The monthly limit
that the user enters is the whole budget. Fixture spending stays an
optional setting. Plaid work is last. The Plaid Sandbox adapters stay in
the code. Live Plaid Sandbox evidence remains pending. See
[wiki/decisions/0016-spoonacular-read-time-overlay.md](wiki/decisions/0016-spoonacular-read-time-overlay.md).
It uses a versioned sample price catalog. It supports 40 meals. The
authoritative list is
`backend/app/domain/catalog_recipes.json`. Each request supports one to
three (1-3) meals and one to eight (1-8) servings per meal.
`POST /grocery/templates` holds a library of six preset meal
combinations. The service filters that library through the
deterministic planner for budget, diet, pantry, and exclusions. The
endpoint returns up to six eligible suggestions. An empty list is
possible. Suggestions use labeled sample prices. They do not reserve
money. `get_budget_summary` returns read-only budget facts. Pending
cents and stale-spending warnings stay separate.
FEWIA has no Instacart shopping-link handoff. The Kroger cart is the
retailer path. Only the frozen benchmark suite (`grocery-eval-v1.1`, decision 0024) runs the handoff
services. See
[wiki/decisions/0023-retire-instacart-adapter.md](wiki/decisions/0023-retire-instacart-adapter.md).
The nutrition decision is
[wiki/decisions/0010-usda-spoonacular-overlay.md](wiki/decisions/0010-usda-spoonacular-overlay.md).
FEWIA stores nutrition facts from USDA FoodData Central. These facts are
not a medical claim. The prototype chat can show a labeled live Kroger
price for a food with no sample price. That overlay is optional and off
by default. It appears only when the Kroger credential files are set and
the user picks a store. FEWIA stores no Kroger content. Budget acceptance
still uses the FEWIA sample-catalog cents, not the Kroger price. Every
sample-catalog estimate MUST carry this exact notice: "Estimated from the
demo price catalog. Store prices, availability, taxes, delivery fees,
and tips are not verified." Section 6.7 of
[docs/design/chat-architecture-proposal.md](docs/design/chat-architecture-proposal.md)
describes the Kroger overlay.

FEWIA does not check out or place orders. It does not submit payments. Budget
totals do not use live retailer prices. It does not train a health model. That
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

To show live Kroger prices, add the Kroger override. It reads the client
ID from `FEWIA_KROGER_CLIENT_ID_FILE` and the secret from
`FEWIA_KROGER_SECRET_FILE`. Keep both files outside the repository with
mode 600. The Kroger terms forbid credentials in an open source
repository. The Kroger account sign-in also needs a Fernet key file in
`FEWIA_KROGER_TOKEN_KEY_FILE`; see
[docs/LOCAL_GROCERY_DEMO.md](docs/LOCAL_GROCERY_DEMO.md). To use Bedrock
too, add both `-f` flags.

```bash
docker compose --env-file .env -f compose.yaml -f compose.kroger.yaml up -d
```

## Secret scanning

A gitleaks hook scans each commit for secrets. Install the hook once per
clone:

```bash
uv tool install pre-commit
pre-commit install
```

The hook scans the staged changes before each commit and blocks a commit
that holds a secret. The first run downloads gitleaks and, when Go is not
installed, a Go toolchain. The hook reads staged changes only, so
`pre-commit run --all-files` does not scan the history. Scan the whole
repository history with the gitleaks image:

```bash
docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --redact --no-banner
```

The `Secrets` workflow in `.github/workflows/secrets.yml` runs the
history scan on every push to `main` and on every pull request.
`.gitleaksignore` lists reviewed false positives by fingerprint. Do not
add an entry for a real secret. A secret in a pushed commit stays in the
history, so rotate it first. Then remove it from the files.

## Checks

Run the shared gates from the repository root:

```bash
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base origin/main
```

Run the backend checks from `backend/`:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Run the frontend checks from `frontend/`:

```bash
cd frontend
npm run lint
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
