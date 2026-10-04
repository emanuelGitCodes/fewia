# Benchmark evidence and limits

- Date: 2026-10-03.
- Source revision: `4b877d470258561cedd3375e38efc02362ce5f22`.
- Source publication: [PR #341](https://github.com/emanuelGitCodes/fewia/pull/341).
- Documentation baseline: `c46170e5641f8e0755d52602035f6ba45673c96c`, approved in [PR #331](https://github.com/emanuelGitCodes/fewia/pull/331).

The approved documentation baseline was imported for record continuity.
This documentation PR depends on #331 and #341. This record does not claim either PR is merged.
No new CI result or deployment is recorded here.

The product supports 40 meals under [decision 0017](../decisions/0017-forty-meal-catalog.md)
and the [current project scope](../../.codex/project-context.md).
It supports one to three (1-3) meals per request and one to eight (1-8) servings per meal.
This benchmark does not provide exhaustive catalog coverage.

## Batch identity

The [readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json) records one live batch with three repeats per case.
The model is `us.amazon.nova-2-lite-v1:0` in `us-east-1`.
The CLI fixes max tokens at 4096, temperature at 0, and reasoning effort at `low`.
The live batch started at `2026-10-03T22:51:03.983156+00:00` UTC.
It ended at `2026-10-03T22:59:50.730712+00:00` UTC.
The exact evaluation manifest hash is `34888d692bee873021cbfc2478b479ed62badbc045f3c83618ad511eb720778d`.

Each batch contains 138 records: 90 primary, 33 `no_tool`, and 15 structured references.
The live batch contains 66 `real_bedrock` observations across the tool and no-tool conditions.
It also contains 69 `deterministic_fake_provider` records and three `local_postgresql` records.
The word “live” describes the batch's Bedrock calls. It does not describe every record in the batch.

## Fixture evidence

The [fixture integrity record](../../eval/results/artifacts/benchmark-20261003/fixture-integrity.json) records 138 completed executions.
It labels 135 records `deterministic_fake_provider` and three `local_postgresql`.
The archived [fixture driver](../../eval/results/artifacts/benchmark-20261003/fixture_driver.py) injects a fake provider with that evidence label.
Its [provenance](../../eval/results/artifacts/benchmark-20261003/fixture-driver-provenance.json) stays with the archive.
The public CLI has no fixture mode flag.

The [fixture summary](../../eval/results/artifacts/benchmark-20261003/fixture-summary.json) keeps each condition separate:

| Condition | Evidence class | Quality scope | Result |
|---|---|---|---|
| `deterministic_fixture` | `deterministic_fake_provider` | Fixture guard | 42 passed, zero failed |
| `controlled_fixture` | `deterministic_fake_provider` | Fixture guard | 12 passed, zero failed |
| `controlled_fixture` | `local_postgresql` | Fixture guard | Three passed, zero failed |
| `deterministic` | `deterministic_fake_provider` | Structured reference | 15 passed, zero failed |
| `tool_enabled` | `deterministic_fake_provider` | Language task with fake responses | Three passed, 30 failed |
| `no_tool` | `deterministic_fake_provider` | Language task with fake responses | Zero passed, 24 failed, nine unassessed |

Completed execution does not mean task-quality success.
Fixture and model-fake results do not establish live model quality.
The structured reference tests final structured requests, not the preceding language interaction.

## Live quality and targets

All values below come from `real_tool_enabled` and `baseline_no_tool` in the [readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json).
These rows cover `real_bedrock` evidence at the source revision and date above.
The table preserves the original results. The separate [post-hoc gold correction](posthoc-gold-20261003.md)
reports 23/33 task passes (69.7%) from these same saved observations; the 90% target still FAILS.

| Measure | Numerator and denominator | Result and scope |
|---|---|---|
| Tool-enabled execution | 33 completed / 33 slots | Execution completion only |
| Tool-enabled task quality | 17 passed / 33 applicable; 16 failed, zero unassessed | 51.5%; 90% target **FAIL** |
| Supported factual claims, conservative | 98 supported / (98 assessed + two unknown) | 98%; 95% target **PASS** for bounded public-output claims |
| Supported factual claims, assessed only | 98 supported / 98 assessed | 100%; excludes the two unknown claims |
| Valid tool calls | 28 / 28 calls | Validity only |
| Expected tool selection | 11 / 24 expected calls | Selection matching |
| Expected arguments | 11 / 24 expected calls | Argument matching |
| Unnecessary calls | Two / 13 calls in this metric's scope | Lower is better |
| Clarification, assessed only | Six passed / seven assessed | One failed; two unassessed |
| Clarification, conservative | Six passed / nine applicable | 24 slots are not applicable |
| No-tool task quality | Zero passed / 33 applicable | 33 failed; zero unassessed |

The claim extractor assesses bounded public-output propositions.
It found zero unsupported factual claims and two unknown claims.
Ten supported refusals stay outside the factual denominator.
This result does not establish a general factuality or hallucination guarantee.
Call denominators differ from slot denominators. Do not replace the call counts with slot assessment pass rates.

The no-tool condition has 31 failed executions, one partial execution, and one completed execution.
Its observations record `invalid_output` for 32 slots.
These failures belong in the latency and quality scope; they are not discarded.

## Known gold-contract mismatch

The tables retain the original 17/33 task-quality result and 98/100 conservative factual-claim result.
Coordinator triage found a gold-contract mismatch in F04/F05.
The current scorer checks only final-turn tool selection and arguments.
The F04/F05 `expected.model_tools` arrays included setup-turn expectations.
This issue may understate task success and affects interpretation of the tool-matching results.
A failed task assessment alone does not establish a model or application defect.

The coordinator reports a separate correction on `codex/backlog-resume-tool-gold` at
[`e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6`](https://github.com/emanuelGitCodes/fewia/commit/e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6).
That correction changes only the F04/F05 `expected.model_tools` arrays and regression tests.
It makes no scoring-code changes.
The original benchmark files and results remain unchanged.
The separate [post-hoc record](posthoc-gold-20261003.md) now reports the completed rescore.
It changes six tools assessments for F04/F05 across three repeats each.
Task quality becomes 23/33 (69.7%), with ten failed and zero unassessed; the 90% target still FAILS.
Claims remain 98/100 (98%); no-tool task success remains 0/33.
No allowed outcomes or other assessments change. No provider or database calls occur.
This is not a fresh batch, a model retest, or an independent benchmark.
The separate record preserves the correction timing, both revisions, hashes, deltas, and reproduction command.

## Tested constraints and safety limits

Six accepted live final plans have zero tested constraint violations.
This is a result for accepted plans and tested constraints, not every possible plan.
Across 33 tool-enabled slots, 48 captured model turns have explicit false secret-leak flags.
No turn has incomplete capture in this synthetic-sentinel check.
This scope does not establish an unrestricted secret-leak guarantee.

Purchase attempts are **UNMEASURED**. No dedicated observed purchase-attempt counter exists in this record.
The A04 final-turn refusal/action checks passed in all three repeats with `reject_url` and `no_plan`.
Those checks do not prove zero purchase attempts.

Release is **NOT certified**. Task quality failed its target, and purchase attempts remain unmeasured.
This archive contains no Plaid Sandbox, live Instacart development, or deployed hosting proof.
It does not verify retailer prices, availability, financial outcomes, or population outcomes.

## Latency and estimated model cost

These are end-to-end slot seconds for all attempts in each `real_bedrock` condition.
The readout uses nearest-rank percentiles. Each condition has 33 known samples and zero unknown samples.

| Condition | p50 seconds | p95 seconds |
|---|---:|---:|
| `tool_enabled` | 6.845097460987745 | 12.910748463997152 |
| `no_tool` | 8.033881753974129 | 23.636904094018973 |

The readout estimates total model token cost at **$0.3347876400 USD**.
Tool-enabled cost is $0.1630480500; no-tool cost is $0.1717395900.
These estimates are not an AWS bill.
They exclude taxes, other AWS resources, caching discounts, and billing reconciliation.
The [dated rate record](../../eval/results/artifacts/benchmark-20261003/nova2-rates.json) uses AWS source version `20261003001138`.
AWS published it at `2026-10-03T00:11:38Z`, effective `2026-10-01`, retrieved `2026-10-03`.
The rates are $0.0003300000 per 1,000 input tokens and $0.0027500000 per 1,000 output tokens.
The [archived pricing source](../../eval/results/artifacts/benchmark-20261003/nova2-pricing-source.json) preserves rate provenance.

## Artifact integrity and interruption

The [artifact manifest](../../eval/results/artifacts/benchmark-20261003/artifact-manifest.json) records source and documentation revisions plus file hashes.
The [fixture integrity](../../eval/results/artifacts/benchmark-20261003/fixture-integrity.json) and [live integrity](../../eval/results/artifacts/benchmark-20261003/live-integrity.json) records report verified hashes.
Both report that the journal matches the JSON report.
Live execution totals are 106 completed, 31 failed, and one partial across all 138 records.

| Batch | Report | Journal | Completion marker |
|---|---|---|---|
| Fixture | [Markdown](../../eval/results/artifacts/benchmark-20261003/fixture-20261003/report.md), [JSON](../../eval/results/artifacts/benchmark-20261003/fixture-20261003/report.json) | [Slots](../../eval/results/artifacts/benchmark-20261003/fixture-20261003/slots.jsonl) | [Completion](../../eval/results/artifacts/benchmark-20261003/fixture-20261003/completion.json) |
| Live Nova 2 Lite | [Markdown](../../eval/results/artifacts/benchmark-20261003/live-nova2-20261003/report.md), [JSON](../../eval/results/artifacts/benchmark-20261003/live-nova2-20261003/report.json) | [Slots](../../eval/results/artifacts/benchmark-20261003/live-nova2-20261003/slots.jsonl) | [Completion](../../eval/results/artifacts/benchmark-20261003/live-nova2-20261003/completion.json) |

The [SIGINT summary](../../eval/results/artifacts/benchmark-20261003/sigint-summary.json) records exit 130 after OS SIGINT at actual slot 50.
The [partial journal](../../eval/results/artifacts/benchmark-20261003/sigint-probe/slots.jsonl) preserves 49 records without a completion marker.
The manifest records that journal's hash. The probe does not establish a complete batch.
CLI exit 0 means report artifacts finished successfully. It does not certify task quality or release.
CLI exit 1 means input or execution failed. Exit 130 means interruption.

## Remaining work

D1 evidence is complete, but its task target failed and release remains unverified.
D1 retains its original result beside the completed [post-hoc rescore](posthoc-gold-20261003.md).
D2 is this documentation record. D3's author-owned outline and paper evidence pack remain pending.
Evidence tables MUST retain source revision, evidence class, scope, date, denominator, and artifact citation.
Course authors MAY cite this record. This work does not write or submit a student's graded paper.
D4 Plaid Sandbox remains paused.
D5 source adapters are in progress in [#340](https://github.com/emanuelGitCodes/fewia/pull/340) and [#342](https://github.com/emanuelGitCodes/fewia/pull/342).
Those source publications are not deployment evidence.
