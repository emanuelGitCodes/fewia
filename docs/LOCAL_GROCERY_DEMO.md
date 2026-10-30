# Local grocery demo

This runbook starts the local Compose stack and checks it in a browser.
It does not prove deployment. It does not prove evaluation quality. For
the invitation-only hosted path, read [HOSTED_DEMO.md](HOSTED_DEMO.md).

## Scope

The local stack runs a React and TypeScript chat, FastAPI, PostgreSQL, a
worker, a sync worker, and Floci SQS and S3. Real Bedrock handles chat
when the Bedrock overlay is on. The base stack runs without Bedrock, and
the chat panel then shows "Meal chat is unavailable."

The catalog holds 40 meals under
[decision 0017](../wiki/decisions/0017-forty-meal-catalog.md). A request
MAY include one to three (1-3) meals. Each meal MAY use one to eight
(1-8) servings. The accepted scope is in
[`.codex/project-context.md`](../.codex/project-context.md). Newer
decisions in [`wiki/decisions/`](../wiki/decisions/) override it.

The default spending source is `manual`. The monthly limit that the user
enters is the whole budget. The form starts at USD 100 per month and a
USD 40 plan cap. Plans do not reserve money. Plaid work is last.

Sample catalog prices are the budget figure under
[decision 0016](../wiki/decisions/0016-spoonacular-read-time-overlay.md).
Every estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability,
> taxes, delivery fees, and tips are not verified.

The product has no Instacart handoff under
[decision 0023](../wiki/decisions/0023-retire-instacart-adapter.md). The
product places no orders and submits no payments.

## Start the base stack

From the repository root, start the stack:

```bash
docker compose up -d
```

The base stack needs no `.env` file and no provider credentials. The
`bootstrap` service runs the migrations, seeds the demo user, and
provisions the Floci resources. It then exits with code 0. `api`,
`worker`, and `sync-worker` start after it completes.

Check that each service is up and that `api` is healthy:

```bash
docker compose ps
```

[`compose.yaml`](../compose.yaml) binds these loopback host ports:

| Service | Host variable | Default host port | Container port |
| --- | --- | --- | --- |
| Web | `WEB_HOST_PORT` | 5173 | 8080 |
| API | `API_HOST_PORT` | 8010 | 8000 |
| PostgreSQL | `POSTGRES_HOST_PORT` | 55435 | 5432 |
| Floci | `FLOCI_HOST_PORT` | 4567 | 4566 |

Open `http://127.0.0.1:5173`. The web container serves the app and
forwards `/api/` to the API.

A second Compose project MUST use a unique project name and unused host
ports. Do not delete the volumes of another project. Example:

```bash
API_HOST_PORT=8020 WEB_HOST_PORT=5183 POSTGRES_HOST_PORT=55445 FLOCI_HOST_PORT=4577 docker compose -p fewia-alt up -d --build
```

## Try the demo

1. Select "Bean tacos for two". The estimate shows $17.03 and the sample
   notice.
2. Select "I have olive oil" in the estimate. The heading changes to
   "Previous estimate".
3. Select "Rebuild estimate". The new estimate shows $11.04.

These totals come from the sample catalog on the current `main`. A
catalog change MAY change them.

## Optional Bedrock chat

Bedrock uses real service endpoints. Bedrock credentials stay separate
from the Floci dummy credentials. Do not set a global AWS endpoint.

Copy `.env.example` to `.env`. Set mode `600`. Git ignores `.env`. Do not
paste secret values or host paths into this runbook. Follow
[`infra/bedrock/README.md`](../infra/bedrock/README.md) for the role and
the host MFA helper. Then layer
[`compose.bedrock.yaml`](../compose.bedrock.yaml):

```bash
docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml up -d
```

The overlay mounts the credentials file into `api` and `worker` only.

## Optional Kroger overlay

The Kroger client ID and client secret MUST live in two host files outside
the repository, mode 600. The Kroger API terms forbid credentials, client
IDs included, in an open source repository. Set
`FEWIA_KROGER_CLIENT_ID_FILE` and `FEWIA_KROGER_SECRET_FILE` in `.env` to
the absolute paths. `FEWIA_KROGER_ENVIRONMENT` defaults to
`certification`; set it to `production` only after Kroger approves the app.

[`compose.kroger.yaml`](../compose.kroger.yaml) mounts both files
read-only into `api` and `worker`:

```bash
docker compose --env-file .env -f compose.yaml -f compose.kroger.yaml up -d
```

The overlay also needs a token key file for the Kroger account sign-in.
The API uses this Fernet key to encrypt the customer tokens it stores.
Create the key once, outside the repository, without showing it:

```bash
uv run --with cryptography python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > ~/.config/fewia/kroger/token-key
```

```bash
chmod 600 ~/.config/fewia/kroger/token-key
```

Set `FEWIA_KROGER_TOKEN_KEY_FILE` in `.env` to its absolute path. The
overlay mounts it read-only into `api` only.

The Kroger app MUST list `http://localhost:8010/grocery/kroger/callback` as
a redirect URI. To use another API port or frontend address, set
`FEWIA_KROGER_REDIRECT_URI` and `FEWIA_KROGER_RETURN_URL`. The return URL
defaults to `http://127.0.0.1:5173/prototype` and MUST NOT hold a query.

On `/prototype`, choose a Kroger store in the chat panel. When a chat reply
swaps in or looks up a food with no sample price, the API adds one live
Kroger price as it serves the reply. The application MUST NOT store Kroger
content. Plan acceptance and every total use sample catalog cents only.

Both overlays together:

```bash
docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml -f compose.kroger.yaml up -d
```

## Health and capability

`GET /api/healthz` through the web port checks API process health.

`GET /api/grocery/providers` reports configuration flags. That response is
not provider proof.

## Checks

Run the repository gates and tests from the repository root:

```bash
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

```bash
cd backend && uv run pytest
```

```bash
cd frontend && npm run lint && npm test && npm run build
```

The browser suite drives the running stack. Follow
[`frontend/tests/e2e/README.md`](../frontend/tests/e2e/README.md). CI does
not run it.

The evaluation runbook is [EVALUATION.md](EVALUATION.md).

## Stop the stack

```bash
docker compose down
```

`docker compose down` keeps the PostgreSQL and Floci volumes. Add `-v`
only to delete the local demo data on purpose.
