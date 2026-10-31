# Evaluation

## Scope

FEWIA runs a local React and TypeScript chat with FastAPI, PostgreSQL, a worker, and Floci SQS and S3. Real Bedrock calls use `LLMProvider`. The first-release provider boundary includes Plaid Sandbox and the Kroger cart. [Decision 0023](../wiki/decisions/0023-retire-instacart-adapter.md) retires the Instacart adapter; the frozen suite keeps its fixture handoff scenario (P02). This benchmark supplies Bedrock evidence only; Plaid Sandbox and live Instacart evidence remain open. The product uses a manual budget and sample catalog prices. The product does not place orders or check out.

The product supports 40 meals under [decision 0017](../wiki/decisions/0017-forty-meal-catalog.md) and the [current project scope](../.codex/project-context.md). A request supports one to three (1-3) meals. Each meal supports one to eight (1-8) servings. This benchmark does not provide exhaustive catalog coverage.

The current evidence includes [the original benchmark](../wiki/phases/benchmark-20261003.md) and a separate [post-hoc gold correction](../wiki/phases/posthoc-gold-20261003.md). The [completion checkpoint](../wiki/phases/evaluation-completion.md) also preserves earlier component history. Older health and activity planning sources remain historical. [Decision 0018](../wiki/decisions/0018-retain-legacy-data.md) retains existing legacy data without reviving retired routes or treating stored totals as current prices.

Every grocery estimate MUST show this notice:

> Estimated from the demo price catalog. Store prices, availability, taxes, delivery fees, and tips are not verified.

[Decision 0024](../wiki/decisions/0024-store-neutral-estimate-notice.md) sets this notice. The benchmark corpus is `grocery-eval-v1.1`. The Oct 3 and Oct 5 batches ran `grocery-eval-v1`, whose notice named Instacart; their records stay unchanged. A `grocery-eval-v1.1` batch MUST NOT be compared with them as the same measurement.

## Current API

