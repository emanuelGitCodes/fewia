# Grocery MVP checkpoint for professor feedback

- **Date**: 2026-09-07
- **Status**: local professor-feedback MVP. This is not a completed AI product.
- **Accepted brief**: [`.codex/project-context.md`](../../.codex/project-context.md)
- **Decision**: [0008 — Grocery bot with local Floci services](../decisions/0008-grocery-bot-pivot.md)
- **Local proof store**: [log.md](../log.md)
- **Publication**: pending. The coordinator has not recorded commit, push, merge, or Graphify refresh.

This page preserves the current grocery demo. It does not expand features.

## Active product

The active product is a budget-aware grocery planner on a local stack. The stack is React and TypeScript, FastAPI, PostgreSQL, a worker, and Floci. Floci supplies local SQS jobs and S3 evaluation export paths. Real Bedrock is the approved model path through `LLMProvider`. Plaid Sandbox adapters measure posted grocery spending. Pending spending stays separate. Instacart development shopping-list links prove handoff. They do not prove live prices. Older health-prediction and activity-planning text remains historical. Those phases are not the active build.

## Working local path

The proven demo path is meal controls → API → PostgreSQL outbox → Floci SQS → worker → itemized estimate. The user selects meals and servings in the form. The API accepts the request. PostgreSQL stores the job and outbox row. Floci SQS carries the job id. The worker computes a labeled sample estimate. The UI shows the itemized result. Pantry removal is explicit. A rebuild follows a pantry change.

Local fixture proof from [log.md](../log.md): bean tacos for two cost 1,703 cents. Olive oil in the pantry reduces that plan to 1,104 cents.

The coordinator verified these combined local checks. PostgreSQL-enabled backend tests passed at 1,374. Frontend tests passed at 238. Ruff, format, and strict mypy passed on 85 files. The frontend build passed. Fresh database migrations applied through 0007. One existing Starlette deprecation warning remains. These are local results. They are not CI, merge, or publication claims. Preserved drafts are included and locally checked.

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

Chat panel, controller, and API exist. They are not wired into `App`. Manual-to-chat handoff remains unfinished. Unsaved-form synchronization remains unfinished. The handoff browser contract and client exist. The button flow remains unfinished. Instacart code creates development shopping-list links. It does not verify live prices, availability, taxes, fees, or tips. An uncertain Instacart write needs a visible retry, not blind replay. Handoff URLs need validation before navigation.

## Evaluation

A 30-scenario corpus exists. A budget evaluation driver exists. The intended design is 30 scenarios repeated three times. No 90-run evaluation has run. No model-quality score exists.

## Evidence classes

| Class | What it may prove | Current grocery status |
| --- | --- | --- |
| Deterministic | Catalog facts, planner arithmetic, budget cents | Local proof is in [log.md](../log.md) |
| Fixture | Demo spending and sample catalog prices | Current demo spending source |
| Emulator | Floci SQS jobs and Floci S3 export paths | Used on the local job path |
| Sandbox | Plaid Sandbox posted and pending grocery spend | Adapters exist. Live Sandbox proof is pending |
| Live | Real Bedrock, live Plaid Sandbox, Instacart development links | Pending |
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
9. State that chat is implemented but not wired into `App`.
10. State that Instacart links are development handoff, not live prices.
11. State that Plaid Sandbox adapters exist. The demo still uses fixture spending.
12. State that the 30-scenario corpus exists. No 90-run result exists.
13. State that live Bedrock, Plaid Sandbox, and Instacart checks remain pending.
14. State that full browser-chat validation remains pending.

## Honest limitations

This checkpoint is an early MVP for professor feedback. The product does not complete the original health-prediction experiment. The product does not complete every grocery feature in the accepted brief. Chat is not a working in-app conversation. The demo does not use a real bank. The demo does not validate a live provider. Instacart prices are not verified. No 90-run evaluation exists. No model-quality result exists. Browser-chat validation is incomplete. Handoff button flow is incomplete. Publication evidence is pending. This page does not claim merge or Graphify refresh.

## Next work after professor feedback

1. Connect the shared form, chat, and estimate.
2. Keep the user cap, or apply a lower explicit cap.
3. Transfer a saved plan safely.
4. Wire explicit handoff retries.
5. Finish the evaluation runner.
6. Run real-provider checks when those providers are configured.

## Wishlist

These items are not required now: nutrition per recipe and per serving; weekly nutrition totals from consumed quantities, with pantry stock still counted; a future cash-flow grocery allowance from income and bills.

## Publication handoff

The user authorized commit, push, one large consolidation pull request, and merge. The user then authorized Graphify and a wiki refresh. That consolidation MAY exceed the 150-line source cap once. Later pull requests keep the 150-line source cap. The coordinator records publication evidence after those actions complete. Until that record exists, publication, CI, and Graphify stay pending.
