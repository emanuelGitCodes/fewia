# Local grocery demo

This runbook starts the local Compose stack and checks it in a browser.
It does not prove deployment. It does not prove evaluation quality. For
the invitation-only hosted path, read [HOSTED_DEMO.md](HOSTED_DEMO.md).

## Scope

The local stack runs a React and TypeScript chat, FastAPI, PostgreSQL, a
worker, a sync worker, and Floci SQS and S3. Chat uses GPT-6 Luna through
OpenAI. Kroger runs in fixture mode. Bedrock serves only the evaluation
tools.

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

> Estimated from the demo price catalog. Store prices, availability,
> taxes, delivery fees, and tips are not verified.

The product has no Instacart handoff under
[decision 0023](../wiki/decisions/0023-retire-instacart-adapter.md). The
product places no orders and submits no payments.

## Start the default browser path

Make, a current Docker Desktop with Docker Compose, and Python 3 are
prerequisites. FEWIA is tested with Docker Compose 5.2.
For first-time setup, copy `.env.example` to `.env` and set
`FEWIA_OPENAI_API_KEY` to an OpenAI API key from your own project. Set
`.env` to mode `0600` before launch. Git ignores `.env`.
Never commit it, share it, or show it on screen.
`FEWIA_OPENAI_REGION` defaults to `global`. Set it to `us` for US
processing, which costs 10% more.

From the repository root, start the default browser path:

```bash
make up
```

`make up` runs `compose.yaml` through `infra/openai/compose-up.sh`. The
launcher prints stage lines and checks the OpenAI key. HTTP 401 or 403
stops it before any build. `FEWIA_SKIP_KEY_CHECK=1` skips the check. It
then shows Compose progress and waits for the `bootstrap` service and the
API. The launcher manages private local password and pairing state.
It rotates the internal database administrator password before bootstrap.
The `bootstrap` service prepares separate administrator and application
database roles, runs migrations, seeds the demo user, and
provisions the Floci resources. It then exits with code 0. `api`,
`worker`, and `sync-worker` start after it completes. The launcher prints
the app address when the API is ready.

