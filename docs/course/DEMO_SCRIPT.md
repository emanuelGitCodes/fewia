# Operator shot list

The author records and submits the video. This script claims no recorded or hosted demonstration.
The [course transcript](../CAP6938%20August%2025.txt), lines 80-110, asks for code and a video of the agent.
Use the GUI and explain the states that actually appear.

## Before recording

Use an owner-prepared, isolated local runtime from [Compose](../../compose.yaml).
The runtime contains React and TypeScript, FastAPI, PostgreSQL, workers, and Floci SQS/S3.
The default web address is `http://127.0.0.1:5173`; the owner identifies any local port override.
The operator MUST NOT modify or run shared services for this shot list.
This document supplies no startup command or API payload.

Live Bedrock chat requires a configured local runtime and owner-authorized provider use.
The [provider backlog record](../FEATURE_BACKLOG.md) names `FEWIA_BEDROCK_MODEL_ID` as the Bedrock activation setting.
The [agent handler](../../backend/app/services/agent_jobs.py) reports an unavailable model when no provider exists.
The writer does not configure credentials, spend AWS funds, or make provider calls.
The operator MUST keep credentials and raw bank data out of the recording.
Do not create a public URL or describe private-hosting source design as a deployed demo.

Use manual spending, a $100 monthly limit, and a $40 plan cap as demonstration inputs.
These values are user choices. They are not measured savings or verified retailer prices.
The catalog supports 40 meals, 1-3 meals per request, and 1-8 servings per meal.
Every displayed grocery estimate MUST retain this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Main shots

Expected states below are observation targets, not a claim that this script has been executed.
Record failures as failures. Do not replace a live failure with fixture output under a live label.

| Shot | GUI action | Observable state and explanation |
|---|---|---|
| 1. Scope | Show the local page and repository. | The header says `Local demo · Sample prices`. Explain the manual budget and bounded catalog. Source: [App](../../frontend/src/App.tsx). |
| 2. Budget | Enter 100 in Monthly limit and 40 in Plan cap. Select bean tacos, two servings, with an empty pantry. | Show the `manual` source, both budget controls, and the selected meal. These inputs demonstrate a cap below the monthly limit. |
| 3. Deterministic plan | Select `Build my estimate`. Wait for the request to finish. | Capture the pending state and final estimate panel. Show ingredient quantities, the sample total, and the full notice. Record the actual result; promise no fixed total. Source: [plan job](../../backend/app/services/plan_job.py). |
| 4. Chat plan | In a configured chat workspace, send `Plan 2 servings of bean tacos.` | Capture the request and reply. Inspect the resulting estimate for the recipe, servings, preserved cap, and notice. If chat is unavailable, show that state and label this shot incomplete. |
| 5. Follow-up | In the same conversation, send `I have black beans`. | Look for a new plan with black beans marked as pantry-owned. Show whether purchase costs change while the recipe and servings stay fixed. The message sequence comes from F01 in the [archived scenarios](../../eval/results/artifacts/benchmark-20261003/scenarios.json). The $40 cap belongs to this demo, not the archived F01 input. |
| 6. Honest readout | Open the supplied [figure](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.png) and [readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json). | Explain 17/33 original, 23/33 post-hoc, and 0/33 no-tool task passes. Both tool-enabled scores fail the 90% target. Explain 98 supported plus two unknown public claims, with ten refusals excluded. |
| 7. One observed failure | Open [failure examples](../../eval/results/artifacts/course-evidence-20261003/failure-examples.json), `$.examples[0]`: F02, repeat 1, `tool_enabled`. | Show two planning turns followed by clarification without a final plan. Show `assessments.plan.checks.final_plan_present=false` and `assessments.tools.expected_tool_selection=0/1`. Explain that dependent false checks are not independent defects. This is an archived failure, not a new live reproduction. |
| 8. Limits and code | Show [limitations](LIMITATIONS.md) and the [chat loop](../../backend/app/agent/chat_loop.py). | Explain model interpretation versus tool arithmetic. Mention the shared demo user, unmeasured purchase attempts, and pending provider/deployment evidence. |

The [browser verification record](../GROCERY_VERIFICATION_PLAN.md) supports the local form, jobs, and polling path.
It explicitly reports unavailable chat in that browser stack. It does not prove the live chat shots above.
The owner records the runtime identity and the actual outcome for each new shot.

## Keep fixture handoff separate

If useful, show the archived consent and retry screenshots linked by the
[browser record](../GROCERY_VERIFICATION_PLAN.md).
Label this segment `fixture handoff; local application; no live Instacart request`.
Preserve the original missing-consent failure beside the repaired 14-check fixture pass.
Explain that the UI validates links and exposes an explicit retry after an uncertain write.
Do not replay an uncertain external action or open a shopping link for this evidence segment.
Development shopping links prove handoff only. They do not verify prices, stock, taxes, fees, tips, or purchases.
Plaid Sandbox evidence remains paused under D4; no real bank account belongs in the demo.

## Evidence labels for the recording

The archived benchmark observations use source `4b877d470258561cedd3375e38efc02362ce5f22`.
The post-hoc scorer and corrected gold use source `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6`.
The [provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json)
records six changed F04/F05 tools assessments with zero new inference calls.
The correction followed access to the outputs. It is not a fresh batch or an independent benchmark.
The operator MUST distinguish new local footage, archived live Bedrock evidence, and fixture handoff evidence.
Neither this script nor the archive establishes deployed hosting or release certification.
Recording, final editing, and course submission remain author work.
