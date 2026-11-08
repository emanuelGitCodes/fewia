# FEWIA

FEWIA is a budget-aware grocery planning chat for CAP 6938. It runs as a
local React and TypeScript chat with FastAPI, PostgreSQL, a worker, and
local Floci SQS and S3 in Docker Compose. One file, `compose.yaml`, starts
the whole stack. The chat model is always GPT-6 Luna through OpenAI. Amazon
Bedrock runs only in the evaluation command-line tools, which compare it
with Luna. See [decision 0030](wiki/decisions/0030-one-compose-file-luna-only.md). The default spending source is `manual`. The monthly limit
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
not a medical claim. The prototype chat can show a labeled Kroger price
for a food with no sample price after the user picks a store. With
`make up`, the price comes from the fixture and carries the label
`FIXTURE, NOT KROGER`. A live Kroger price needs `make up-kroger-live`. FEWIA stores no Kroger content. Budget acceptance
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

You need Make, Python 3, and Docker Desktop with Docker Compose. FEWIA is
tested with Docker Compose 5.2. Start Docker Desktop before you begin.

1. Copy the example settings file:

   ```bash
   cp .env.example .env
   ```

2. Open `.env`. Set `FEWIA_OPENAI_API_KEY` to an OpenAI API key from your
   own project. `FEWIA_OPENAI_REGION` defaults to `global`. Set it to `us`
   for US processing, which costs 10% more and needs a key from a project
   with US data residency. Git ignores `.env`. Never commit it, share it, or
   show it on screen.

3. Start FEWIA from the repository root:

   ```bash
   make up
   ```

4. Open [`http://127.0.0.1:5173/prototype`](http://127.0.0.1:5173/prototype).

`make up` prints one line per stage: the `.env` check, the OpenAI key check,
the configuration check, the image download, the image build, the service
start, the database and demo user setup, and the API health check. Docker
Compose shows its own download and build progress between those lines. The
first run takes several minutes. The last line prints the app address.

`make up` stops before it builds anything when the key is missing or OpenAI
rejects it. Create a new key at https://platform.openai.com/api-keys, put it
in `.env`, and run `make up` again. Without a working OpenAI key, FEWIA does
not start.

Docker Compose gives the key to the worker as a secret file. The key is not
in the container environment, and the launcher never prints it.

`make up` also starts Kroger in fixture mode. It needs no Kroger
credentials and makes no Kroger call. Store search, the Kroger sign-in,
the cart preview, and the cart add run against invented stores and
products. The page labels each fixture result `FIXTURE, NOT KROGER`. A
fixture cart add changes no Kroger cart. See
[decision 0029](wiki/decisions/0029-kroger-fixture-mode-default.md).

To stop FEWIA, run `docker compose down`. To make a source ZIP, run
`git archive --format=zip -o fewia.zip HEAD`. `git archive` leaves out
`.env` and every other ignored file. Read
[runbooks/durable-jobs.md](runbooks/durable-jobs.md) for jobs.

The OpenAI path uses Responses `gpt-6-luna` with reasoning `none`, output
limit 4096, `store=false`, and parallel tool calls disabled. See
[the matched conversation benchmark](docs/EVALUATION.md#matched-nova-and-luna-runs)
for the Bedrock Nova comparison commands.

### Live Kroger

Live Kroger replaces fixture mode. It needs three files outside the
repository, each with mode 600: the client ID in
`FEWIA_KROGER_CLIENT_ID_FILE`, the secret in `FEWIA_KROGER_SECRET_FILE`, and
a Fernet key in `FEWIA_KROGER_TOKEN_KEY_FILE`. Set the three absolute paths
in `.env`. The Kroger terms forbid credentials in an open source repository.
See [docs/LOCAL_GROCERY_DEMO.md](docs/LOCAL_GROCERY_DEMO.md). Then run:

```bash
make up-kroger-live
```

`make up-kroger-live` adds `compose.kroger.yaml`, the only overlay.

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
