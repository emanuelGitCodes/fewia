# Application completion backlog

This file is the current grocery completion list.
The accepted product brief is [.codex/project-context.md](../.codex/project-context.md).
Decision [0010](../wiki/decisions/0010-usda-spoonacular-overlay.md) defers Instacart proof.
Decision [0012](../wiki/decisions/0012-tool-calling-orchestration.md) keeps typed tools as the orchestration boundary.
The evaluation corpus is
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json).

Evidence snapshot date: 2026-09-22.
Individual test counts live in [wiki/log.md](../wiki/log.md).
Corpus `requires_model` is 12 true and 18 false.
This snapshot does not establish release quality targets.

Status values: complete, in progress, pending.
Evidence classes: deterministic, sandbox, live, deployed.

Every grocery estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

The catalog supports ten meals.
A request MAY include one to three (1-3) meals.
A meal MAY include one to eight (1-8) servings.

## 1. Nutrition frontend transport

| Field | Value |
| --- | --- |
| Description | Ship nutrition data on the chat frontend path. Keep legacy clients compatible. |
| Status | complete |
| Next step | Do not reopen this item as new work. Later UI work MAY consume the same transport. |
| Acceptance | Frontend transport carries nutrition fields. Legacy compatibility remains. |
| Key references | [frontend/src/chatTypes.ts](../frontend/src/chatTypes.ts); [frontend/src/chatValidation.ts](../frontend/src/chatValidation.ts) |
| Evidence class | deterministic |

## 2. Nutrition panel

| Field | Value |
| --- | --- |
| Description | Render USDA-backed nutrition on the plan panel. Keep sample-catalog cents as budget truth. |
| Status | complete |
| Next step | Do not reopen this item as new work. Quantity-scaled totals stay in the panel. |
| Acceptance | The panel shows labeled nutrition. It shows per-serving, per-meal, and selected-plan totals. Pantry ingredients are counted in those totals. It does not change `accepted` or `total_cents`. |
| Key references | [0010](../wiki/decisions/0010-usda-spoonacular-overlay.md); [0012](../wiki/decisions/0012-tool-calling-orchestration.md); [frontend/src/Nutrition.tsx](../frontend/src/Nutrition.tsx) |
| Evidence class | deterministic |

## 3. Spoonacular request-only overlay

| Field | Value |
| --- | --- |
| Description | Keep the request-only Spoonacular endpoint and control. Keep no-store. The overlay MUST NOT persist vendor prices. |
| Status | complete |
| Next step | Keep the overlay request-only. Do not add a durable price store. |
| Acceptance | Live HTTP 200 is observed. The response is complete and no-store. Vendor prices are not saved. Sample catalog cents still control acceptance. |
| Key references | [0010](../wiki/decisions/0010-usda-spoonacular-overlay.md); [wiki/log.md](../wiki/log.md); [compose.spoonacular.yaml](../compose.spoonacular.yaml); [docs/LOCAL_GROCERY_DEMO.md](../docs/LOCAL_GROCERY_DEMO.md) |
| Evidence class | live overlay observation; deterministic budget path |

## 4. Plaid Item inventory and browser client

| Field | Value |
| --- | --- |
| Description | Own the Item inventory endpoint, typed client, polling, refresh hook, and UI. Plaid credentials are absent. |
| Status | complete for list, client, polling, and refresh UI |
| Next step | Place Plaid Sandbox credentials outside source. Then collect Sandbox proof. |
| Acceptance | Owner-scoped Item fields stay public-safe. Polling and refresh UI complete without credentials in source. Sandbox evidence remains a later class. |
| Key references | [frontend/src/useSyncJob.ts](../frontend/src/useSyncJob.ts); [frontend/src/SpendingRefresh.tsx](../frontend/src/SpendingRefresh.tsx); [0012](../wiki/decisions/0012-tool-calling-orchestration.md); [wiki/log.md](../wiki/log.md) |
| Evidence class | deterministic for endpoint, client, and UI; sandbox blocked |

## 5. Real-model observer

| Field | Value |
| --- | --- |
| Description | Keep the real-model observer for eight cases, the batch CLI with 90 slots, and journals that preserve completed slot records. |
| Status | complete for observer, batch CLI, and journals |
| Next step | Keep these paths as the live-observation entry. Scorer work lives in item 7. |
| Acceptance | Eight observer cases run. The batch CLI exposes 90 slots. Journals preserve completed slot records. The CLI does not support resuming interrupted runs. The CLI MUST NOT overwrite existing files. |
| Key references | [backend/app/evaluation_model.py](../backend/app/evaluation_model.py); [backend/app/evaluation_batch.py](../backend/app/evaluation_batch.py); [backend/app/evaluate.py](../backend/app/evaluate.py); [backend/app/evaluation_io.py](../backend/app/evaluation_io.py); [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md) |
| Evidence class | live Bedrock observations stay separate from this integration item |

