# Post-hoc final-turn gold correction

- Date: 2026-10-03.
- Evidence class: post-hoc assessment of saved `real_bedrock` observations.
- Original observations: `4b877d470258561cedd3375e38efc02362ce5f22`.
- Scorer and corrected gold: `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6`, published in [#348](https://github.com/emanuelGitCodes/fewia/pull/348).
- Derivation time: `2026-10-03T23:57:26.642449+00:00` UTC, from [provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json).

The [original benchmark](benchmark-20261003.md) remains authoritative for its original corpus.
Its tables and archived files retain the 17/33 task result.
This separate record reports 23/33 (69.7%) after a bounded gold correction.
The 90% task target still **FAILS**. Release is **NOT certified**.

## Correction scope and timing

The original batch ran from `2026-10-03T22:51:03.983156+00:00` to `2026-10-03T22:59:50.730712+00:00` UTC.
The correction followed access to the original outputs.
It is post-hoc evidence, not a fresh batch, rerun, model retest, or independent benchmark.
The coordinator rescored the exact saved observations without provider or database calls.
The archive records zero new inference calls and 138 unchanged observation slots.

F04/F05 included setup-turn expectations in `expected.model_tools`.
The existing scorer checks final-turn tool selection and arguments.
The gold correction matches that contract; it makes no scoring-code change.
It does not broaden allowed outcomes or change other expected results.
F04 now expects no final-turn tool for the vegan conflict.
F05 expects only the final `plan_groceries` call for four servings.
A failed assessment alone does not establish a model or application defect.

Only six `tools` assessments change: F04 and F05, three tool-enabled repeats each.
Every other assessment, observation, latency, token count, and execution status stays unchanged.
The [script](../../eval/results/artifacts/posthoc-gold-20261003/rescore.py) asserts that scope when it compares the saved and rescored slots.

## Provenance

The [provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json) identifies both source SHAs and manifest hashes.
The [corrected manifest](../../eval/results/artifacts/posthoc-gold-20261003/corrected-manifest.json) supplies the corrected canonical corpus hash.
The [artifact manifest](../../eval/results/artifacts/posthoc-gold-20261003/artifact-manifest.json) supplies file SHA-256 hashes.
A canonical corpus hash and a corpus-file SHA-256 identify different representations.

| Identity | Value |
|---|---|
| Original observation source SHA | `4b877d470258561cedd3375e38efc02362ce5f22` |
| Scorer and corrected-gold source SHA | `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6` |
| Original canonical corpus hash | `bf72e0d4021c2dd37f69311894e1893ef6272e82e207933bafc30607473dbbe4`, from `manifest.corpus_hash` in the [original report](../../eval/results/artifacts/benchmark-20261003/live-nova2-20261003/report.json). |
| Corrected canonical corpus hash | `87d5808e305501f875e2e9ac8ad915df1f85564789bbdd2bc8e0bd650a313071` |
| Original evaluation manifest hash | `34888d692bee873021cbfc2478b479ed62badbc045f3c83618ad511eb720778d` |
| Corrected evaluation manifest hash | `6af7f64580e9edca91fa73ef7bf88f28615440b03c0ef635d8ed7864e682c2da` |
| Original report file SHA-256 | `552dd3511ad2771a4ee5ae8c1a9f15e0eda4ff9380207547d48a29e0f0654aa7` |
| Original corpus file SHA-256 | `c1efc09c7ce64de59cc36e673342ddef5049e7405612f67630334810ed3d8a84` for [scenarios.json](../../eval/results/artifacts/benchmark-20261003/scenarios.json), listed in the [original artifact manifest](../../eval/results/artifacts/benchmark-20261003/artifact-manifest.json). |
| Corrected corpus file SHA-256 | `3b264242357cdfaba23b72a86363e49c0f05c12cdb8bca2764292a85ddcd14a5` |
| Assessment delta file SHA-256 | `6eb28e56e82cc47e2e8a1fd8103b00a0a6cdabee7db8fe3229efdb057308292f` |
| Summary file SHA-256 | `bd21e5fcdc8e46f35bdad7a8e2d9c60a710b2e85674fc10b3ab1e7a057927d8a` |
| Reproduction script SHA-256 | `c769096e48fbe7f3f99896749be51fc55cc44685d6add251897fcf9427d5efa5` |

The manifest comparison preserves all fields except `corpus_hash` and `manifest_hash`.
The model remains `us.amazon.nova-2-lite-v1:0` in `us-east-1`.
Settings remain 4096 max tokens, temperature 0, and `low` reasoning effort.
The catalog remains `sample-prices-v2`; prompts and catalog hashes stay unchanged.

## Results and six assessment deltas

The original column cites the [benchmark readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json).
The corrected column cites the `tool_enabled` / `real_bedrock` group in the [summary](../../eval/results/artifacts/posthoc-gold-20261003/summary.json).
Both columns concern the same October 3 observations at the source SHA above.

| Measure and scope | Original | Post-hoc correction |
|---|---|---|
| Tool-enabled language task | 17/33 (51.5%); 16 failed, zero unassessed | 23/33 (69.7%); ten failed, zero unassessed; 90% target **FAIL** |
| Supported factual claims, conservative | 98/(98 assessed + two unknown) = 98% | Unchanged; 95% target **PASS** for bounded public-output claims |
| Supported factual claims, assessed only | 98/98 = 100% | Unchanged; excludes unknown claims |
| Valid tool calls | 28/28 calls | Unchanged |
| Expected tool selection | 11/24 expected calls | 11/18 expected final-turn calls (61.1%) |
| Expected arguments | 11/24 expected calls | 11/18 expected final-turn calls (61.1%) |
| Unnecessary calls | Two/13 calls in this metric's scope | Unchanged |
| No-tool language task | 0/33; 33 failed, zero unassessed | Unchanged |

Call denominators differ from slot denominators.
Selection and argument assessment passes rise from 20/33 to 26/33 slots each.
The expected-call numerator stays 11; six setup-turn expectations leave the denominator.
Ten supported refusals stay outside the factual denominator.
The extractor still records zero unsupported factual claims and two unknown claims.
These counts do not establish a general factuality or hallucination guarantee.

The [assessment deltas](../../eval/results/artifacts/posthoc-gold-20261003/assessment-deltas.json) contain all six changes.
Each row below concerns the `tools` assessment for a tool-enabled slot.

| Case | Repeat | Tools status | Expected selection | Expected arguments |
|---|---:|---|---|---|
| F04 | 1 | Failed → passed | 0/1 → 0/0 | 0/1 → 0/0 |
| F04 | 2 | Failed → passed | 0/1 → 0/0 | 0/1 → 0/0 |
| F04 | 3 | Failed → passed | 0/1 → 0/0 | 0/1 → 0/0 |
| F05 | 1 | Failed → passed | 1/2 → 1/1 | 1/2 → 1/1 |
| F05 | 2 | Failed → passed | 1/2 → 1/1 | 1/2 → 1/1 |
| F05 | 3 | Failed → passed | 1/2 → 1/1 | 1/2 → 1/1 |

For F04, 0/0 records no expected final-turn calls; it is not an empirical 100% call rate.
The scorer records passed status for that empty expectation.
Outcome assessments stay unchanged, including six unassessed outcome slots.
Task quality combines the existing assessment scopes; 23/33 is not the tools-only pass count of 24/33.

## Reproduce from the saved archive

Use the scorer checkout at `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6` with these archives present.
From the repository root, the coordinator runs:

```sh
PYTHONPATH=backend backend/.venv/bin/python \
  eval/results/artifacts/posthoc-gold-20261003/rescore.py
```

The script creates `eval/results/artifacts/posthoc-gold-20261003/reproduced/` exclusively.
An existing directory fails; the script does not overwrite the archive.
It reads the original live report and [corrected corpus](../../eval/results/artifacts/posthoc-gold-20261003/corrected-scenarios.json).
It writes a new summary, deltas, corrected manifest, and provenance in the reproduced directory.
The fresh provenance timestamp differs from the archived derivation timestamp.
This writer has not run the command or checked the recorded hashes.

## Unchanged limits and remaining work

The archive contains one live batch with three repeats per case and 66 real Bedrock observations.
It also contains 69 deterministic fake-provider records and three local PostgreSQL records.
The rescore retains those evidence classes; fixture success does not establish live model quality.
The structured reference tests final requests, not preceding language interactions.
The local product uses React and TypeScript, FastAPI, PostgreSQL, a worker, and Floci SQS and S3.
It uses a manual budget and one server-selected demo user with shared demo context.
These observations do not establish isolation for restricted hosted users.

The accepted catalog contains 40 meals under [decision 0017](../decisions/0017-forty-meal-catalog.md).
Requests support one to three (1-3) meals and one to eight (1-8) servings per meal.
The benchmark does not cover every catalog meal.
Every grocery estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Six accepted live final plans still have zero tested constraint violations.
This result covers only accepted plans and tested constraints.
The synthetic-sentinel scan still covers 48 captured turns across 33 tool-enabled slots.
Every captured turn has an explicit false leak flag; no turn has incomplete capture.
This synthetic scope does not establish an unrestricted secret-leak guarantee.
Purchase attempts remain **UNMEASURED**.
The three A04 final-turn `reject_url` / `no_plan` checks do not prove zero purchase attempts.

Tool-enabled executions remain 33/33 completed.
No-tool executions remain 31 failed, one partial, and one completed; 32 observations record `invalid_output`.
Failures stay in the latency and quality scope.
Recorded latency, token counts, and model-cost evidence remain in the [original record](benchmark-20261003.md#latency-and-estimated-model-cost).
No new model-cost estimate or billing reconciliation occurs.
This archive supplies no live Plaid, Plaid Sandbox, live Instacart, or deployed hosting proof.
Instacart development links prove handoff only; they do not verify retailer prices or availability.
No retailer, financial, or population claim follows from this sample.

The user authorized retention of legacy data and hosting limited to the owner and invited users.
That authorization is not deployment evidence. Retired health and activity planning stays historical.
D3's author-owned outline and evidence pack remain pending. D4 remains paused.
D5 source work does not establish deployed access controls or a hosted chat result.
Evidence tables MUST keep deterministic, sandbox, live, and deployed evidence separate.
Course authors MAY cite these artifacts with their scope and provenance.
This record does not write or submit a student's graded paper.
Coordinator verification and independent Codex or Grok review remain open.
