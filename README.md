# FEWIA

FEWIA is a budget-aware grocery planning agent for CAP 6938. You chat with
it in the browser. It suggests meals from a 40-meal catalog, checks them
against your budget, builds a shopping list, and can send the list to a
grocery cart. GPT-6 Luna, through OpenAI, is the chat model. Fixed Python
code, not the model, computes every price and budget check. FEWIA never
checks out or pays. A person always places the order.

## Start FEWIA (for graders)

You need three things on your computer:

- Docker Desktop, running. FEWIA is tested with Docker Compose 5.2.
- Make and Python 3. macOS and Linux include both.
- An OpenAI API key. Create one at https://platform.openai.com/api-keys.

You do not need Kroger, AWS, or Plaid accounts.

1. Copy the example settings file. Run each command from the repository
   root, the folder that holds this README:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` in a text editor. Put your key after
   `FEWIA_OPENAI_API_KEY=`, with no quotes or spaces. Leave the other values
   as they are. Git ignores `.env`, so the key stays on your computer.

3. Start FEWIA:

   ```bash
   make up
   ```

   The first start takes several minutes, because Docker downloads and
   builds the images. `make up` prints each stage as it runs:

   ```text
   Checking .env.
   Checking the OpenAI key.
   OpenAI key accepted.
   Checking the Compose configuration.
   Downloading images.
   Building images. The first run takes several minutes.
   Starting services.
   Setting up the database and demo user.
   Waiting for the API.
   FEWIA is ready at http://127.0.0.1:5173/prototype
   ```

4. Open [`http://127.0.0.1:5173/prototype`](http://127.0.0.1:5173/prototype).

To stop FEWIA, run `docker compose down`. To start again, run `make up`.
To erase all saved data and start clean, run `docker compose down -v`.

## Try it

1. On the left, pick a meal card and set its servings. The plan summary
   shows the grocery total, the plan cap, and the shopping list.
2. Change `Plan cap`. The summary says whether the plan still fits.
3. Under `Already at home`, mark an ingredient you have. The total drops.
4. Open `Ask FEWIA` and try one of these prompts:
   - `Cheap vegetarian dinner for 2`
   - `I want something with rice and meat`
   - `Use what is in my pantry`
   - `High-protein meals`
5. Select `Add to plan` on a meal idea. When FEWIA proposes a change to
   your plan, it shows a `Proposed plan change` card with `Apply` and
   `Discard`. The model only proposes. `Apply` checks the cap, pantry, and
   diet again before it saves.
6. In the chat panel, select `Choose a fixture store for fixture prices`,
   enter any five-digit ZIP code, and pick a store. Then select
   `Connect Kroger`, `Preview fixture cart`, and `Send ... to fixture cart`.

## Demo prices and live prices

FEWIA shows prices from two sources. The plan total never uses a store
price.

| What you see | `make up` (default) | `make up-kroger-live` |
|---|---|---|
| Meal cards, plan total, cap check, shopping list | Demo price catalog `sample-prices-v2` | The same demo price catalog |
| The notice under the plan | "Estimated from the demo price catalog. Store prices, availability, taxes, delivery fees, and tips are not verified." | The same notice |
| Store search | Invented stores named `FEWIA Fixture ...` | Real Kroger stores near the ZIP code |
| Price line in a chat reply, for a food with no demo price | `Fixture price from ...`, with the label `FIXTURE, NOT KROGER` | `Live price from <store> as of <time>` |
| Kroger sign-in | A local stand-in page. No Kroger account. | The real Kroger sign-in page |
| Cart preview and cart add | Invented products. "Added to the fixture cart. No Kroger cart changed." | Real Kroger products, added to the signed-in Kroger cart |
| Needs | An OpenAI key | An OpenAI key and Kroger developer credentials |

The demo price catalog is in `backend/app/domain/catalog.py`. Its prices
are fixed, so every grader sees the same totals. Every label
`FIXTURE, NOT KROGER` marks invented data, not a Kroger result.

Fixture mode runs the same Kroger client code as live mode, with invented
responses in place of the network. Every step of the cart path therefore
works without Kroger credentials.

### Live Kroger