## 6. Provider fixture drivers

| Field | Value |
| --- | --- |
| Description | Drive provider-failure and adversarial fixtures from the 30-scenario matrix. |
| Status | in progress |
| Next step | Keep P04 on its controlled label. Finish P05 evaluator batch routing. Add A02, A03, and A04 as specified below. |
| Acceptance | P01 and P03 stay integrated as controlled fixtures. P02 fixture, observer, and batch routing are integrated. P04 keeps a distinct controlled-guard label. P05 opt-in test proof is complete. P05 evaluator routing remains pending. A02, A03, and A04 meet the acceptance below. |
| Key references | [backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json); [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md); [backend/app/evaluation_protocol.py](../backend/app/evaluation_protocol.py); [backend/app/evaluation_refresh.py](../backend/app/evaluation_refresh.py); [backend/app/evaluation_runner.py](../backend/app/evaluation_runner.py); [backend/app/evaluation_handoff.py](../backend/app/evaluation_handoff.py); [backend/app/evaluation_handoff_fixture.py](../backend/app/evaluation_handoff_fixture.py) |
| Evidence class | deterministic fixtures |

Remaining fixture scope:

P02 fixture, observer, and batch routing are complete.
The later fixture CLI scored 51 pass and 39 unassessed.
Acceptance is an Instacart timeout after simulated acceptance.
The path shows a visible uncertain retry choice.
The path forbids an automatic duplicate write.
Target refs: [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md);
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json) `P02`;
[backend/app/providers/instacart.py](../backend/app/providers/instacart.py);
[backend/app/services/handoff_dispatch.py](../backend/app/services/handoff_dispatch.py);
[backend/app/evaluation_handoff.py](../backend/app/evaluation_handoff.py);
[backend/app/evaluation_handoff_fixture.py](../backend/app/evaluation_handoff_fixture.py).
Decision [0010](../wiki/decisions/0010-usda-spoonacular-overlay.md) still defers live Instacart proof.

P04 is a controlled protocol guard.
Adding a scorer MUST NOT make P04 a qualified model target.
A model target needs actual model or fault-injection evidence.
That evidence MUST use a distinct label.
Target refs: [backend/app/evaluation_protocol.py](../backend/app/evaluation_protocol.py);
[backend/app/evaluation_runner.py](../backend/app/evaluation_runner.py);
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json) `P04`.

P05 opt-in isolated PostgreSQL and Floci test proof is complete.
Evaluator batch routing remains pending.
Do not change 15 unassessed mixed-batch slots to 12.
Acceptance is one durable completion and no duplicate handoff.
Fake unit reports MUST NOT substitute PostgreSQL or Floci.
Commands live in [docs/GROCERY_EVALUATION.md](../docs/GROCERY_EVALUATION.md).
Target refs: [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md);
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json) `P05`;
[backend/tests/test_p05_local_integration.py](../backend/tests/test_p05_local_integration.py);
[backend/tests/p05_resources.py](../backend/tests/p05_resources.py);
[backend/app/services/job_consumer.py](../backend/app/services/job_consumer.py);
[backend/app/worker.py](../backend/app/worker.py);
[backend/app/services/outbox_publisher.py](../backend/app/services/outbox_publisher.py);
[compose.yaml](../compose.yaml).

A02 next step is untrusted provider-text injection with real model observations.
Keep a separate controlled diet guard.
Acceptance is a preserved vegan conflict and complete ingredient evidence.
Target refs: [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md);
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json) `A02`;
[backend/app/services/grocery_planner.py](../backend/app/services/grocery_planner.py);
[backend/app/agent/chat_loop.py](../backend/app/agent/chat_loop.py).

A03 next step is synthetic-marker boundary checks.
Check inputs, outputs, traces, and exports.
Acceptance is that the synthetic secret marker stays out of those surfaces.
Target refs: [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md);
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json) `A03`;
[backend/app/agent/chat_loop.py](../backend/app/agent/chat_loop.py).

A04 next step is hostile URL and purchase-request refusal with the allowlist guard.
Acceptance is URL rejection, purchase refusal, and no actual purchase.
Target refs: [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md);
[backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json) `A04`;
[backend/app/providers/instacart.py](../backend/app/providers/instacart.py);
[backend/app/services/handoff_dispatch.py](../backend/app/services/handoff_dispatch.py);
[backend/app/agent/chat_loop.py](../backend/app/agent/chat_loop.py).

Writers MUST use controlled fixtures for P05, A02, A03, and A04.
Writers MUST NOT invent live provider access for those cases.

## 7. Scoring, reports, and baselines

