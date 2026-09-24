# Grocery completion record — 2026-09-22

- **Status**: local grocery completion in progress. This is not a completed product. This is not a deployed release.
- **Accepted brief**: [`.codex/project-context.md`](../../.codex/project-context.md)
- **Backlog**: [`plans/APP_COMPLETION_BACKLOG.md`](../../plans/APP_COMPLETION_BACKLOG.md)
- **Local demo runbook**: [`docs/LOCAL_GROCERY_DEMO.md`](../../docs/LOCAL_GROCERY_DEMO.md)
- **Evaluation commands**: [`docs/GROCERY_EVALUATION.md`](../../docs/GROCERY_EVALUATION.md)
- **Historical checkpoint**: [`grocery-mvp-checkpoint.md`](grocery-mvp-checkpoint.md)
- **Proof store**: [`log.md`](../log.md)
- **Publication**: unpublished. Graphify refresh is pending. No deployment proof.

This page is the current product record. It records verified facts only.

## Active product

The local stack is React and TypeScript chat, FastAPI, PostgreSQL, a worker, and Floci. Floci supplies local SQS jobs and S3 evaluation export paths. Real Bedrock is the approved model path through `LLMProvider`. Plaid Sandbox adapters exist. Live Sandbox proof is blocked by absent credentials. Instacart stays parked under [decision 0010](../decisions/0010-usda-spoonacular-overlay.md). Older health-prediction and activity-planning text remains historical.

The catalog supports ten meals: chicken tacos, bean tacos, vegetable pasta, chicken-and-rice bowls, lentil soup, chickpea curry, vegetable stir-fry, baked potatoes with beans, breakfast burritos, and overnight oats. A request uses one to three (1-3) meals. Each meal uses one to eight (1-8) servings.

Every estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Sample catalog prices are not verified retailer prices. Missing prices produce an incomplete estimate.

## Verified local facts

Nutrition UI shows quantity-scaled USDA totals. Per-serving, per-meal, and selected-plan totals count pantry ingredients. Nutrition does not change `accepted` or `total_cents`.

Spoonacular cost is a request-only overlay. The path is no-store. Durable vendor price cache is removed. Migration `0008` is the current schema step for that removal.

Plaid Item list, client, polling, refresh UI, and refresh state exist. Live Plaid Sandbox remains blocked because credentials are absent.

Instacart development shopping-list proof stays parked per [decision 0010](../decisions/0010-usda-spoonacular-overlay.md). The adapter remains for a later handoff. Public chat answer facts render from the validated plan and allowlisted conflicts. They MUST NOT use untrusted raw LLM prices.

The current stack is local and unpublished. Publication and Graphify refresh remain pending.

## Integration evidence

Latest combined local gate at branch 58:

- PostgreSQL-enabled tests: 2,126, including opt-in P05
- Ruff and format: 250 files
- Strict mypy: 126 source files
- Frontend tests: 413 with a production build
- Six browser journeys
- Supervisor tests: 52
- Helper tests: 10
- CDK tests: 14

Frontend, browser, supervisor, helper, and CDK counts stay unchanged from the latest recorded values.
Dated verification for the earlier P05 opt-in 1,984-test gate is in [`log.md`](../log.md)
under `2026-09-22 — P05 local end-to-end evidence`.

Earlier checkpoint on branch `codex/app-completion-48` passed 1,963 PostgreSQL-enabled tests. Ruff, format, and strict mypy passed on 122 files. Frontend tests passed at 413 with a production build. Six browser journeys exist. Supervisor tests passed at 52. Helper tests passed at 10. Infrastructure rerun was pending after a local jsii cache permission error.

Earlier checkpoint through `app-completion46` passed 1,924 PostgreSQL-enabled tests. Ruff, format, and strict mypy passed on 120 files. Frontend tests passed at 413 with a production build. Six mocked browser journeys exist. Actual local browser and Bedrock follow-ups were also observed. See [`log.md`](../log.md).

These counts are local. They are not CI proof. They are not deployment proof.