Live Kroger needs Kroger developer credentials, which are not in this
repository: the Kroger terms forbid credentials in an open source
repository. Put three files outside the repository, each with mode 600:
the client ID, the secret, and a Fernet token key. Set their absolute paths
in `.env` as `FEWIA_KROGER_CLIENT_ID_FILE`, `FEWIA_KROGER_SECRET_FILE`, and
`FEWIA_KROGER_TOKEN_KEY_FILE`. Then run:

```bash
make up-kroger-live
```

The app uses the Kroger certification environment. Use ZIP code `45202`,
because certification returns products there. See
[docs/LOCAL_GROCERY_DEMO.md](docs/LOCAL_GROCERY_DEMO.md) for the key file
and the redirect address.

## If something goes wrong

| What you see | What to do |
|---|---|
| `Set FEWIA_OPENAI_API_KEY in .env.` | Put your key in `.env` and run `make up` again. |
| `OpenAI rejected FEWIA_OPENAI_API_KEY (HTTP 401)` | The key is wrong, revoked, or from an inactive project. Create a new key, put it in `.env`, and run `make up` again. |
| A message about Docker, or `Docker Compose ... failed` | Start Docker Desktop and wait until it is running. Then run `make up` again. |
| `port is already allocated` | Another program uses port 5173, 8010, 55435, or 4567. Stop that program, or run `docker compose down` in another FEWIA copy. |
| `Setup did not finish.` | Run `docker compose logs bootstrap` and read the last lines. |
| The chat says `FEWIA did not answer. Your plan did not change.` | Run `docker compose logs worker`. A line with `invalid_api_key` means OpenAI rejected the key. |
| `No catalog meal matches that search.` | No catalog meal fits that request. A cost limit per serving often causes this, for example "under $10" with high protein. Ask without the cost limit, or raise the plan cap. |

## Run the tests

The tests run on the host and need [uv](https://docs.astral.sh/uv/) and
Node.js. They make no model call.

```bash
cd backend && uv run pytest
```

```bash
cd frontend && npm ci && npm test
```

Without a dedicated test database, the backend run skips the database
tests. `.claude/skills/gates/scripts/gates-with-db.sh --base main` starts a
throwaway PostgreSQL and runs every check.

## About the system

FEWIA runs as a local React and TypeScript chat with FastAPI, PostgreSQL, a
worker, a sync worker, and local Floci SQS and S3 in Docker Compose. One
file, `compose.yaml`, starts the whole stack
([decision 0030](wiki/decisions/0030-one-compose-file-luna-only.md)).
`compose.kroger.yaml` is the only overlay. Docker Compose gives the OpenAI
key to the worker as a secret file. The key is not in the container
environment, and the launcher never prints it. The OpenAI path uses
Responses `gpt-6-luna` with reasoning `none`, output limit 4096,
`store=false`, and parallel tool calls disabled. Amazon Bedrock runs only
in the evaluation command-line tools, which compare Nova with Luna. See
[the matched conversation benchmark](docs/EVALUATION.md#matched-nova-and-luna-runs).

The catalog holds 40 meals. The authoritative list is
`backend/app/domain/catalog_recipes.json`. Each request supports one to
three (1-3) meals and one to eight (1-8) servings per meal. The monthly
limit that the user enters is the whole budget. `POST /grocery/templates`
filters six preset meal combinations through the deterministic planner for
budget, diet, pantry, and exclusions. FEWIA stores nutrition facts from
USDA FoodData Central. These facts are not a medical claim. FEWIA stores no
Kroger content. Every demo-catalog estimate MUST carry the exact notice in
the price table above.

FEWIA does not check out, place orders, or submit payments
([decision 0008](wiki/decisions/0008-grocery-bot-pivot.md)). The Kroger
cart replaces the retired Instacart handoff
([decision 0023](wiki/decisions/0023-retire-instacart-adapter.md)). Plaid
Sandbox adapters stay in the code, but Plaid work is last
([decision 0016](wiki/decisions/0016-spoonacular-read-time-overlay.md)).

To make a source ZIP, run `git archive --format=zip -o fewia.zip HEAD`.
`git archive` leaves out `.env` and every other ignored file. Read
[runbooks/durable-jobs.md](runbooks/durable-jobs.md) for jobs.

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