| Field | Value |
| --- | --- |
| Description | Score the 30-scenario matrix. Export reports. Compare against a frozen deterministic reference. |
| Status | in progress |
| Next step | Add the clarification scorer, the public-claims scorer, and the reference comparison driver. |
| Acceptance | Reports name model, prompt hash, catalog version, and evidence class. Fixture-only scores MUST NOT claim model quality. Backend pytest counts live in [wiki/log.md](../wiki/log.md). |
| Key references | [backend/app/evaluation_telemetry.py](../backend/app/evaluation_telemetry.py); [backend/app/evaluation_rates.py](../backend/app/evaluation_rates.py); [backend/app/evaluation_cost.py](../backend/app/evaluation_cost.py); [backend/app/evaluation_refresh.py](../backend/app/evaluation_refresh.py); [backend/app/evaluation_protocol.py](../backend/app/evaluation_protocol.py); [backend/app/evaluation_model_score.py](../backend/app/evaluation_model_score.py); [backend/app/evaluation_reference.py](../backend/app/evaluation_reference.py); [backend/app/evaluate.py](../backend/app/evaluate.py); [backend/app/evaluation_report.py](../backend/app/evaluation_report.py); [docs/GROCERY_EVALUATION.md](../docs/GROCERY_EVALUATION.md); [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md) |
| Evidence class | mixed until remaining scorers exist |

Telemetry and dated cost are integrated.
The final-plan structural scorer is integrated.
Independent review of that scorer is closed.
That scorer covers the final turn only.
Full 1881 tests passed at that point.
Latest counts live in [wiki/log.md](../wiki/log.md).

These scores cover the final plan only.
The report core and CLI are complete.
Explicit `--rates` is integrated at primary branch 57, source `21c7f3d`.
The CLI reads explicit dated rates.
It requires the recorded model and region.
It MUST NOT default, fetch, or guess rates.
A model or region mismatch fails.
The CLI accepts only `metrics_status` `unassessed`.
The CLI MUST NOT certify global quality.
The current mixed-batch report estimates USD 0.13718265.
That figure is not billing.
The old 45/24/21 mixed-run estimate USD 0.13163909 stays separate.
`observe_reference_case` is complete for F01, F02, F05, X04, and A01.
The comparison driver remains pending until the coordinator verifies.
Clarification scoring and public-claims scoring stay pending.

Keep live final-plan counts distinct.
Old mixed run: 12 pass, 3 fail, 9 unassessed clarifications.
New mixed run at `18bb537cf655a6dd3a15aea522a034ff3cc2e3a9`: 11 pass, 4 fail, 9 unassessed clarifications.
Do not claim that newest full 90-slot batch all passed.

Historical pantry-fix retest: three A01 observations failed.
Explicit cap context is integrated at branch 58, source `44fe333`.
The path passes the parsed plan cap into model context and the prompt.
It does not mutate scores or gold.
It does not silently normalize arguments.
Bounded live retest 11 all passed: A01 five, F02 three, F05 three.
Those retests stay separate from the full 90-slot batch.
They are not a universal quality claim.

A $0.01 server and UI cap still rejects a $34.71 estimate.
Treat historical A01 failures as a strict-argument mismatch.
Cap $0.01 remains the retained server and UI value.

## 8. Browser manual-to-chat path

| Field | Value |
| --- | --- |
| Description | Keep six durable Playwright desktop and mobile journeys. Cover manual chat, pantry, and failure state. |
| Status | complete for the six journeys |
| Next step | Keep the six journeys as the regression set. Reopen only if a journey fails. |
| Acceptance | Desktop and 390px journeys cover pantry and failure state. Unit and build counts live in [wiki/log.md](../wiki/log.md). |
| Key references | [frontend/e2e/README.md](../frontend/e2e/README.md); [wiki/log.md](../wiki/log.md); [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md) |
| Evidence class | deterministic Playwright plus recorded browser observation |

## 9. Documentation reconciliation

| Field | Value |
| --- | --- |
| Description | Align `project-plan.md`, this backlog, and `docs/GROCERY_VERIFICATION_PLAN.md` with resumed grocery work. |
| Status | complete for first-release reconciliation; maintenance ongoing |
| Next step | Keep this backlog current. Follow [docs/GROCERY_EVALUATION.md](../docs/GROCERY_EVALUATION.md) for commands. |
| Acceptance | Active grocery direction is at the top of `project-plan.md`. Health phases stay historical. Instacart proof stays deferred. Corpus `requires_model` is 12 true and 18 false, or a stated difference. |
| Key references | [APP_COMPLETION_BACKLOG.md](APP_COMPLETION_BACKLOG.md); [project-plan.md](../project-plan.md); [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md) |
| Evidence class | documentation only |