[`run_evaluation_batch`](../backend/app/evaluation_batch.py) executes the frozen matrix through the runtime and dispatch paths. [`python -m app.evaluate`](../backend/app/evaluate.py) publishes an exclusive journal, JSON report, Markdown report, and completion marker. The CLI source is published in [#339](https://github.com/emanuelGitCodes/fewia/pull/339) and [#341](https://github.com/emanuelGitCodes/fewia/pull/341).

[`run_evaluation`](../backend/app/evaluation_runner.py) remains a fixture-only legacy API. Its earlier component smoke recorded 42 scored passes and 48 unassessed slots. Those counts are historical component evidence, not the completed batch's live quality.

[`prepare_matrix`](../backend/app/evaluation_matrix.py) validates the finite `grocery-eval-v1.1` corpus (decision 0024) and returns isolated execution slots. It does not execute them.

The completed fixture and live batches each contain 138 records: 90 primary, 33 `no_tool`, and 15 structured references. The live batch contains 66 real model observations. Its other records remain fixture or local PostgreSQL evidence. See the [readout](../eval/results/artifacts/benchmark-20261003/benchmark-readout.json) and [live integrity record](../eval/results/artifacts/benchmark-20261003/live-integrity.json).

## Run the CLI

Use the checkout at source revision `4b877d470258561cedd3375e38efc02362ce5f22` for this replay example. Configure Bedrock access outside the command. Keep credentials out of source, model inputs, and logs.

```sh
cd backend
uv run python -m app.evaluate \
  --corpus ../eval/results/artifacts/benchmark-20261003/scenarios.json \
  --output-dir ../eval/results/nova2-replay-new \
  --revision 4b877d470258561cedd3375e38efc02362ce5f22 \
  --model-id us.amazon.nova-2-lite-v1:0 \
  --region us-east-1 \
  --rates ../eval/results/artifacts/benchmark-20261003/nova2-rates.json \
  --live-bedrock
```

The caller MUST use a new output directory for each run. An existing directory fails with exit 1. The CLI creates exclusive output and journal files. It fixes settings at 4096 max tokens, temperature 0, and `low` reasoning effort. It accepts the named Nova 2 Lite US profile only, in `us-east-1` or `us-west-2`. Rates, when supplied, MUST match the model and region.

`--corpus`, `--output-dir`, and `--revision` are required flags. `--rates` supplies dated token rates. `--local-services` enables isolated local service inputs from `FEWIA_EVALUATION_DATABASE_URL` and `FEWIA_EVALUATION_FLOCI_ENDPOINT`. Configure these outside the command. `AWS_PROFILE`, when set, selects the local Bedrock profile. No command above exposes credential values or secret paths.

Without `--live-bedrock`, the public CLI exits 1 before provider calls. The archived [fixture driver](../eval/results/artifacts/benchmark-20261003/fixture_driver.py) injects a fake provider and labels it `deterministic_fake_provider`. It is not a live CLI mode. The [SIGINT summary](../eval/results/artifacts/benchmark-20261003/sigint-summary.json) records exit 130 with 49 journal records preserved. Exit 0 means artifact completion, not target success or release certification.

## Completed benchmark result

The [benchmark phase](../wiki/phases/benchmark-20261003.md) records the exact manifest hash, UTC window, settings, and artifact links. It covers one live batch with three repeats per case at the source revision above.

| Live measure | Numerator / denominator | Verdict |
|---|---|---|
| Tool-enabled language task | 17 / 33; all 33 executions completed | 51.5%; 90% target FAIL |
| Supported factual claims, conservative | 98 / (98 assessed + two unknown) | 98%; 95% target PASS for bounded public-output claims |
| Supported factual claims, assessed only | 98 / 98 | 100%; excludes unknown claims |
| No-tool language task | Zero / 33 | All 33 failed quality |

Ten supported refusals do not enter the factual denominator. The no-tool executions include 31 failed, one partial, and one completed. Observations record `invalid_output` for 32 slots. Fixture success does not establish live quality.

These are the original quality results. The separate [post-hoc record](../wiki/phases/posthoc-gold-20261003.md) reports 23/33 task passes (69.7%), ten failed, and zero unassessed. The 90% target still FAILS. The correction removes F04/F05 setup-turn expectations to match the existing final-turn scorer contract. It changes six tools assessments only. It changes no scoring code or allowed outcomes. The original tables and archive remain unchanged. This rescore uses the exact saved observations after the original outputs were available. It makes no provider or database calls. It is not a fresh batch, a model retest, or an independent benchmark. Claims remain 98/(98 + two unknown), or 98%; no-tool task success remains 0/33. A failed task assessment alone does not establish a model or application defect.

Six accepted live final plans have zero tested violations. The synthetic-sentinel check captures 48 turns across 33 tool-enabled slots with explicit false leak flags and no incomplete capture. Purchase attempts are UNMEASURED. Separate A04 refusal/action checks do not prove zero purchase attempts.

Release is NOT certified. The task target failed. Plaid Sandbox, live Instacart, and deployed evidence remain absent. The [artifact manifest](../eval/results/artifacts/benchmark-20261003/artifact-manifest.json) preserves file hashes. Fixture and live integrity records report verified hashes and matching journals. These are recorded evidence, not checks run by this documentation writer.

The approved documentation baseline [#331](https://github.com/emanuelGitCodes/fewia/pull/331) was imported for record continuity. This documentation PR depends on #331 and #341. It does not claim either is merged.

## Fresh live batch, 2026-10-05

A fresh live batch ran at `main` revision `d50572a15d007be5afe26f44a378a57ff6d896db`.
It used the current corpus, which carries the F04/F05 and X03 gold changes, and
`--local-services`. The [benchmark record](../wiki/phases/benchmark-20261005.md) holds the
identity, the failed slots, and the limits. The
[archive](../eval/results/artifacts/benchmark-20261005/) holds the outputs and their hashes.

| Live measure | Numerator / denominator | Verdict |
|---|---|---|
| Tool-enabled language task | 25 / 33; all 33 executions completed | 75.8%; 90% target FAIL |
| Supported factual claims, conservative | 109 / (109 assessed + three unknown) | 97.3%; 95% target PASS for bounded public-output claims |
| Supported factual claims, assessed only | 109 / 109 | 100%; excludes unknown claims |
| No-tool language task | Zero / 33 | All 33 failed quality |

Eight slots failed: A02 in three repeats, F04 in three repeats, and F02 in two repeats.
The estimated model cost is USD 0.3374943000. Tool-enabled latency is 8.01 s at p50 and
16.75 s at p95. Release stays not certified.

Run this command from `backend/`. It needs a new output directory for each run. Set
`AWS_PROFILE`, `FEWIA_EVALUATION_DATABASE_URL`, and `FEWIA_EVALUATION_FLOCI_ENDPOINT`
outside the command. The Floci host endpoint is `http://127.0.0.1:4567`.

```sh
uv run python -m app.evaluate \
  --corpus tests/evaluation/scenarios.json \
  --output-dir "../eval/results/nova2-live-$(date -u +%Y%m%dT%H%M%S)" \
  --revision "$(git rev-parse HEAD)" \
  --model-id us.amazon.nova-2-lite-v1:0 \
  --region us-east-1 \
  --rates ../eval/results/artifacts/benchmark-20261003/nova2-rates.json \
  --local-services \
  --live-bedrock
```

## Conversation suite (`conversation-eval-v1`)

The conversation suite is separate from the benchmark above (owner decision, 2026-10-30). The benchmark corpus (`grocery-eval-v1.1`, decision 0024) keeps its 30 scenarios, and its batch keeps 138 slots. The benchmark CLI accepts only Nova 2 Lite.

- **Corpus.** [`conversation.json`](../backend/tests/evaluation/conversation.json) holds 12 scenarios (C01 to C12), 22 turns in all, with three repeats: substitutions, a follow-up, a false premise, a budget question, a proposal and an apply, off-topic and medical requests, a prompt injection, a nine-turn thread, and a purchase-override attempt. A test regenerates every gold value from the deterministic tools.
- **Runner.** [`evaluation_conversation.py`](../backend/app/evaluation_conversation.py) runs `run_chat` with validated model prose on, an in-memory plan revision, and a stub `propose`. Nothing writes the database.
- **Records.** Each turn record holds the tool trace, the prose gate reason, the validator verdict codes, the count of unmatched numbers, usage, latency, and the reply's SHA-256. A record MUST NOT hold the reply text or the unmatched tokens. A test runs a marker reply and asserts the marker is in no output file.
- **Scores.** [`evaluation_conversation_score.py`](../backend/app/evaluation_conversation_score.py) scores tools, outcome, gold facts, and grounding (`grounded_replies / prose_attempts`, unsupported numbers, fallbacks by gate reason), and reports p50 and p95 latency and cost per turn. Targets are reported, not enforced: grounded 99%, unsupported 0, p50 under 5 s, p95 under 12 s, cost under USD 0.006 per turn. A fixture run reports the cost and latency targets as `not_applicable`.
- **Profiles.** [`evaluation_profiles.py`](../backend/app/evaluation_profiles.py) allows `nova-2-lite`, `nova-2-pro`, and `claude-haiku`. Only Nova models are approved in the AWS account, so `claude-haiku` MUST NOT be run live. The `nova-2-pro` model ID is not verified.

Fixture run, from `backend/`:

```bash
uv run python -m app.evaluate_conversation \
  --corpus tests/evaluation/conversation.json \
  --output-dir /tmp/conversation-fixture \
  --profile nova-2-lite --region us-east-1 \
  --revision "$(git rev-parse HEAD)" --fixture
```

A live run replaces `--fixture` with `--live-bedrock` and adds `--rates`. It spends money and needs the owner's approval. Set `AWS_SHARED_CREDENTIALS_FILE` to the file that `infra/bedrock_session.py` writes and `AWS_PROFILE` to `fewia-bedrock-dev`.

First live batch (2026-10-30, Nova 2 Lite, revision `95cfbea3`): [report](../eval/results/artifacts/conversation-20261030/report.md). It recorded 66 of 66 turns. The validator accepted 9 of 36 prose attempts (25%), with 59 unsupported numbers. Latency p50 was 4.6 s and p95 was 16.4 s. Cost was USD 0.0057 per turn.

## Component boundaries

- [`observe_reference_case`](../backend/app/evaluation_reference.py) runs the final structured request for five supported reference scenarios through deterministic planning. It does not run earlier language turns or a durable evidence store.
- The approved claim and task helpers use public outputs, bounded claims, strict task criteria, explicit denominators, and visible unknown counts. They keep fixture, reference, and model quality separate. A passing helper does not prove a live provider result.
- Provider drivers cover controlled failures and duplicate delivery. A driver exercises only its named condition.
- [`summarize_telemetry`](../backend/app/evaluation_telemetry.py) groups captured observations by condition and evidence class. It reports known totals and unknown counts separately.
- [`summarize_evaluation`](../backend/app/evaluation_summary.py) validates identities, groups observations by condition and evidence class, and preserves metric and task scopes and unknown counts. Partial matrices remain partial.
- [`estimate_cost`](../backend/app/evaluation_cost.py) uses dated rate inputs and captured token counts. It reports known values as lower bounds when usage is incomplete. It is not an invoice or billing reconciliation.
- [`evaluation_io`](../backend/app/evaluation_io.py) writes exclusive journal and report files. Its completion marker records hashes for the JSON and Markdown reports.

The component set keeps deterministic fixtures, structured references, controlled provider conditions, and model observations separate. Components do not certify targets. The completed batch's bounded target verdicts appear above. They do not provide a general guarantee against hallucinations.

## Database validation

The coordinator configures reachable, isolated test databases through `FEWIA_JOB_TEST_DATABASE_URL` and `FEWIA_EVALUATION_DATABASE_URL`. When `FEWIA_REQUIRE_DB=1`, a missing required evaluation URL fails validation.

```sh
FEWIA_REQUIRE_DB=1 \
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

Configure both URLs for isolated test databases. Keep credentials out of the documentation and source files.

## Evidence and provenance

Evidence tables MUST keep deterministic, sandbox, live-provider, and deployed evidence in separate groups. Do not pool fake-provider success with live-provider success. Mark samples and unknown values. A scenario matrix is a plan until its execution record exists. This archive does not supply verified retailer, financial, or population claims.

Each evidence-table row MUST identify its source, source revision, evidence class, scope, date, and denominator. Keep citations and provenance with the row.
