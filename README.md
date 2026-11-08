# FEWIA

FEWIA is a budget-aware grocery planning chat for CAP 6938. It runs as a
local React and TypeScript chat with FastAPI, PostgreSQL, a worker, and
local Floci SQS and S3 in Docker Compose. The default browser path uses
GPT-6 Luna through OpenAI. Run `make up` to check the API key setting and start the OpenAI overlay. `make up-bedrock`
selects real Amazon Bedrock through the `LLMProvider` protocol in
`backend/app/agent/`. `make up-offline` starts the base stack without a
provider, so chat is unavailable. FEWIA does not switch providers
automatically. The default spending source is `manual`. The monthly limit
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

Make, a current Docker Desktop with Docker Compose, and Python 3 are
prerequisites. FEWIA is tested with Docker Compose 5.2.
For first-time setup, copy `.env.example` to `.env` and set
`FEWIA_OPENAI_API_KEY` to an OpenAI API key from your own project. Git
ignores `.env`. Never commit it, share it, or show it on screen.
Docker Compose gives the key to the worker as a secret file. The key is not
in the container environment. The launcher uses Python 3 to check the
setting before it runs Docker Compose. `FEWIA_OPENAI_REGION` defaults to `global`. Set it to `us` for US
processing, which costs 10% more. Run the following command from the repository root.

```bash
make up
```

`make up` also starts Kroger in fixture mode. It needs no Kroger
credentials and makes no Kroger call. Store search, the Kroger sign-in,
the cart preview, and the cart add run against invented stores and
products. The page labels each fixture result `FIXTURE, NOT KROGER`. A
fixture cart add changes no Kroger cart. See
[decision 0029](wiki/decisions/0029-kroger-fixture-mode-default.md).

To make a source ZIP, run `git archive --format=zip -o fewia.zip HEAD`.
`git archive` leaves out `.env` and every other ignored file.

Open the chat at
[`http://127.0.0.1:5173/prototype`](http://127.0.0.1:5173/prototype).
Read [runbooks/durable-jobs.md](runbooks/durable-jobs.md) for jobs.

To select Bedrock explicitly, configure these values in `.env`:
`FEWIA_BEDROCK_MODEL_ID`, `FEWIA_BEDROCK_REGION`, `FEWIA_AWS_PROFILE`,
and `FEWIA_BEDROCK_CREDENTIALS_FILE`. Read
[infra/bedrock/README.md](infra/bedrock/README.md) for credentials. Then run:

```bash
make up-bedrock
```

To start the base stack without provider credentials, run:

```bash
make up-offline
```

The OpenAI path uses Responses `gpt-6-luna` with reasoning `none`, output limit
4096, `store=false`, and parallel tool calls disabled. Bedrock Nova keeps
reasoning `low`. The two providers support different reasoning settings.
See [the matched conversation benchmark](docs/EVALUATION.md#matched-nova-and-luna-runs)
for smoke, full-run, and offline comparison commands. Real OpenAI evidence
does not establish Bedrock, Plaid Sandbox, Kroger Certification, or
deployed AWS evidence.

To show live Kroger prices, use the Kroger override in place of fixture
mode. Do not combine `compose.kroger.yaml` with
`compose.kroger-fixture.yaml`: fixture mode with a Kroger credential file
fails closed. It reads the client
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
