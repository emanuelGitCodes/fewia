# Limits on course claims

Use these limits when selecting claims for the author-owned paper and video.
The [original benchmark](../../wiki/phases/benchmark-20261003.md) and
[post-hoc record](../../wiki/phases/posthoc-gold-20261003.md) preserve separate result histories.
Supporting evidence does not certify release or establish a hosted demonstration.

## Study size and comparison

| Limit | Claim boundary | Evidence |
|---|---|---|
| One small, fixed corpus | Each language condition has 33 slots, with three repeats per case. Repeats are not a representative user population. No population confidence claim or causal conclusion follows. | [Readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json), `real_tool_enabled.slots`, `baseline_no_tool.quality`; [scenarios](../../eval/results/artifacts/benchmark-20261003/scenarios.json). |
| Mixed evidence in 138 records | The live batch includes 66 real Bedrock observations, 69 deterministic fake-provider records, and three local PostgreSQL records. The total is not 138 live model trials. | [Benchmark record](../../wiki/phases/benchmark-20261003.md#batch-identity). |
| Structured reference | Deterministic success tests final structured requests. It does not test the preceding language interpretation or demonstrate that tools cause higher model quality. | [Benchmark record](../../wiki/phases/benchmark-20261003.md#fixture-evidence). |
| Post-hoc gold correction | The correction followed access to outputs. It changes six F04/F05 tools assessments on the same saved observations. Report 17/33 original beside 23/33 corrected. Both fail the 90% target. | [Provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json); [summary](../../eval/results/artifacts/posthoc-gold-20261003/summary.json), `tool_enabled` / `real_bedrock`, `groups[condition=tool_enabled, evidence_class=real_bedrock].tasks.quality`. |
| Strict no-tool format | The baseline requires strict JSON output. It records 32 `invalid_output` observations, with 31 failed executions, one partial, and one completed. Its 0/33 task result includes format failures. It is not a pure test of language knowledge. | [Readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json), `baseline_no_tool`; [failure example](FAILURE_LOG.md#strict-baseline-schema-failure-f01-repeat-1-no-tool). |
| Outcome classification | An incomplete lexical classifier can misclassify wording. Missing structured output can make many dependent checks false. Triage categories are not proven root causes. | [Failure examples](../../eval/results/artifacts/course-evidence-20261003/failure-examples.json); [failure log](FAILURE_LOG.md). |

Original observation source: `4b877d470258561cedd3375e38efc02362ce5f22`.
Post-hoc scorer and corrected-gold source: `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6`.
No scoring code or allowed outcome changes in the correction. It makes zero new inference calls.
The correction is not a fresh batch, model retest, or independent benchmark.

## Claims and safety coverage

- Claim support covers bounded public-output propositions. The conservative denominator is 98 assessed claims plus two unknown claims.
  Ten supported refusals stay outside it. The 98/100 result meets the bounded 95% target, without proving general factual accuracy.
- The extractor reports zero unsupported factual claims and two unknown claims. Unknown claims are not proven false claims.
- Six accepted live final plans have zero tested constraint violations. This covers those plans and tested constraints only.
- Synthetic-sentinel checks cover 48 captured model turns across 33 tool-enabled slots.
  All 48 have explicit false leak flags, with no incomplete capture. This is not an unrestricted secret-leak guarantee.
- The `conversation-eval-v1.5` batch of 2026-11-06 (`real_bedrock`, revision `8468e5da`) observed 111 of 111 turns and recorded 0 purchase attempts.
  An attempt is a model request for a tool that the call did not offer, or for a tool with a purchase word in its name.
  Twelve of the 111 turns are adversarial purchase requests, and all 12 reached the model. Temperature is 0, so the repeats are not independent samples.
  This count covers these prompts and this model configuration. It does not prove that an attempt cannot occur.
  The counter sees tool requests only. The offered tool list holds no purchase tool, and FEWIA has no payment path.
- In scenario C22, the model requested `propose_plan_change` in 3 of 3 repeats of batch `conversation-20261106b` at `8468e5da`. The tool failed and the scenario failed. The archive does not show the arguments of a failed proposal. This is a wrong tool choice, and the counter does not count it as a purchase attempt.
- The 2026-10-03 batch stays **UNMEASURED** for purchase attempts. Its three A04 final-turn `reject_url` / `no_plan` checks do not prove zero purchase attempts.

Evidence: [readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json),
`real_tool_enabled.claims_target`, `accepted_plans`, `secret_sentinel_checks`, `purchase_attempts`, and `a04`;
[2026-11-06 report](../../eval/results/artifacts/conversation-20261106b/report.md), `Purchase attempts`.
Source and prompt rules alone do not prove that these rules hold for all inputs.

## Product, prices, and users

The accepted catalog contains 40 meals under
[decision 0017](../../wiki/decisions/0017-forty-meal-catalog.md).
Requests support one to three (1-3) meals and one to eight (1-8) servings per meal.
The benchmark does not exhaustively test all 40 meals or every combination of pantry, diet, servings, and exclusions.

Sample catalog prices and nutrition totals are estimates.
They are not verified retailer prices, stock, product safety, financial savings, or population health outcomes.
The [backlog](../FEATURE_BACKLOG.md) records quantity-scaled USDA nutrition estimates and the optional Kroger live-price overlay.
The [scope](../../.codex/project-context.md) keeps sample-catalog cents as the budget figure.
Neither ingredient diet facts nor estimates certify retailer products or cross-contact safety.
Every grocery estimate MUST retain this exact notice:

> Estimated from the demo price catalog. Store prices, availability, taxes, delivery fees, and tips are not verified.

Plans do not reserve money. The manual monthly limit is user input, not independently verified financial evidence.
The local runtime uses one server-selected demo user with shared context.
It does not establish isolation among invited hosted users.
See the [scope](../../.codex/project-context.md),
[agent handler](../../backend/app/services/agent_jobs.py), and [post-hoc record](../../wiki/phases/posthoc-gold-20261003.md).
Earlier health and activity planning remains historical. A4 retains legacy records; this pack changes no data.

## Providers and deployment

| Evidence class | What this pack supports | What remains pending |
|---|---|---|
| Deterministic and local emulator | Fixture checks, local PostgreSQL jobs, and Floci SQS/S3 paths. Browser records exercise the local app with fixture provider responses. | These checks do not establish live model quality or provider readiness. |
| Plaid Sandbox | Source scope and the paused D4 task. | No Sandbox request or posted/pending financial observation is supplied. No real accounts are in scope. |
| Live provider | Archived real Bedrock batches: the benchmark on 2026-10-03 and 2026-10-05, and the conversation batches through `conversation-20261107`. | No live cart add and no live Kroger evaluation is on record. Plaid has no Sandbox run. The Instacart adapter is retired by decision 0023. |
| Deployed | Restricted owner/invited-user hosting design and source work. | No deployment, hosted chat, deployed access control, or public URL is verified. Each mutating AWS step still needs owner confirmation under D5. |

Evidence: [benchmark record](../../wiki/phases/benchmark-20261003.md),
[browser record](../GROCERY_VERIFICATION_PLAN.md), [scope](../../.codex/project-context.md),
[Compose](../../compose.yaml), and [backlog](../FEATURE_BACKLOG.md).
Owner authorization for restricted hosting scope is not deployment evidence.
The Instacart adapter is retired. Fixture handoff responses in the frozen suite are not live results.
Release remains unverified because task quality fails.
D4 remains paused. D5 source publication does not change these limits.

## Latency, cost, and authorship

Latency covers all attempts in each real Bedrock condition, including failures.
Each condition has 33 known end-to-end slot samples, with zero unknown samples and nearest-rank percentiles.
Do not report these values as successful-request latency alone.
The [readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json),
`telemetry_groups`, separates slot, turn, and provider timing.

The archived model token-cost estimate is $0.3347876400 USD, not an AWS bill.
It excludes taxes, other AWS resources, caching discounts, and billing reconciliation.
The readout's `cost` field records the dated rate source. No new cost estimate accompanies the post-hoc correction.
The writer has not checked hashes or executed reproducers.
The coordinator verifies artifacts and runs gates. A separate Codex or Grok reviewer verifies the result independently.

The author still writes the final paper and records/submits the video.
The [course transcript](../CAP6938%20August%2025.txt), lines 80-110 and 250-278,
sets a maximum of eight pages in two columns and rejects generating the report from scratch with ChatGPT.
This pack supplies prompts, citations, and provenance. It does not complete or submit graded work for the author.
