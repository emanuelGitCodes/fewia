# Local grocery demo

This runbook starts the local Compose stack. It does not prove deployment.
It does not prove evaluation quality.

Copy `.env.example` to `.env`. Set mode `600`. Git ignores `.env`.
Keep `.env` private. Do not paste host paths or secret values into this
runbook.

The base fixture stack does not require Spoonacular credentials.

The local stack is React and TypeScript chat, FastAPI, PostgreSQL, worker,
and Floci SQS and S3 paths. Bedrock is real when the overlay is on.
Plaid Sandbox and Instacart development shopping links stay unverified
in this fixture path.

The catalog supports ten meals: chicken tacos, bean tacos, vegetable
pasta, chicken-and-rice bowls, lentil soup, chickpea curry, vegetable
stir-fry, baked potatoes with beans, breakfast burritos, and overnight
oats. Each request MAY include one to three (1-3) meals. Each meal MAY
use one to eight (1-8) servings.

Sample catalog prices MUST stay labeled as estimates. Show this notice
with every estimate:

> Estimated from the demo price catalog. Instacart prices, availability,
> taxes, delivery fees, and tips are not verified.

## Base stack

From the repository root, start the default fixture stack:

```bash
docker compose -p fewia-demo up -d --build
```

[`compose.yaml`](../compose.yaml) binds these loopback host ports by
default:

| Service | Host variable | Default host port | Container port |
| --- | --- | --- | --- |
| API | `API_HOST_PORT` | 8010 | 8000 |
| Web | `WEB_HOST_PORT` | 5173 | 80 |
| PostgreSQL | `POSTGRES_HOST_PORT` | 55435 | 5432 |
| Floci | `FLOCI_HOST_PORT` | 4567 | 4566 |

Floci listens on container port 4566. The host bind is loopback only.

A parallel Compose project MUST use a unique project name. It MAY
override the four host ports. Those ports MUST be unused on the host
at start time. Isolated ports from another runtime are not a free-port
guarantee. Do not delete Compose volumes for a parallel project.

Example:

```bash
API_HOST_PORT=8011 WEB_HOST_PORT=5174 POSTGRES_HOST_PORT=55436 FLOCI_HOST_PORT=4568 \
  docker compose -p fewia-demo-alt up -d --build
```

One isolated runtime used host ports 5178, 8015, 55439, and 4571.
Those values are an example. Do not treat them as repository defaults.
They MAY be occupied on this host.

## Optional Bedrock

Bedrock uses real service endpoints. Bedrock credentials stay separate
from Floci dummy credentials. Do not set a global AWS endpoint.

Follow [`infra/bedrock/README.md`](../infra/bedrock/README.md) for the
host MFA helper and [`compose.bedrock.yaml`](../compose.bedrock.yaml).
Example:

```bash
docker compose -p fewia-demo --env-file .env -f compose.yaml -f compose.bedrock.yaml up -d --build
```

## Optional Spoonacular overlay

The Spoonacular key MUST live in a host file outside the repository.
Set `FEWIA_SPOONACULAR_KEY_FILE` in `.env` to that absolute path.
Do not put the key value in Compose, images, logs, or `.env.example`.

[`compose.spoonacular.yaml`](../compose.spoonacular.yaml) mounts the key
file into `api` only. It does not add worker, bootstrap, web, or Floci
mounts.

The container path is `/run/fewia/spoonacular-key`.
Compose sets `FEWIA_SPOONACULAR_KEY_FILE=/run/fewia/spoonacular-key` in `api`.
The host bind source is `${FEWIA_SPOONACULAR_KEY_FILE:?Set FEWIA_SPOONACULAR_KEY_FILE to an absolute host path outside the repository}`.
`create_host_path` is false.

An absent `FEWIA_SPOONACULAR_KEY_FILE` variable triggers Compose
interpolation help. A set variable whose host path does not exist fails
the bind. Those are different errors.

Layer the files. Pass `.env` for interpolation:

```bash
docker compose -p fewia-demo --env-file .env -f compose.yaml -f compose.spoonacular.yaml up -d --build
```

Bedrock and Spoonacular together:

```bash
docker compose -p fewia-demo --env-file .env -f compose.yaml -f compose.bedrock.yaml -f compose.spoonacular.yaml up -d --build
```

Spoonacular calls are request-only. The stack MUST NOT persist vendor prices.

## Demo data

The default spending source is the fixture.
Nutrition facts follow the USDA catalog path. They are not a medical claim.

Plaid Sandbox credentials are absent in this setup. Live Plaid is unverified.
Instacart stays parked. See
[`wiki/decisions/0010-usda-spoonacular-overlay.md`](../wiki/decisions/0010-usda-spoonacular-overlay.md).

## Health and capability

`GET /healthz` checks API process health.

`GET /grocery/providers` reports configuration flags.
That response is not provider proof.

## Fixture evaluation

Run the typed host CLI from `backend`. Pass the current 40-character
lowercase hex git revision. Write a new output file outside the
repository.

```bash
uv run python -m app.evaluate --mode fixture --revision "$(git rev-parse HEAD)" --output /absolute/path/outside/repo/fixture-eval.json
```

`evaluation_batch._corpus_ok` accepts 30 scenarios and 3 repeats.
That matrix is 90 slots. The slot count is the corpus contract. It is
not quality proof.

## Further checks

Follow [`GROCERY_VERIFICATION_PLAN.md`](GROCERY_VERIFICATION_PLAN.md)
for the scenario matrix. Follow
[`frontend/e2e/README.md`](../frontend/e2e/README.md) for browser fakes.
Those suites do not claim complete benchmark or deployment evidence.
