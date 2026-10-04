# Author-owned course evidence pack

This pack supports the author's own course paper and demonstration.
The author still writes the final paper, records the video, and submits both.
It contains prompts, source maps, and archived evidence. It contains no completed paper or recorded demo.

The [course transcript](../CAP6938%20August%2025.txt) sets a maximum of eight pages,
two columns, a code repository, and a video (lines 80-110).
Lines 250-278 ask authors not to generate the report from scratch with ChatGPT.
The author MUST follow that boundary. This pack supplies no LaTeX or generated essay.
The outline includes references within eight pages as a conservative planning assumption.

## Use the pack

| Document | Author task |
|---|---|
| [Paper outline](PAPER_OUTLINE.md) | Answer the section questions in your own words. Choose evidence and citations. |
| [Demo script](DEMO_SCRIPT.md) | Prepare an authorized local runtime. Record observable states and explain the evidence limits. |
| [Failure log](FAILURE_LOG.md) | Inspect each selected case and distinguish triage from proven causes. |
| [Limitations](LIMITATIONS.md) | Select the limits that bind your claims. |

Use the [backlog](../FEATURE_BACKLOG.md) for remaining owner work.
Supporting documents do not establish completion of the final paper or video.

## Accepted product and source map

The active problem is budget-aware grocery planning under the
[project scope](../../.codex/project-context.md) and
[decision 0017](../../wiki/decisions/0017-forty-meal-catalog.md).
Health and activity planning text describes the earlier project. It is not the first-release scope.
The catalog contains 40 meals in `sample-prices-v2`.
Requests support one to three (1-3) meals and one to eight (1-8) servings per meal.
The authoritative meal list is `backend/app/domain/catalog_recipes.json`, as named in decision 0017.

Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

| Path | Source and boundary |
|---|---|
| Local interface and API | [React and TypeScript App](../../frontend/src/App.tsx); [Compose](../../compose.yaml) runs FastAPI and the web interface on loopback. |
| Jobs and planning | [Agent handler](../../backend/app/services/agent_jobs.py) selects chat or planning. [Plan job](../../backend/app/services/plan_job.py) validates inputs and computes the budget. |
| Queue and evidence | [Outbox publisher](../../backend/app/services/outbox_publisher.py) sends committed jobs with at-least-once delivery. Compose supplies PostgreSQL, workers, and Floci SQS/S3. The scope assigns S3 evaluation exports. |
| Language model | [Chat loop](../../backend/app/agent/chat_loop.py) uses `LLMProvider`, typed tools, eight model turns, and three planner revisions. Real Bedrock evidence comes from the archived benchmark. |
| Plaid Sandbox | The scope permits Sandbox only, with no real accounts. D4 remains paused; this archive supplies no Sandbox run. |
| Instacart development shopping links | The scope defines development link handoff. The [browser record](../GROCERY_VERIFICATION_PLAN.md) uses fixture responses. A link does not verify prices, stock, checkout, or purchases. Live development evidence remains pending. |

Source inspection describes behavior and design. It does not prove that a provider or deployed service works.
The local runtime uses one server-selected demo user with shared context.
Private hosting for the owner and invited users remains a source design, without deployment evidence.
Legacy data remains retained under A4. Retired health work stays historical.

## Evidence identity and results

| Identity | Exact source |
|---|---|
| Original observation source SHA | `4b877d470258561cedd3375e38efc02362ce5f22` |
| Post-hoc scorer and corrected-gold source SHA | `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6` |
| Original evaluation manifest hash | `34888d692bee873021cbfc2478b479ed62badbc045f3c83618ad511eb720778d` |
| Corrected evaluation manifest hash | `6af7f64580e9edca91fa73ef7bf88f28615440b03c0ef635d8ed7864e682c2da` |

The [original readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json)
records one October 3, 2026 batch with Nova 2 Lite, `us.amazon.nova-2-lite-v1:0`, in `us-east-1`.
It contains 138 records: 66 real Bedrock observations, 69 deterministic fake-provider records, and three local PostgreSQL records.
Each language condition has 33 slots, with three repeats per case.

| Measure | Original | Post-hoc | Scope |
|---|---|---|---|
| Tool-enabled task quality | 17/33 (51.5%); 16 failed | 23/33 (69.7%); ten failed | Same saved observations; zero unassessed; 90% target FAIL under both gold versions. |
| No-tool task quality | 0/33 | 0/33 | 33 failed; zero unassessed. Strict output schema burdens this baseline. |
| Conservative supported claims | 98/100 (98%) | Unchanged | 98 supported plus two unknown claims; ten supported refusals excluded. Bounded 95% target PASS. |

The [post-hoc summary](../../eval/results/artifacts/posthoc-gold-20261003/summary.json)
uses the `tool_enabled` / `real_bedrock` group.
The [provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json)
records derivation at `2026-10-03T23:57:26.642449+00:00`, after access to the outputs.
Only six F04/F05 `tools` assessments change. The correction changes no scoring code or allowed outcomes.
It makes zero new inference calls. It is not a fresh live batch or an independent benchmark.
The original artifacts and results remain intact.

Read the [original benchmark record](../../wiki/phases/benchmark-20261003.md) and
[separate correction record](../../wiki/phases/posthoc-gold-20261003.md) before citing results.
Release remains unverified. Purchase attempts are unmeasured.

## Figures, failures, and provenance

| Supplied artifact | Use |
|---|---|
| Figure [PNG](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.png), [SVG](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.svg), [PDF](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.pdf) | Compare original and post-hoc task quality while retaining bounded claim scope. |
| [Figure data](../../eval/results/artifacts/course-evidence-20261003/figure-data.json) and [reproducer](../../eval/results/artifacts/course-evidence-20261003/figures.py) | Trace counts and source revisions. The script exports the three figure formats. |
| [Failure examples](../../eval/results/artifacts/course-evidence-20261003/failure-examples.json) | Inspect exact case, repeat, condition, and assessment fields. Categories are coordinator triage. |
| [Course artifact manifest](../../eval/results/artifacts/course-evidence-20261003/artifact-manifest.json) | Trace file hashes and recorded figure provenance. |
| [Original scenarios](../../eval/results/artifacts/benchmark-20261003/scenarios.json) | Separate expected values from observed outputs. |

The figure manifest names `matplotlib==3.10.8`. The writer has not run the reproducer or verified artifact hashes.
The coordinator verifies artifacts and links. A separate Codex or Grok reviewer verifies the pack independently.
Evidence tables MUST retain the source revision, date, evidence class, scope, denominator, and artifact citation.
Authors MUST separate deterministic, local emulator, Sandbox, live-provider, and deployed evidence.
This pack supplies no new live batch, hosted demo, or deployment claim.
