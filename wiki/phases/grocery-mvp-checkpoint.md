# Grocery MVP checkpoint for professor feedback

## Current status — 2026-09-12

- **Status**: Local grocery planner with stored USDA macros, unattended Bedrock chat, and an optional request-local Spoonacular overlay. This is not a completed AI product.
- **Accepted brief**: [`.codex/project-context.md`](../../.codex/project-context.md)
- **Decisions**: [0008 — Grocery bot with local Floci services](../decisions/0008-grocery-bot-pivot.md), [0010 — Park Instacart. Use USDA nutrition and Spoonacular cost](../decisions/0010-usda-spoonacular-overlay.md)
- **Overlay runbook**: [docs/SUPERMARKET_ESTIMATES.md](../../docs/SUPERMARKET_ESTIMATES.md)
- **Local proof store**: [log.md](../log.md)
- **Published foundation**: pull request [42](https://github.com/emanuelGitCodes/fewia/pull/42) merged on 2026-09-07 at `5bcf21b31523f7c2e1b22bb1aa069b9bb8a08c14`. That merge is historical.
- **Current local source**: `39840b6`. Independent Grok final range review approved 8/10.
- **Saved local `main` snapshot**: `0c6d571`, merge of the USDA per-100 g nutrition overlay (pull request 68). The coordinator verified that SHA from local `git log main`. Remote `HEAD` was not queried. This page MUST NOT claim current GitHub `main`.
- **Graph and wiki prerequisite**: `e045a9d`. Prebuild graph had 4190 nodes, 12131 edges, and 169 communities. Do not treat that graph as current after later code changes.
- **Prior current-build source base**: `c0357d6` on `codex/project-context-refresh`. Application code is committed locally. No Git push. No pull request. No merge.

Spoonacular retention, request-local overlay, P03 evaluation, and optional runtime binding are recorded.
Remaining evaluation slots stay unfinished.

The 2026-09-08 MFA checkpoint called continuity unfinished, handoff UI unfinished, features paused, and Instacart release proof required.
Those claims are historical. They are not current status.

### Active product

The active product is a budget-aware grocery planner on a local stack.
The stack is React and TypeScript, FastAPI, PostgreSQL, a worker, and Floci.
Floci supplies local SQS jobs and S3 evaluation export paths.
Real Bedrock is the approved model path through `LLMProvider`.
Plaid Sandbox adapters measure posted grocery spending. Pending spending stays separate.
Instacart development shopping-list links stay in the parked adapter.
They do not prove live prices. IDP is closed to new applicants.
Older health-prediction and activity-planning text remains historical.
Those phases are not the active build.

The catalog supports ten meals: chicken tacos, bean tacos, vegetable pasta, chicken-and-rice bowls, lentil soup, chickpea curry, vegetable stir-fry, baked potatoes with beans, breakfast burritos, and overnight oats.
A request uses one to three (1-3) meals.
Each meal uses one to eight (1-8) servings.

Every estimate shows this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Budget acceptance uses sample-catalog integer cents.
Spoonacular average cost MAY appear as a labeled current-view overlay.
It MUST NOT change `accepted` or `total_cents`.
It is not a live store price.
Job results MUST NOT keep a root `supermarket_estimate`.

### What is complete locally

Local macros compute calories, protein, carbs, and fat per serving and per plan.
There are no micronutrients.
All 22 USDA ingredient mappings match the public source in `docs/nutrition-sources.md`.
Pantry items count in nutrition.
Quantities are consumed recipe amounts, not packages.
USDA facts stay stored separately.
Manual and chat jobs return root nutrition JSON after evidence.
Frontend 5174 displays those macros.
Older 5173 remains a separate instance.

Chat and form continuity is complete locally.
Handoff controls are complete locally.
Instacart stays unavailable.
`instacart_configured` stays false.

Amazon Nova 2 Lite, reasoning effort `low`, planned chat on updated 5174.
Olive oil stayed in the pantry. Servings were 4.
Sample catalog total is 1233 cents. Plan energy is 1515 kcal.
Those figures are demo catalog and USDA values. They are not Spoonacular prices.
Runtime uses dedicated IAM user `fewia-bedrock-runtime` from CDK.
Credentials live outside Git with file mode `600`.
Runtime does not use human MFA.
The human MFA role is unchanged.
Created IAM user, deployment role, and CloudFormation stacks carry seven tags.
Billing has six Active `iamPrincipal` dimensions.
Filter `iamPrincipal/Project=FEWIA`.
`CostCenter` waits for registration.
Charges are not verified.
Do not print account ids or access keys.
USDA stored facts need no runtime API key.
Plaid Sandbox is not live-verified.
Optional `--spoonacular-key-file` mounts the key read-only on `api` only.
The worker has no Spoonacular key. AWS mounts stay.
The first live overlay check failed on a unit mismatch.
A later 5174 lookup succeeded after the locale and unit fix.
HTTP 200, numeric estimate available, `Cache-Control: no-store`.
Budget cents stayed. USDA macros stayed. The overlay cleared after a plan edit.
The database has 0 root price fields.
This page MUST NOT record an actual Spoonacular price.

### Evidence counts

These counts come from different environments. They are not a contradiction.

| Environment | Recorded result |
| --- | --- |
| Final range backend | 1577 passed |
| Final range infra | 31 passed |
| Final range frontend | 346 passed, build passed |
| Final range lint | ruff, format, and `app` mypy passed |
| Browser | Desktop 1280x900 and mobile 375x812, no overflow |
| Evaluation runner | 90 slots, 45 scored, 45 unassessed |
| Independent Grok reviews | Retention `b1f089b` 8/10. P03 `fe58d22` 8/10. Security `b867856` 8/10. Final range 8/10 |

No 90-run model-quality evaluation exists.
Earlier slice counts stay in [log.md](../log.md).
They are not a contradiction.

### Evidence classes

| Class | What it may prove | Current grocery status |
| --- | --- | --- |
| Deterministic | Catalog facts, planner arithmetic, budget cents, stored USDA macros, stripped job results | Local proof is in [log.md](../log.md) |
| Fixture | Demo spending, sample catalog prices, fictional overlay test values | Current demo spending source |
| Emulator | Floci SQS jobs and Floci S3 export paths | Used on the local job path |
| Sandbox | Plaid Sandbox posted and pending grocery spend | Adapters exist. Live Sandbox proof is pending |
| Live | Real Bedrock on local Compose. Optional Spoonacular overlay | Nova 2 Lite `low` planned chat on updated 5174. Overlay succeeded after a unit mismatch. No stored price |
| Deployed | IAM user, deployment role, and CloudFormation stacks | Verified in `infra/bedrock/UNATTENDED.md`. No public hosting. Charges not verified |

Fixture data is not a verified retailer or bank claim.
Sample catalog prices are not verified retailer prices.
Stored USDA facts are not medical advice.

### Remaining work

Remaining unassessed evaluation slots include F01, F02, F04, F05, X02, X03, X04, P01, P02, P04, P05, and A01 through A04.
`metrics_status` stays unassessed.
This page MUST NOT claim full evaluation coverage.
This page MUST NOT claim LLM quality or a live provider result from P03.

Plaid Sandbox live proof remains pending.
Instacart stays parked.
Cost Explorer charges are not verified.
No 90-run model-quality evaluation exists.

Graph artifacts are local and ignored; verify manifest/source hashes before use.
The coordinator rebuilds the graph after this documentation pass.
This page MUST NOT claim a completed graph.

### Current demo outline

1. Open the local 5174 preview.
2. Keep olive oil in the pantry.
3. Set four servings. Keep fixture spending.
4. Submit on the unattended Bedrock path. Wait for the queued job.
5. Read the itemized sample estimate of 1,233 cents.
6. Read the catalog notice on the estimate.
7. Read plan energy of 1515 kcal. Those values are demo catalog and USDA facts.
8. Use the explicit `Check supermarket estimate` button if the overlay is configured.
9. State that the overlay is current-view only. A plan edit clears it.
10. State that sample prices and fixture spending remain.
11. State that Instacart is parked and unavailable.
12. State that Plaid Sandbox adapters exist. The demo still uses fixture spending.
13. State that the evaluation runner has 90 slots, 45 scored, and 45 unassessed.

### Honest limitations

This checkpoint is an early MVP for professor feedback.
The product does not complete the original health-prediction experiment.
The product does not complete every grocery feature in the accepted brief.
Live chat is verified with Amazon Nova 2 Lite, reasoning effort `low`.
Sample prices remain. Fixture spending remains.
The demo does not use a real bank.
Instacart prices are not verified.
The first live overlay check failed on a unit mismatch, then succeeded.
This page MUST NOT record an actual Spoonacular price.
No 90-run evaluation exists.
No model-quality result exists.
This page MUST NOT claim a completed AI product.
This page MUST NOT claim real Plaid or Instacart proof.
This page MUST NOT claim a 90-run evaluation.

## Preserved historical record — 2026-09-08 checkpoint

The next sections keep the 2026-09-08 MFA checkpoint.
They are history.
They are not current status.

- **Date**: 2026-09-08
- **Status**: live chat VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. Feature work is PAUSED as the user requested. This is not a completed AI product.
- **Accepted brief**: [`.codex/project-context.md`](../../.codex/project-context.md)
- **Decision**: [0008 — Grocery bot with local Floci services](../decisions/0008-grocery-bot-pivot.md)
- **Local proof store**: [log.md](../log.md)
- **Published foundation**: merged into `main` on 2026-09-07. The live Nova 2 changes remain local.
- **Pull request**: [Consolidate grocery MVP and provider foundations](https://github.com/emanuelGitCodes/fewia/pull/42)
- **Merge commit**: `5bcf21b31523f7c2e1b22bb1aa069b9bb8a08c14`
- **GitHub checks**: Backend checks passed. Frontend checks passed.
- **Local branch**: `codex/bedrock-development-role`. Not pushed. Not merged.

This page preserves the current grocery demo. It does not expand features.

### Historical active product

The active product is a budget-aware grocery planner on a local stack. The stack is React and TypeScript, FastAPI, PostgreSQL, a worker, and Floci. Floci supplies local SQS jobs and S3 evaluation export paths. Real Bedrock is the approved model path through `LLMProvider`. Plaid Sandbox adapters measure posted grocery spending. Pending spending stays separate. Instacart development shopping-list links prove handoff. They do not prove live prices. Older health-prediction and activity-planning text remains historical. Those phases are not the active build.

### Historical working local path

The proven demo path is meal controls → API → PostgreSQL outbox → Floci SQS → worker → itemized estimate. The user selects meals and servings in the form. The API accepts the request. PostgreSQL stores the job and outbox row. Floci SQS carries the job id. The worker computes a labeled sample estimate. The UI shows the itemized result. Pantry removal is explicit. A rebuild follows a pantry change. The local page also mounts meal chat beside the manual planner.

Local fixture proof from [log.md](../log.md): bean tacos for two cost 1,703 cents. Olive oil in the pantry reduces that plan to 1,104 cents. A later browser check on `codex/visible-meal-chat` repeated the bean-tacos estimate at 1,703 cents.

Published consolidation checks remain those recorded for pull request 42. PostgreSQL-enabled backend tests passed at 1,374. Frontend tests passed at 238. Ruff, format, and strict mypy passed on 85 files. The frontend build passed. Fresh database migrations applied through 0007. One existing Starlette deprecation warning remains. GitHub Backend checks passed. GitHub Frontend checks passed. Preserved drafts are included and locally checked.

Current live-chat checks from [log.md](../log.md) differ. Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. Two-servings bean tacos returned USD 17.03. A four-servings follow-up returned USD 18.32. The budget 40 stayed preserved. The form updated to 4. The browser showed no errors. Sample prices remain. Fixture spending remains. Backend pytest reported 1,383 passed and eight database tests skipped. Ruff, format, and strict mypy passed. CDK 14 tests passed. Helper 10 tests passed. Local commits are `282f682` (model) and `06d41f3` (currency). No push or merge occurred.

### Historical catalog and estimates

The catalog supports ten meals: chicken tacos, bean tacos, vegetable pasta, chicken-and-rice bowls, lentil soup, chickpea curry, vegetable stir-fry, baked potatoes with beans, breakfast burritos, and overnight oats. A request uses one to three (1-3) meals. Each meal uses one to eight (1-8) servings. Sample package prices live in `backend/app/domain/catalog.py`. Ingredient quantities live in `backend/app/domain/catalog_recipes.json`.

The current deterministic planner rejects unsupported recipe IDs. It does not invent a substitute meal. Conversational alternatives are intended chat behavior. They are not current planner output.

Every estimate shows this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Missing prices produce an incomplete estimate. Incomplete estimates stay visible. Sample prices are not verified retailer prices.

### Historical budget

The user sets the monthly grocery limit. The planner does not recommend an allowance from income or bills. Posted grocery spending is subtracted from that limit. The remainder clamps to zero. Pending spending is shown separately. Plans do not reserve money. An explicit plan cap MAY lower the remaining budget. It MUST NOT raise the user cap. Budget math uses USD, integer cents, and America/New_York month dates. Shared ingredients aggregate before package rounding. The planner does not lower servings or omit ingredients to claim budget compliance.

The current demo uses fixture spending. No real bank account is validated. Plaid Sandbox adapters exist. Live Sandbox evidence remains pending.

### Historical chat, form, and handoff

The local `App` mounts `ChatWorkspace` and `ChatPanel` beside the manual planner. The page uses the existing provider capability hook and chat controller. A valid chat result updates the shared form and estimate. The budget cap stays preserved. Stale-result protection applies.

Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. A two-servings bean-tacos request produced a live reply and estimate of USD 17.03. A four-servings follow-up produced USD 18.32. The budget 40 stayed preserved. The form updated to 4. The browser showed no errors. The first live display used the wrong currency. A later fix used server USD display. Stored plan and evidence were not changed. Full context transfer from the manual planner to chat remains unfinished.

This page MUST NOT claim a completed AI product. This page MUST NOT claim real Plaid or Instacart proof. This page MUST NOT claim a 90-run evaluation. Feature work is PAUSED as the user requested.

The handoff browser contract and client exist. The button flow remains unfinished. Instacart code creates development shopping-list links. It does not verify live prices, availability, taxes, fees, or tips. An uncertain Instacart write needs a visible retry, not blind replay. Handoff URLs need validation before navigation.

### Historical evaluation

A 30-scenario corpus exists. A budget evaluation driver exists. The intended design is 30 scenarios repeated three times. No 90-run evaluation has run. No model-quality score exists.

### Historical evidence classes

| Class | What it may prove | Current grocery status |
| --- | --- | --- |
| Deterministic | Catalog facts, planner arithmetic, budget cents | Local proof is in [log.md](../log.md) |
| Fixture | Demo spending and sample catalog prices | Current demo spending source |
| Emulator | Floci SQS jobs and Floci S3 export paths | Used on the local job path |
| Sandbox | Plaid Sandbox posted and pending grocery spend | Adapters exist. Live Sandbox proof is pending |
| Live | Real Bedrock, live Plaid Sandbox, Instacart development links | Bedrock chat VERIFIED with Nova 2 Lite `low`. Plaid and Instacart remain pending |
| Deployed | Public hosting and production AWS | Not claimed |

Fixture data is not a verified retailer or bank claim.

### Historical professor demo outline

1. Open the local web form.
2. Select bean tacos with two servings.
3. Set a user monthly limit. Keep fixture spending.
4. Submit the form. Wait for the queued job.
5. Read the itemized sample estimate of 1,703 cents.
6. Read the catalog notice on the estimate.
7. Mark olive oil as pantry stock. Rebuild the plan.
8. Read the reduced sample estimate of 1,104 cents.
9. Show Meal chat beside the manual planner.
10. Send bean tacos for two. Read the live reply and USD 17.03 estimate.
11. Follow up with four servings. Read USD 18.32. Confirm budget 40 and form 4.
12. State that sample prices and fixture spending remain.
13. State that Instacart links are development handoff, not live prices.
14. State that Plaid Sandbox adapters exist. The demo still uses fixture spending.
15. State that the 30-scenario corpus exists. No 90-run result exists.
16. State that full manual-to-chat transfer remains unfinished.
17. State that feature work is PAUSED as the user requested.

### Historical honest limitations

This checkpoint is an early MVP for professor feedback. The product does not complete the original health-prediction experiment. The product does not complete every grocery feature in the accepted brief. Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. Sample prices remain. Fixture spending remains. The demo does not use a real bank. Instacart prices are not verified. No 90-run evaluation exists. No model-quality result exists. Full manual-plan context transfer is unfinished. Handoff button flow is incomplete. Feature work is PAUSED as the user requested. Pull request 42 merged into `main`. Graphify ran after that merge in the saved checkout. That record covers the prior merged checkpoint. A local chat graph refresh is not yet recorded.

### Historical next work after professor feedback

1. Renew the one-hour MFA session before the next live test.
2. Finish full manual-plan context transfer.
3. Keep feature work paused until the user requests it.
4. Keep the user cap, or apply a lower explicit cap.
5. Transfer a saved plan safely.
6. Wire explicit handoff retries.
7. Finish the evaluation runner.
8. Run real-provider checks when those providers are configured.

### Historical data sources after IDP closure

Instacart Developer Platform is closed to new applicants. The hybrid path
is [0010](../decisions/0010-usda-spoonacular-overlay.md). Park Instacart.
Store USDA nutrition. Show Spoonacular average cost as a labeled overlay.
Budget cents stay on the sample catalog.

### Historical wishlist

Weekly nutrition totals from consumed quantities, with pantry stock still
counted, remain optional. A future cash-flow grocery allowance from income
and bills remains optional. Per-recipe nutrition is now in decision 0010.

### Historical publication handoff

The user authorized commit, push, one large consolidation pull request, and merge. [Consolidate grocery MVP and provider foundations](https://github.com/emanuelGitCodes/fewia/pull/42) merged into `main` at `5bcf21b31523f7c2e1b22bb1aa069b9bb8a08c14` on 2026-09-07. GitHub Backend checks passed. GitHub Frontend checks passed. That consolidation MAY exceed the 150-line source cap once. Later pull requests keep the 150-line source cap.

Graphify rebuilt after the merge in the saved checkout. That record covers the prior merged checkpoint. It does not cover local visible-chat work on `codex/visible-meal-chat`. The local ignored artifacts are `graphify-out/graph.html`, `graph.json`, `GRAPH_REPORT.md`, and `health.json`. Full source coverage is 237 code files, 44 documents, and 1 image. Raw extraction excludes 979 unresolved endpoint references, mostly external imports. The default undirected graph collapses 919 repeated endpoint relationships. The extract also records 121 exact duplicate raw edges. These counts are analysis coverage limits. They are not application failures. Semantic agent token usage is unavailable. This page does not claim the graph has no errors. A local chat graph refresh is not yet recorded.
