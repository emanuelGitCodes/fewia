# Grocery evaluation commands

This guide records current evaluation commands for the local grocery stack.
It does not prove model quality.
It does not prove deployment.

The local product is React and TypeScript chat, FastAPI, PostgreSQL, a worker,
and Floci SQS and S3 paths. Real Bedrock is the approved model path.
Plaid Sandbox adapters exist. Instacart development shopping links stay parked
under [decision 0010](../wiki/decisions/0010-usda-spoonacular-overlay.md).

The catalog supports ten meals: chicken tacos, bean tacos, vegetable pasta,
chicken-and-rice bowls, lentil soup, chickpea curry, vegetable stir-fry,
baked potatoes with beans, breakfast burritos, and overnight oats.
A request uses one to three (1-3) meals.
Each meal uses one to eight (1-8) servings.

Every estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Writers MUST separate deterministic, sandbox, live, and deployed evidence.
Fixture or sample data MUST NOT become verified retailer, financial, or
population claims.

Corpus and scoring sources:

- [backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json)
- [backend/app/evaluate.py](../backend/app/evaluate.py)
- [backend/app/evaluation_report.py](../backend/app/evaluation_report.py)
- [docs/GROCERY_VERIFICATION_PLAN.md](GROCERY_VERIFICATION_PLAN.md)

## Fixture batch

Start at the repository root.
Then change into `backend`.
`--revision` MUST be 40 lowercase hexadecimal characters.
`$(git rev-parse HEAD)` supplies that value.
`--output` MUST be a new path that does not already exist.

```bash
cd backend
mkdir -p ../artifacts/evaluation
uv run python -m app.evaluate \
  --mode fixture \
  --revision "$(git rev-parse HEAD)" \
  --output ../artifacts/evaluation/fixture-20260922.json
```

The CLI writes JSON at `--output` and a sibling `.jsonl` journal.
The CLI MUST NOT overwrite an existing output or journal.
A second run of the same command refuses those existing files.
The CLI does not resume an interrupted run.

A later fixture CLI scored 51 pass and 39 unassessed.
That run includes P02 batch routing.
Keep that count separate from live mixed batches.

## Report CLI

The report CLI exists.
It reads a batch JSON file.
It writes Markdown.
It does not call providers.

`--rates` is integrated at primary branch 57, source `21c7f3d`.
The CLI reads explicit dated rates.
It requires the recorded model and region.
It MUST NOT default, fetch, or guess rates.
A model or region mismatch fails.

The fixture batch records `model_id` and `source_region` as null.
The first fixture report example MUST omit `--rates`.
`--rates` on that fixture file MUST fail.

```bash
cd backend
uv run python -m app.evaluation_report \
  --input ../artifacts/evaluation/fixture-20260922.json \
  --output ../artifacts/evaluation/fixture-20260922.md
```

Run the live Bedrock batch first.
Use that output file `../artifacts/evaluation/bedrock-20260922.json`.
Pass `--rates` only after that live batch exists.
Use the recorded model and region from that file.
Those values MUST match the rate file.
The operator MUST NOT guess model or region.

```bash
cd backend
uv run python -m app.evaluation_report \
  --input ../artifacts/evaluation/bedrock-20260922.json \
  --output ../artifacts/evaluation/bedrock-20260922.md \
  --rates tests/evaluation/pricing/nova2-lite-use1-20260922.json
```

`--input` MUST be an existing batch JSON file.
`--output` MUST be a new Markdown path.
The CLI MUST NOT overwrite an existing report.
A second run of the same command refuses those existing files.

The report preserves unknown usage.
The CLI accepts only `metrics_status` `unassessed`.
The CLI MUST NOT certify global quality.
The current mixed-batch report estimates USD 0.13718265.
That figure is not billing.
The old 45/24/21 mixed-run estimate USD 0.13163909 stays separate.

## Live mixed batches — keep runs separate

Do not merge these runs.

Old mixed live batch at revision
`f6f633539afec4e38b77c00e830ca0ad9f76b3ca`:

- 90 slots
- 45 fixture pass
- 24 real completed
- 21 unassessed
- Final-plan replay: 12 pass, 3 fail (A01 omitted request cap), 9 clarification unassessed

New mixed live batch at revision
`18bb537cf655a6dd3a15aea522a034ff3cc2e3a9`:

- 90 slots
- 51 fixture
- 24 real
- 15 unassessed
- 0 execution failed
- Final-plan replay: 11 pass, 4 fail
- Failures: 3 A01 cap null, and F02 repeat 2 retained black beans after buy-again
- 9 clarifications unassessed
- Model `us.amazon.nova-2-lite-v1:0` in region `us-east-1`