The browser listens at
[`http://127.0.0.1:5173/prototype`](http://127.0.0.1:5173/prototype).

## Live Kroger

To use live Kroger instead of fixture mode, set the three Kroger file
variables in `.env` as described in
[Optional Kroger overlay](#optional-kroger-overlay). Then run:

```bash
make up-kroger-live
```

There is no offline mode. Without a working OpenAI key, `make up` fails.

Find the running API and its Compose project without loading launcher secrets:

```bash
docker ps --filter 'label=com.docker.compose.service=api' --format 'table {{.ID}}\t{{.Label "com.docker.compose.project"}}\t{{.Status}}\t{{.Ports}}'
```

Match the project to the stack just launched. The API status MUST show
healthy. Inspect other services with a filter for that exact project label.

[`compose.yaml`](../compose.yaml) binds these loopback host ports by default:

| Service | Host variable | Default host port | Container port |
| --- | --- | --- | --- |
| Web | `WEB_HOST_PORT` | 5173 | 8080 |
| API | `API_HOST_PORT` | 8010 | 8000 |
| PostgreSQL | Unpublished | None | 5432 |
| Floci | Unpublished | None | 4566 |

`make up-tools` uses the launcher with `compose.tools.yaml`. It adds
the Floci endpoint at `http://127.0.0.1:4566` to the default web and API ports.
PostgreSQL stays unpublished. Floci proves local SQS and S3 integration
behavior only. It provides no real AWS evidence.

Open `http://127.0.0.1:5173/prototype`. The web container redirects `/` to
`/prototype`, serves the older page at `/app`, and forwards `/api/` to the API.

The current launcher path expects the frontend origin
`http://127.0.0.1:5173`. Use that exact origin, including the port.
The Compose files do not wire `FEWIA_PUBLIC_ORIGIN` into the API.
Changing `WEB_HOST_PORT` or Kroger URLs alone does not configure another
accepted browser origin. Another hostname or port needs separate wiring
and verification. Do not delete another project's volumes.

## Try the demo

Open `http://127.0.0.1:5173/app`. These controls are on the older page.

1. Select "Bean tacos for two". The estimate shows $17.03 and the sample
   notice.
2. Select "I have olive oil" in the estimate. The heading changes to
   "Previous estimate".
3. Select "Rebuild estimate". The new estimate shows $11.04.

These totals come from the sample catalog on the current `main`. A
catalog change MAY change them.

## Bedrock settings

Bedrock serves only the evaluation command-line tools
(`python -m app.evaluate` and `app.evaluate_conversation`). They run
outside Docker and compare Nova with Luna. The browser stack does not use
Bedrock. Bedrock uses real service endpoints. Bedrock credentials stay
separate from the Floci dummy credentials. Do not set a global AWS
endpoint.

Copy `.env.example` to `.env`. Set mode `0600`. Git ignores `.env`. Do not
paste secret values or host paths into this runbook. Follow
[`infra/bedrock/README.md`](../infra/bedrock/README.md) for the role and
the host MFA helper. No Docker overlay for Bedrock exists.

## Optional Kroger overlay

The Kroger client ID and client secret MUST live in two host files outside
the repository, mode 600. The Kroger API terms forbid credentials, client
IDs included, in an open source repository. Set
`FEWIA_KROGER_CLIENT_ID_FILE` and `FEWIA_KROGER_SECRET_FILE` in `.env` to
the absolute paths. `FEWIA_KROGER_ENVIRONMENT` defaults to
`certification`; set it to `production` only after Kroger approves the app.

[`compose.yaml`](../compose.yaml) runs Kroger in fixture mode. Fixture
mode needs no Kroger files and makes no Kroger call. The steps below set
up live Kroger instead.

[`compose.kroger.yaml`](../compose.kroger.yaml) is the live Kroger overlay.
`make up-kroger-live` selects it through the launcher. It mounts both
files read-only into `api` and `worker`. Direct Compose startup lacks
the launcher's generated private file paths and host user settings.

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
a redirect URI. Keep the API on port 8010 for this registered callback.
The return URL defaults to `http://127.0.0.1:5173/prototype` and MUST NOT
hold a query. The overlay passes `FEWIA_KROGER_REDIRECT_URI` and
`FEWIA_KROGER_RETURN_URL`, but these settings do not change the API's
accepted browser origin. This runbook uses only the default ports and
exact frontend origin above.

After `make up-kroger-live`, pair the operator's browser before live calls.
Use the API discovery command above. Select the exact running API
container in the project just started in live mode. Do not select another
project's API. In a private terminal, run:

```bash
LIVE_API_CONTAINER='EXACT_RUNNING_LIVE_API_CONTAINER_ID'
docker exec "$LIVE_API_CONTAINER" python -m app.kroger_pairing_cli --user-id 1
```

Use the existing container environment. Do not reconstruct launcher
variables or print container secrets. The output is one single-use
`#kroger-pair=...` fragment. Append it privately to the configured frontend
URL in the same browser tab within five minutes. For the default stack,
use `http://127.0.0.1:5173/prototype` followed by that fragment.
The redeemed proof lasts eight hours in that tab. Do not share, capture,
log, or persist the link. A new tab needs its own pairing. Fixture mode
needs no pairing.

On `/prototype`, choose a Kroger store in the chat panel. When a chat reply
swaps in or looks up a food with no sample price, the API adds one live
Kroger price as it serves the reply. The application MUST NOT store Kroger
content. Plan acceptance and every total use sample catalog cents only.

GPT-6 Luna with live Kroger:

```bash
make up-kroger-live
```

## Health and capability

`GET /api/healthz` through the web port checks API process health.

`GET /api/grocery/providers` reports configuration flags. That response is
not provider proof.

## Host checks and request limits

The API accepts a request only when its `Host` header names `localhost`,
`127.0.0.1`, `[::1]`, `api`, or a host in `FEWIA_ALLOWED_HOSTS`. The
variable is a comma-separated list of host names with no port and no
wildcard. Another host gets HTTP 400.

The web container checks the `Host` header on `/api/` when
`FEWIA_WEB_HOST_CHECK` is `local`. `compose.yaml` sets `local`. The image
default is `off`, because the hosted load balancer filters the host. A
host that is not `localhost`, `127.0.0.1`, or `[::1]` gets HTTP 421.

The API serves `/docs`, `/redoc`, and `/openapi.json` only when
`FEWIA_API_DOCS` is `1`.

Browser mutations also need an accepted `Origin` and valid workspace access.
Use the exact frontend origin above. A permitted `Host` does not replace
the Origin or workspace checks.

Each owner can submit 20 new agent jobs per 60 seconds across chat and plan
requests combined. Queued and running jobs share a concurrency limit of
3 per owner and 200 across all owners, including sync jobs.
A request over a limit gets HTTP 429 with `Retry-After: 60`.
An idempotent retry with the same request key and matching content returns
the accepted job without consuming another submission or concurrency slot.

The backend containers use the launcher's host UID and GID with no
capabilities. The `api`,
`bootstrap`, and `sync-worker` containers have a read-only root file
system. The `worker` container has a writable root file system, because
Compose mounts the OpenAI key secret only into a writable one. A Kroger
key file MUST be readable by that user inside the container.

## Checks

Run the repository gates and tests from the repository root:

```bash
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

```bash
cd backend && uv run pytest
```

`uv run pytest` runs on one process. Add `-n auto` to run the suite on
workers; the gates and CI pass that flag.

```bash
cd frontend && npm run lint && npm test && npm run build
```

The browser suite drives the running stack. Follow
[`frontend/tests/e2e/README.md`](../frontend/tests/e2e/README.md). CI does
not run it.

The evaluation runbook is [EVALUATION.md](EVALUATION.md).

## Stop the stack

There is no Make stop target. List running containers for the exact
project before stopping them:

```bash
docker ps --filter 'label=com.docker.compose.project=EXACT_PROJECT_NAME' --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'
docker stop EXACT_CONTAINER_ID
```

Repeat `docker stop` for each listed container in that project.
This keeps PostgreSQL and Floci volumes. Delete volumes only when you
intend to delete the local demo data.
