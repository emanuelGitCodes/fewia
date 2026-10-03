# Evaluation

## Scope

FEWIA runs a local React and TypeScript chat with a FastAPI backend, PostgreSQL, a worker, and Floci SQS and S3. The product uses real Bedrock through `LLMProvider`. Plaid and Instacart live-provider evidence is not part of this checkpoint. The product uses a manual budget and sample catalog prices. A development shopping link, when present, proves handoff only. It does not verify retailer products or prices. The product does not place orders or check out.

The first release supports 40 meals under [decision 0017](../wiki/decisions/0017-forty-meal-catalog.md). A request supports one to three (1-3) meals. Each meal supports one to eight (1-8) servings.

The local integration record is [the evaluation completion checkpoint](../wiki/phases/evaluation-completion.md).

Every grocery estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Current API

[`run_evaluation`](../backend/app/evaluation_runner.py) is an existing fixture-only Python API. It accepts a scenario corpus and returns three repeated slots per scenario. It scores budget and meal cases, plus follow-up and missing-input cases that do not require a model. Other slots remain `unassessed`. The component smoke recorded 42 scored passes and 48 unassessed slots for this legacy runner.

There is no complete benchmark CLI or batch entrypoint yet. Do not run or document `python -m app.evaluate` as an available command.

[`prepare_matrix`](../backend/app/evaluation_matrix.py) is a pure matrix-preparation API. It checks a finite JSON `grocery-eval-v1` corpus, catalog version, three repeats, scenario IDs and groups, required inputs, and expected result shapes. It returns isolated copies of execution slots. It does not execute the slots.

The planned matrix has 90 primary slots: 42 `deterministic_fixture`, 15 `controlled_fixture`, and 33 `tool_enabled`. It adds 33 `no_tool` baseline slots and 15 deterministic structured-reference slots, for 138 planned slots total. Planning these slots does not execute them. The 90 primary slots and 138 total slots have not run as a benchmark.

## Component boundaries

- [`observe_reference_case`](../backend/app/evaluation_reference.py) runs the final structured request for five supported reference scenarios through deterministic planning. It does not run earlier language turns or a durable evidence store.
- The approved claim and task helpers use public outputs, bounded claims, strict task criteria, explicit denominators, and visible unknown counts. They keep fixture, reference, and model quality separate. A passing helper does not prove a live provider result.
- Provider drivers cover controlled failures and duplicate delivery. A driver exercises only its named condition.
- [`summarize_telemetry`](../backend/app/evaluation_telemetry.py) groups captured observations by condition and evidence class. It reports known totals and unknown counts separately.
- [`summarize_evaluation`](../backend/app/evaluation_summary.py) validates identities, groups observations by condition and evidence class, and preserves metric and task scopes and unknown counts. Partial matrices remain partial.
- [`estimate_cost`](../backend/app/evaluation_cost.py) uses dated rate inputs and captured token counts. It reports known values as lower bounds when usage is incomplete. It is not an invoice or billing reconciliation.
- [`evaluation_io`](../backend/app/evaluation_io.py) writes exclusive journal and report files. Its completion marker records hashes for the JSON and Markdown reports.

The component set supports separate measurement of deterministic fixtures, structured references, controlled provider conditions, and model observations. It does not provide a general guarantee against hallucinations. The task-success and supported-claim targets are not certified by these component checks.

## Database validation

Set both database URLs to reachable, isolated test databases. CI supplies `FEWIA_JOB_TEST_DATABASE_URL` and `FEWIA_EVALUATION_DATABASE_URL`. When `FEWIA_REQUIRE_DB=1`, a missing required evaluation URL fails validation.

```sh
FEWIA_JOB_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/JOB_TEST_DB \
FEWIA_EVALUATION_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/EVALUATION_DB \
FEWIA_REQUIRE_DB=1 \
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

Configure both URLs for isolated test databases. Keep credentials out of the documentation and source files.

## Evidence and provenance

Keep deterministic, sandbox, live-provider, and deployed evidence in separate groups. Do not pool fake-provider success with live-provider success. Mark samples and unknown values. A scenario matrix is a plan until its execution record exists.

Each evidence-table row MUST identify its source, source revision, evidence class, scope, date, and denominator. Keep citations and provenance with the row.