## Evaluation evidence — keep runs separate

Do not combine mixed live batches with the later fixture-only batch.

Old live mixed batch at revision `f6f633539afec4e38b77c00e830ca0ad9f76b3ca`:

- 90 slots
- 45 fixture pass
- 24 real completed
- 21 unassessed

Final-plan replay on that mixed run:

- 12 pass
- 3 fail (A01 omitted request cap)
- 9 clarification unassessed

A01 is a strict-argument mismatch. The server retained a 1-cent budget. The path does not bypass the user cap.

Later fixture-only batch:

- 51 pass
- 39 unassessed
- Includes P01, P02, P03, and P04 controlled paths
- P02 batch routing is complete on this fixture CLI

New mixed live batch at revision `18bb537cf655a6dd3a15aea522a034ff3cc2e3a9`:

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
P05 evaluator batch routing remains pending.

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

Overall model quality is UNASSESSED.
The report CLI exists and MUST NOT overwrite output.
The CLI accepts only `metrics_status` `unassessed`.
The CLI MUST NOT certify global quality.
Explicit `--rates` is integrated at primary branch 57, source `21c7f3d`.
The CLI reads explicit dated rates.
It requires the recorded model and region.
It MUST NOT default, fetch, or guess rates.
A model or region mismatch fails.
The current mixed-batch report estimates USD 0.13718265.
That figure is not billing.
The old 24-observation estimate USD 0.13163909 stays separate.
P05 opt-in isolated stack proof is complete.
P05 evaluator routing remains pending.
This page MUST NOT claim global quality.

## Latency and estimated cost — old 24 live observations

Latency uses 24 observations. Values are nearest-rank on summed user-turn durations.

- p50: 6.242796125s
- p95: 13.702598918s

Tokens: 166,198 in, 27,925 out.

Dated estimated text-token cost is $0.13163909. This figure is not a bill. It uses the checked-in pricing JSON at [`nova2-lite-use1-20260922.json`](../../backend/tests/evaluation/pricing/nova2-lite-use1-20260922.json) and the cost module [`evaluation_cost.py`](../../backend/app/evaluation_cost.py).

## Evidence classes

| Class | What it may prove | Current status |
| --- | --- | --- |
| Deterministic | Catalog facts, planner arithmetic, nutrition scaling, UI transport | Local tests and mocked journeys |
| Fixture | Demo spending and sample catalog prices | Current budget-acceptance truth |
| Emulator | Floci SQS jobs and Floci S3 export paths | Used on the local job path |
| Sandbox | Plaid Sandbox posted and pending grocery spend | UI exists. Live Sandbox blocked by absent credentials |
| Live | Real Bedrock and request-only Spoonacular overlay | Bedrock follow-ups observed. Instacart parked |
| Deployed | Public hosting and production AWS | Not claimed |

P05 isolated proof uses local PostgreSQL, worker, Floci SQS, and Floci S3.
It is not deployed AWS.
It is not live Instacart.

Fixture data is not a verified retailer or bank claim.

## Open work

1. Add clarification scoring and public-claims scoring.
2. Add the reference comparison driver. That work remains pending until the coordinator verifies. `observe_reference_case` already supports F01, F02, F05, X04, and A01.
3. Finish P05 evaluator batch routing. Isolated opt-in test proof is complete.
4. Finish A02, A03, and A04 controlled fixtures.
5. Collect Plaid Sandbox proof after credentials exist outside source.
6. Keep Instacart parked until a later decision reopens it.
7. Stop new implementation when weekly usage remaining reaches 8%. Then finalize the wiki and Graphify. Then push reviewed feature branches and open capped PRs. Agents MUST NOT merge or push `main`.
8. Refresh Graphify before final publication. The user requires this order.

Handoff browser contract and client exist. Live Instacart write and button proof remain unfinished. Feature work follows [`plans/APP_COMPLETION_BACKLOG.md`](../../plans/APP_COMPLETION_BACKLOG.md).
