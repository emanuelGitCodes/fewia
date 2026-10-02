# Grocery MVP checkpoint for professor feedback

- **Date**: 2026-09-08
- **Status**: feature work resumed on 2026-09-27. Read "Current state" first. The sections after it record the 2026-09-08 checkpoint. This is not a completed AI product.
- **Accepted brief**: [`.codex/project-context.md`](../../.codex/project-context.md)
- **Decision**: [0008 — Grocery bot with local Floci services](../decisions/0008-grocery-bot-pivot.md)
- **Local proof store**: [log.md](../log.md)
- **Published foundation**: merged into `main` on 2026-09-07. The live Nova 2 changes remain local.
- **Pull request**: [Consolidate grocery MVP and provider foundations](https://github.com/emanuelGitCodes/fewia/pull/42)
- **Merge commit**: `5bcf21b31523f7c2e1b22bb1aa069b9bb8a08c14`
- **GitHub checks**: Backend checks passed. Frontend checks passed.
- **Local branch**: `codex/bedrock-development-role`. Not pushed. Not merged.

This page preserves the grocery demo for professor feedback. The first
section records the state on `main` on 2026-09-30.

## Current state

- **Chat transfer.** A saved manual plan feeds chat. Unsaved form edits
  need a rebuild first. This shipped on 2026-09-09.
- **Budget.** The default spending source is `manual`. The monthly limit
  that the user enters is the whole budget. `fixture` and `plaid_sandbox`
  stay valid settings. Plaid is paused until the end of the project.
- **Nutrition.** The estimate shows USDA FoodData Central nutrition for
  each meal and for the plan.
- **Supermarket prices.** The estimate shows a Spoonacular average for
  each purchased line and for the plan. The API computes it at read time
  and stores none. Budget acceptance still uses sample-catalog cents.
  Live prices show on the Compose stack since 2026-10-02.
  Decision [0016](../decisions/0016-spoonacular-read-time-overlay.md)
  records the rules.
- **Instacart.** The handoff is parked. Instacart Developer Platform does
  not accept new applicants. Decision
  [0010](../decisions/0010-usda-spoonacular-overlay.md) records this. The
  shopping button stays hidden.
- **Evaluation.** The runner scores the budget and meal groups, F03, and
  X01. The provider-failure group, the adversarial group, and the cases
  that need the model stay unassessed. No 90-run evaluation has run.

The demo outline below still uses fixture spending. With the `manual`
source, a $100 limit shows $100 available.

## Active product

The active product is a budget-aware grocery planner on a local stack. The stack is React and TypeScript, FastAPI, PostgreSQL, a worker, and Floci. Floci supplies local SQS jobs and S3 evaluation export paths. Real Bedrock is the approved model path through `LLMProvider`. Plaid Sandbox adapters measure posted grocery spending. Pending spending stays separate. Instacart development shopping-list links prove handoff. They do not prove live prices. Older health-prediction and activity-planning text remains historical. Those phases are not the active build.

## Working local path

The proven demo path is meal controls → API → PostgreSQL outbox → Floci SQS → worker → itemized estimate. The user selects meals and servings in the form. The API accepts the request. PostgreSQL stores the job and outbox row. Floci SQS carries the job id. The worker computes a labeled sample estimate. The UI shows the itemized result. Pantry removal is explicit. A rebuild follows a pantry change. The local page also mounts meal chat beside the manual planner.

Local fixture proof from [log.md](../log.md): bean tacos for two cost 1,703 cents. Olive oil in the pantry reduces that plan to 1,104 cents. A later browser check on `codex/visible-meal-chat` repeated the bean-tacos estimate at 1,703 cents.

Published consolidation checks remain those recorded for pull request 42. PostgreSQL-enabled backend tests passed at 1,374. Frontend tests passed at 238. Ruff, format, and strict mypy passed on 85 files. The frontend build passed. Fresh database migrations applied through 0007. One existing Starlette deprecation warning remains. GitHub Backend checks passed. GitHub Frontend checks passed. Preserved drafts are included and locally checked.

Current live-chat checks from [log.md](../log.md) differ. Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. Two-servings bean tacos returned USD 17.03. A four-servings follow-up returned USD 18.32. The budget 40 stayed preserved. The form updated to 4. The browser showed no errors. Sample prices remain. Fixture spending remains. Backend pytest reported 1,383 passed and eight database tests skipped. Ruff, format, and strict mypy passed. CDK 14 tests passed. Helper 10 tests passed. Local commits are `282f682` (model) and `06d41f3` (currency). No push or merge occurred.

## Catalog and estimates

The catalog supports ten meals: chicken tacos, bean tacos, vegetable pasta, chicken-and-rice bowls, lentil soup, chickpea curry, vegetable stir-fry, baked potatoes with beans, breakfast burritos, and overnight oats. A request uses one to three (1-3) meals. Each meal uses one to eight (1-8) servings. Sample package prices live in `backend/app/domain/catalog.py`. Ingredient quantities live in `backend/app/domain/catalog_recipes.json`.

The current deterministic planner rejects unsupported recipe IDs. It does not invent a substitute meal. Conversational alternatives are intended chat behavior. They are not current planner output.

Every estimate shows this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Missing prices produce an incomplete estimate. Incomplete estimates stay visible. Sample prices are not verified retailer prices.

## Budget

The user sets the monthly grocery limit. The planner does not recommend an allowance from income or bills. Posted grocery spending is subtracted from that limit. The remainder clamps to zero. Pending spending is shown separately. Plans do not reserve money. An explicit plan cap MAY lower the remaining budget. It MUST NOT raise the user cap. Budget math uses USD, integer cents, and America/New_York month dates. Shared ingredients aggregate before package rounding. The planner does not lower servings or omit ingredients to claim budget compliance.

The current demo uses fixture spending. No real bank account is validated. Plaid Sandbox adapters exist. Live Sandbox evidence remains pending.

## Chat, form, and handoff

The local `App` mounts `ChatWorkspace` and `ChatPanel` beside the manual planner. The page uses the existing provider capability hook and chat controller. A valid chat result updates the shared form and estimate. The budget cap stays preserved. Stale-result protection applies.

Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. A two-servings bean-tacos request produced a live reply and estimate of USD 17.03. A four-servings follow-up produced USD 18.32. The budget 40 stayed preserved. The form updated to 4. The browser showed no errors. The first live display used the wrong currency. A later fix used server USD display. Stored plan and evidence were not changed. On 2026-09-08, full context transfer from the manual planner to chat was unfinished. It shipped on 2026-09-09.

This page MUST NOT claim a completed AI product. This page MUST NOT claim real Plaid or Instacart proof. This page MUST NOT claim a 90-run evaluation. Feature work was PAUSED from 2026-09-08 to 2026-09-27.

The handoff browser contract and client exist. The button flow remains unfinished. Instacart code creates development shopping-list links. It does not verify live prices, availability, taxes, fees, or tips. An uncertain Instacart write needs a visible retry, not blind replay. Handoff URLs need validation before navigation.

## Evaluation

A 30-scenario corpus exists. A budget evaluation driver exists. The intended design is 30 scenarios repeated three times. No 90-run evaluation has run. No model-quality score exists.

## Evidence classes

| Class | What it may prove | Current grocery status |
| --- | --- | --- |
| Deterministic | Catalog facts, planner arithmetic, budget cents | Local proof is in [log.md](../log.md) |
| Fixture | Demo spending and sample catalog prices | Current demo spending source |
| Emulator | Floci SQS jobs and Floci S3 export paths | Used on the local job path |
| Sandbox | Plaid Sandbox posted and pending grocery spend | Adapters exist. Live Sandbox proof is pending |
| Live | Real Bedrock, live Plaid Sandbox, Instacart development links | Bedrock chat VERIFIED with Nova 2 Lite `low`. Plaid and Instacart remain pending |
| Deployed | Public hosting and production AWS | Not claimed |

Fixture data is not a verified retailer or bank claim.

## Professor demo outline

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
16. State that manual-to-chat transfer shipped on 2026-09-09.
17. State that the default budget is now the amount that the user enters.

## Honest limitations

This checkpoint is an early MVP for professor feedback. The product does not complete the original health-prediction experiment. The product does not complete every grocery feature in the accepted brief. Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`. Sample prices remain. Fixture spending remains. The demo does not use a real bank. Instacart prices are not verified. No 90-run evaluation exists. No model-quality result exists. On 2026-09-08, full manual-plan context transfer was unfinished. It shipped on 2026-09-09. Handoff button flow is incomplete. Instacart is parked. Pull request 42 merged into `main`. Graphify ran after that merge in the saved checkout. That record covers the prior merged checkpoint. A local chat graph refresh is not yet recorded.

## Next work after professor feedback

1. Renew the one-hour MFA session before the next live test.
2. Finish full manual-plan context transfer.
3. Keep feature work paused until the user requests it. Done: the user resumed feature work on 2026-09-27.
4. Keep the user cap, or apply a lower explicit cap.
5. Transfer a saved plan safely.
6. Wire explicit handoff retries.
7. Finish the evaluation runner.
8. Run real-provider checks when those providers are configured.

## Data sources after IDP closure

Instacart Developer Platform is closed to new applicants. The hybrid path
is [0010](../decisions/0010-usda-spoonacular-overlay.md). Park Instacart.
Store USDA nutrition. Show Spoonacular average cost as a labeled overlay.
Budget cents stay on the sample catalog.

## Wishlist

Weekly nutrition totals from consumed quantities, with pantry stock still
counted, remain optional. A future cash-flow grocery allowance from income
and bills remains optional. Per-recipe nutrition is now in decision 0010.

## Publication handoff

The user authorized commit, push, one large consolidation pull request, and merge. [Consolidate grocery MVP and provider foundations](https://github.com/emanuelGitCodes/fewia/pull/42) merged into `main` at `5bcf21b31523f7c2e1b22bb1aa069b9bb8a08c14` on 2026-09-07. GitHub Backend checks passed. GitHub Frontend checks passed. That consolidation MAY exceed the 150-line source cap once. Later pull requests keep the 150-line source cap.

Graphify rebuilt after the merge in the saved checkout. That record covers the prior merged checkpoint. It does not cover local visible-chat work on `codex/visible-meal-chat`. The local ignored artifacts are `graphify-out/graph.html`, `graph.json`, `GRAPH_REPORT.md`, and `health.json`. Full source coverage is 237 code files, 44 documents, and 1 image. Raw extraction excludes 979 unresolved endpoint references, mostly external imports. The default undirected graph collapses 919 repeated endpoint relationships. The extract also records 121 exact duplicate raw edges. These counts are analysis coverage limits. They are not application failures. Semantic agent token usage is unavailable. This page does not claim the graph has no errors. A local chat graph refresh is not yet recorded.
