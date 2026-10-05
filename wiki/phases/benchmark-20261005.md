# Fresh live benchmark — 2026-10-05

- Date: 2026-10-05.
- Source revision: `d50572a15d007be5afe26f44a378a57ff6d896db` on `main`.
- Backlog item: F1. The batch measures the four application fixes in #387 to #390 and the E1 to E4 changes in #392 to #395.
- Archive: [`eval/results/artifacts/benchmark-20261005/`](../../eval/results/artifacts/benchmark-20261005/). The [artifact manifest](../../eval/results/artifacts/benchmark-20261005/artifact-manifest.json) holds a SHA-256 hash for each file.

This record does not replace the [2026-10-03 benchmark](benchmark-20261003.md) or the
[post-hoc correction](posthoc-gold-20261003.md). Those records stay unchanged.

## Batch identity

The model is `us.amazon.nova-2-lite-v1:0` in `us-east-1`. The CLI fixes max tokens at
4096, temperature at 0, and reasoning effort at `low`.
The batch started at `2026-10-05T21:04:29.647010+00:00` UTC.
It ended at `2026-10-05T21:13:08.359416+00:00` UTC.
The evaluation manifest hash is `996eeb4f372967f1cc647815040196b6ab8254464f0ad8c49df042c7d984933d`.

The corpus is `backend/tests/evaluation/scenarios.json` at the source revision. It
differs from the 2026-10-03 corpus in F04, F05, and X03: the F04/F05 final-turn gold
from the post-hoc correction and the X03 gold from #390. The
[archived copy](../../eval/results/artifacts/benchmark-20261005/scenarios.json) is the exact input.
The rates file is the 2026-10-03 [Nova 2 Lite rates](../../eval/results/artifacts/benchmark-20261005/nova2-rates.json).

The batch ran from the host with `--local-services`. A dedicated `postgres:16` server
held the evaluation database. Floci answered on the host port 4567. The Compose worker
was running and consuming `fewia-agent` during the batch.

| Condition | Evidence class | Executions |
|---|---|---|
| `tool_enabled` | `real_bedrock` | 33 completed |
| `no_tool` | `real_bedrock` | 1 completed, 32 failed |
| `deterministic_fixture` | `deterministic_fake_provider` | 42 completed |
| `controlled_fixture` | `deterministic_fake_provider` | 12 completed |
| `controlled_fixture` | `local_postgresql` | 3 completed |
| `deterministic` | `deterministic_fake_provider` | 15 completed |

The [live integrity record](../../eval/results/artifacts/benchmark-20261005/live-integrity.json)
confirms 138 slots and that the journal matches the report.

## Fixture rehearsal

Before the live batch, the archived fixture driver ran the same corpus at the same
revision with local services. All 138 slots completed: 135 `deterministic_fake_provider`
and three `local_postgresql`. The three P05 slots passed with the Compose worker running.
See the [fixture integrity record](../../eval/results/artifacts/benchmark-20261005/fixture-integrity.json).
Fixture results do not establish live model quality.

## Live quality and targets

All values come from the `tool_enabled / real_bedrock` and `no_tool / real_bedrock`
sections of the [report](../../eval/results/artifacts/benchmark-20261005/live-nova2-20261005/report.md).

| Measure | Numerator and denominator | Result and scope |
|---|---|---|
| Tool-enabled task quality | 25 passed / 33 applicable; 8 failed, zero unassessed | 75.8%; 90% target **FAIL** |
| Supported factual claims, conservative | 109 supported / (109 assessed + three unknown) | 97.3%; 95% target **PASS** for bounded public-output claims |
| Supported factual claims, assessed only | 109 / 109 | 100%; excludes the three unknown claims |
| Valid tool calls | 36 / 36 calls | Validity only |
| Expected tool selection | 18 / 21 expected calls | Selection matching |
| Expected arguments | 16 / 21 expected calls | Argument matching |
| Unnecessary calls | Three / 21 calls in this metric's scope | Lower is better |
| Plan assessment | 13 passed / 17 assessed | Zero unassessed |
| Outcome assessment | 25 passed / 28 assessed | Five unassessed |
| Clarification, assessed only | Six passed / six assessed | Three unassessed |
| No-tool task quality | Zero passed / 33 applicable | 33 failed; zero unassessed |

Eight supported refusals stay outside the factual denominator.
Call denominators differ from slot denominators.
This result does not establish a general factuality or hallucination guarantee.

## Failed tool-enabled slots

| Case | Repeats | Observed turns | Failed checks |
|---|---|---|---|
| A02 | 1, 2, 3 | Repeat 1 clarified with no tool call. Repeats 2 and 3 called `plan_groceries` and returned a plan. | Outcome, expected arguments; selection in repeat 1; unexpected plan in repeats 2 and 3 |
| F04 | 1, 2, 3 | Turn 2 called `plan_groceries` and then clarified. | Unnecessary calls only |
| F02 | 2, 3 | Turn 3 clarified with no tool call instead of planning again. | Expected selection and arguments; the plan assessment |

The A02 gold expects a typed planner conflict. The A02 gold alignment is an open owner
decision. With A02 failing in all three repeats, the highest reachable task result is
30/33, which equals 90.9%.
A failed assessment alone does not establish a model or application defect.

## Latency and estimated model cost

| Condition | p50 seconds | p95 seconds | Sample slots |
|---|---|---|---|
| `tool_enabled / real_bedrock` | 8.01 | 16.75 | 33 |
| `no_tool / real_bedrock` | 6.83 | 14.14 | 33 |

The token-cost estimate is USD 0.3374943000: USD 0.1807037100 for the tool condition
and USD 0.1567905900 for the no-tool condition. The estimate uses the 2026-10-03 rates.
It is not an AWS bill.

## Limits

Release is **NOT certified**. Task quality failed its target.
Purchase attempts stay unmeasured.
This archive contains no Plaid Sandbox, live Instacart, or deployed hosting proof.
These are local results. GitHub Actions did not run because of the account billing limit.