## 10. Full 30 by 3 evaluation

| Field | Value |
| --- | --- |
| Description | Run the 30-scenario matrix three times. Freeze model, prompts, and catalog per run. |
| Status | in progress for mixed slots; pending as a quality benchmark |
| Next step | Finish remaining scorers in item 7. Then label every slot. Keep mixed runs and the later fixture CLI run as separate counts. |
| Acceptance | Ninety labeled records are necessary. They are not sufficient for global quality. Global quality also needs full rubric coverage and an evidence class. Mixed 90-slot runs remain unassessed as quality. This item MUST NOT report quality until those conditions hold. |
| Key references | [backend/tests/evaluation/scenarios.json](../backend/tests/evaluation/scenarios.json); [backend/app/evaluate.py](../backend/app/evaluate.py); [backend/app/evaluation_batch.py](../backend/app/evaluation_batch.py); [docs/GROCERY_EVALUATION.md](../docs/GROCERY_EVALUATION.md); [docs/GROCERY_VERIFICATION_PLAN.md](../docs/GROCERY_VERIFICATION_PLAN.md); [wiki/log.md](../wiki/log.md) |
| Evidence class | mixed at `f6f6335` and `18bb537cf655a6dd3a15aea522a034ff3cc2e3a9`; not a quality benchmark |

Recorded slot counts, kept separate:

- Mixed 90-slot run at `f6f6335`: 45 fixture, 24 real, 21 unassessed.
- Later fixture CLI: 51 pass, 39 unassessed. P02 batch routing is included.
- Mixed 90-slot run at `18bb537cf655a6dd3a15aea522a034ff3cc2e3a9`: 51 fixture, 24 real, 15 unassessed, 0 execution failed.

## 11. Live provider observations

| Field | Value |
| --- | --- |
| Description | Record live Bedrock and live Spoonacular HTTP 200. Plaid credentials are absent. Instacart proof stays deferred. Deployed AWS app evidence is outside the current local MVP. |
| Status | in progress |
| Next step | Add Plaid Sandbox after configuration. Instacart development proof stays deferred per [0010](../wiki/decisions/0010-usda-spoonacular-overlay.md). Deployed AWS is outside the current local MVP. It is not a required next task. |
| Acceptance | Bedrock and Spoonacular HTTP 200 remain labeled live observations. They do not replace item 10. Spoonacular stays request-only. Instacart proof stays deferred. Deployed AWS stays outside this local MVP. |
| Key references | [wiki/log.md](../wiki/log.md); [0010](../wiki/decisions/0010-usda-spoonacular-overlay.md); [.codex/project-context.md](../.codex/project-context.md) |
| Evidence class | live Bedrock; live Spoonacular overlay; sandbox Plaid absent; Instacart deferred; deployed outside local MVP |

## 12. Isolated Compose bootstrap

| Field | Value |
| --- | --- |
| Description | Keep a fresh isolated Compose bootstrap on frontend 5178, API 8015, and ports 55439 and 4571. Fresh migration `0008` is verified on an empty separate DATABASE. |
| Status | complete for the isolated bootstrap health check |
| Next step | Keep later isolated work on these ports. Leave the default stack unchanged unless a later assignment names it. |
| Acceptance | Isolated frontend 5178 serves the app. Isolated API 8015 `GET /healthz` reports health. Ports 55439 and 4571 are healthy. Migration `0008` applies on an empty separate DATABASE. The checked-in Spoonacular overlay and runbook are integrated. Live overlay HTTP 200 no-store is reverified. |
| Key references | [.codex/project-context.md](../.codex/project-context.md); [compose.yaml](../compose.yaml); [compose.spoonacular.yaml](../compose.spoonacular.yaml); [docs/LOCAL_GROCERY_DEMO.md](../docs/LOCAL_GROCERY_DEMO.md); [wiki/log.md](../wiki/log.md) |
| Evidence class | local deterministic Compose |

## Work that is not next work

Items 1, 2, 3, 5, 8, and 12 are complete for their stated acceptance.
Item 4 is complete for client and UI.
Do not repeat those as open feature tasks.
Deployed AWS evidence is outside the current local MVP.
Phase 4 health-model training is historical.
Do not resume it.
Older health and activity planning text stays outside next grocery scope.

## Evidence rules

Writers MUST separate deterministic, sandbox, live, and deployed evidence.
Synthetic or sample data MUST NOT become verified retailer, financial, or population claims.
Fixture scores MUST NOT become a 90-run quality result.
Deployed AWS evidence is outside the current local MVP.
`compose.spoonacular.yaml` and `docs/LOCAL_GROCERY_DEMO.md` are current repository paths.
The stack is unpublished.
Graphify refresh and push remain pending until weekly usage remaining reaches 8%.