Do not change 15 unassessed to 12.
P05 batch routing remains pending.

Historical pantry-fix retest: F02 five and F05 three passed.
That same retest failed three A01 observations.
That record remains historical.

Explicit cap context is integrated at branch 58, source `44fe333`.
The path passes the parsed plan cap into model context and the prompt.
It does not mutate scores or gold.
It does not silently normalize arguments.
Bounded live retest 11 all passed: A01 five, F02 three, F05 three.
These retests stay separate from the full 90-slot batch.
The full 90-slot source `18bb537cf655a6dd3a15aea522a034ff3cc2e3a9` stays 11 pass and 4 fail.
These bounded passes are not a universal quality claim.

## Structured reference

`observe_reference_case` in
[backend/app/evaluation_reference.py](../backend/app/evaluation_reference.py)
supports F01, F02, F05, X04, and A01.
It uses structured inputs.
It does not interpret language.
It does not persist evidence.
The comparison driver remains pending until the coordinator verifies.

## P05 isolated PostgreSQL and Floci

P05 opt-in integration is local proof on an isolated stack.
It is not evaluator batch routing.
It is not deployed AWS.
It is not live Instacart.

Start a unique Compose project from the repository root.
Ensure host ports 55440 and 4566 are free.

```bash
POSTGRES_HOST_PORT=55440 FLOCI_HOST_PORT=4566 \
  docker compose --env-file /dev/null -p fewia-p05-check -f compose.yaml \
  up -d postgres floci
```

Bootstrap Floci:

```bash
uv run --project backend python -m infra.floci_bootstrap \
  --endpoint http://127.0.0.1:4566
```

From `backend`:

```bash
FEWIA_P05_DATABASE_URL=postgresql+psycopg://fewia:fewia@127.0.0.1:55440/fewia \
FEWIA_P05_FLOCI_ENDPOINT=http://127.0.0.1:4566 \
  uv run pytest -q tests/test_p05_local_integration.py
```

[backend/tests/p05_resources.py](../backend/tests/p05_resources.py)
requires both environment variables.
It rejects a non-local host and a query override.
It does not fall back to `DATABASE_URL`.
It owns a UUID schema, queue, and object keys.
The test cleans those owned resources.

Stop only the named project `postgres` and `floci` services.
Preserve volumes.
Do not delete the database, bucket, or volumes.

Observed opt-in proof: two SQS deliveries, one job, one attempt, one handler,
one evidence row.
Twice prepare and dispatch, one handoff, one fake call.
Actual Floci S3 canonical bytes and hash verified.
Owned resources cleaned.

Full-source P05 with opt-in passed 1,984 tests.
That dated verification is in [wiki/log.md](../wiki/log.md)
under `2026-09-22 — P05 local end-to-end evidence`.

## Real Bedrock

Bedrock mode uses an externally configured provider environment.
Follow [docs/LOCAL_GROCERY_DEMO.md](LOCAL_GROCERY_DEMO.md) and
[infra/bedrock/README.md](../infra/bedrock/README.md).
Do not invent credentials.
Do not paste secrets into this guide.

Example evaluate mode:

Use a different new output path for live Bedrock.

```bash
cd backend
mkdir -p ../artifacts/evaluation
uv run python -m app.evaluate \
  --mode bedrock \
  --revision "$(git rev-parse HEAD)" \
  --output ../artifacts/evaluation/bedrock-20260922.json
```

`--mode bedrock` requires a configured provider.
Missing configuration fails without writing a quality claim.

## Evidence classes

| Class | What it may prove |
| --- | --- |
| Deterministic | Catalog facts, planner arithmetic, fixture guards |
| Fixture | Demo spending and sample catalog prices |
| Emulator | Floci SQS jobs and Floci S3 export paths |
| Sandbox | Plaid Sandbox posted and pending grocery spend |
| Live | Real Bedrock and request-only Spoonacular overlay |
| Deployed | Public hosting and production AWS |

P05 isolated proof is local PostgreSQL, worker, Floci SQS, and Floci S3.
It is not deployed evidence.

## Related records

- [plans/APP_COMPLETION_BACKLOG.md](../plans/APP_COMPLETION_BACKLOG.md)
- [wiki/phases/grocery-completion-20260922.md](../wiki/phases/grocery-completion-20260922.md)
- [docs/GROCERY_VERIFICATION_PLAN.md](GROCERY_VERIFICATION_PLAN.md)
