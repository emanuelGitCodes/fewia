# Grocery completion record — 2026-09-22

- **Status**: local grocery completion in progress. This is not a completed product. This is not a deployed release.
- **Accepted brief**: [`.codex/project-context.md`](../../.codex/project-context.md)
- **Backlog**: [`plans/APP_COMPLETION_BACKLOG.md`](../../plans/APP_COMPLETION_BACKLOG.md)
- **Local demo runbook**: [`docs/LOCAL_GROCERY_DEMO.md`](../../docs/LOCAL_GROCERY_DEMO.md)
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

Latest combined local gate on branch `codex/app-completion-48`:

- The backend gate passed 1,963 PostgreSQL-enabled tests.
- Ruff passed.
- Format passed on 238 files.
- Strict mypy passed on 122 source files.
- Frontend tests passed at 413 with a production build.
- Operators reran six browser journeys.
- Supervisor tests passed at 52.
- Helper tests passed at 10.
- Infrastructure test rerun is pending after a local jsii cache permission error.
- This page MUST NOT claim that infrastructure rerun passed.

Earlier checkpoint through `app-completion46` passed 1,924 PostgreSQL-enabled tests. Ruff, format, and strict mypy passed on 120 files. Frontend tests passed at 413 with a production build. Six mocked browser journeys exist. Actual local browser and Bedrock follow-ups were also observed. See [`log.md`](../log.md).

These counts are local. They are not CI proof. They are not deployment proof.

## Evaluation evidence — keep runs separate

Do not combine the old live mixed batch with the later fixture-only batch.

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

Latest fixture-only batch:

- 51 pass
- 39 unassessed
- Includes P01, P02, P03, and P04 controlled paths

Overall model quality is UNASSESSED. Report export remains in progress. P05 live integration remains in progress. This page MUST NOT claim those items complete.

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

Fixture data is not a verified retailer or bank claim.

## Open work

1. Finish report exports and remaining scorers.
2. Finish P05 live integration on isolated PostgreSQL and Floci.
3. Collect Plaid Sandbox proof after credentials exist outside source.
4. Keep Instacart parked until a later decision reopens it.
5. Stop new implementation when weekly usage remaining reaches 8%. Then finalize the wiki and Graphify. Then push reviewed feature branches and open capped PRs. Agents MUST NOT merge or push `main`.
6. Refresh Graphify before final publication. The user requires this order.

Handoff browser contract and client exist. Live Instacart write and button proof remain unfinished. Feature work follows [`plans/APP_COMPLETION_BACKLOG.md`](../../plans/APP_COMPLETION_BACKLOG.md).
