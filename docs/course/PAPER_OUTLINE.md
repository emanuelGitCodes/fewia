# Paper planning prompts

The author writes every paper section in their own words.
These questions and evidence maps support that work. They are not text for submission.
The [course transcript](../CAP6938%20August%2025.txt), lines 80-110 and 250-278,
sets a maximum of eight pages, two columns, code, and a video.
It asks authors not to generate the report from scratch with ChatGPT.
The author MUST preserve that boundary.

## Page budget

This budget includes figures, tables, and references within eight pages.
Including references is a conservative planning assumption, not a separate claim about course rules.

| Section | Pages | Writing task |
|---|---:|---|
| Title and abstract | 0.4 | Write last. State the problem, method, observed result, and main limit. |
| Problem and scope | 0.8 | Define the current grocery task and excluded claims. |
| Architecture | 1.3 | Explain tool ownership, jobs, and provider boundaries. |
| Evaluation method | 1.5 | Explain corpus, conditions, scoring, and provenance. |
| Results | 1.3 | Present denominators and original/post-hoc columns. |
| Failures | 0.8 | Select cases with observable evidence and bounded interpretations. |
| Limitations and next work | 0.9 | State threats to validity and pending provider work. |
| References | 1.0 | Cite repository evidence and sources you have read. |
| Total | 8.0 | Maximum planning budget. |

The author MAY shorten sections. The final paper MUST stay within the course maximum.

## Section questions and evidence map

### Title and abstract

- What budget-aware grocery task did you implement?
- What does tool ownership contribute to the design?
- Which observed result and limit matter most?
- How will you label the original and post-hoc scores without implying a new model run?

Evidence: [project scope](../../.codex/project-context.md),
[original readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json),
and [post-hoc provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json).
Draft no abstract until you have selected claims and inspected their evidence.

### Problem and scope

- Who uses the local demo, and which budget facts does the user supply?
- How do monthly limits, posted spending, pending spending, and plan caps differ?
- Why do sample prices constrain any affordability claim?
- How do the accepted 40 meals, 1-3 meals per request, and 1-8 servings bound the task?
- Which health and activity goals belong only to the earlier project?

Evidence: [scope](../../.codex/project-context.md),
[catalog decision 0017](../../wiki/decisions/0017-forty-meal-catalog.md),
and [backlog](../FEATURE_BACKLOG.md), including A4's legacy-data retention.
Keep immutable course sources in their original context.

Every grocery estimate MUST carry the exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

### Architecture

- Which steps belong to React and TypeScript, FastAPI, PostgreSQL, the worker, and Floci SQS/S3?
- How does the committed outbox reach the queue? What follows from at-least-once delivery?
- Where does `LLMProvider` interpret language, and where do tools validate arithmetic and constraints?
- How do eight model turns and three planner revisions bound a job?
- What does the evidence revision identify? What does shared demo-user context fail to establish?
- Which provider paths have live evidence, and which remain design or fixture evidence?

Evidence: [App](../../frontend/src/App.tsx), [Compose](../../compose.yaml),
[chat loop](../../backend/app/agent/chat_loop.py),
[agent handler](../../backend/app/services/agent_jobs.py),
[plan job](../../backend/app/services/plan_job.py), and
[outbox publisher](../../backend/app/services/outbox_publisher.py).
The [scope](../../.codex/project-context.md) identifies S3 exports, Plaid Sandbox, and Instacart development shopping links.
The [browser record](../GROCERY_VERIFICATION_PLAN.md) bounds fixture handoff evidence.

### Evaluation method

- How do 90 primary, 33 no-tool, and 15 structured-reference slots form the 138-record matrix?
- Why are only 66 records real Bedrock observations, with 33 language slots per condition?
- What does repeating a small fixed corpus three times measure?
- Which model, region, settings, prompt/catalog identity, and source revision were frozen?
- Which checks score final plans, final-turn tools, public claims, and observable outcomes?
- How does strict JSON output burden the no-tool baseline?
- Why does the deterministic reference test structured requests rather than language interpretation?
- When did the gold correction occur, and which six assessments changed?

Evidence: [original scenarios](../../eval/results/artifacts/benchmark-20261003/scenarios.json),
[benchmark record](../../wiki/phases/benchmark-20261003.md),
[readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json),
[post-hoc record](../../wiki/phases/posthoc-gold-20261003.md), and
[provenance](../../eval/results/artifacts/posthoc-gold-20261003/provenance.json).

Retain both exact source SHAs:

- Original observations: `4b877d470258561cedd3375e38efc02362ce5f22`.
- Post-hoc scorer and corrected gold: `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6`.

The correction followed access to the outputs. It uses the same saved observations with zero new inference calls.
It changes no scoring code or allowed outcomes. Preserve the original result beside the correction.

### Results

- How will you present 17/33 original task passes beside 23/33 post-hoc passes and 0/33 no-tool passes?
- How will you explain that both tool-enabled scores fail the 90% target?
- Why is 98/(98 assessed + two unknown) a bounded claim-support result?
- Why do ten supported refusals stay outside that denominator?
- How do call counts differ from slot assessment counts?
- What can six accepted plans with zero tested violations establish?
- Why do latency summaries retain failed attempts? Why is model token cost not an AWS bill?

Evidence: `real_tool_enabled`, `baseline_no_tool`, `telemetry_groups`, and `cost` in the
[readout](../../eval/results/artifacts/benchmark-20261003/benchmark-readout.json).
For corrected quality, select `groups` with `condition=tool_enabled` and `evidence_class=real_bedrock` in the
[summary](../../eval/results/artifacts/posthoc-gold-20261003/summary.json), then read `metrics.quality`.
The [benchmark record](../../wiki/phases/benchmark-20261003.md) records scope, percentiles, and dated pricing provenance.

Use the supplied figure: [PNG](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.png),
[SVG](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.svg), or
[PDF](../../eval/results/artifacts/course-evidence-20261003/benchmark-quality.pdf).
Trace it through [figure data](../../eval/results/artifacts/course-evidence-20261003/figure-data.json),
[reproducer](../../eval/results/artifacts/course-evidence-20261003/figures.py), and
[manifest](../../eval/results/artifacts/course-evidence-20261003/artifact-manifest.json).
Write your own caption with the date, both revisions, denominators, and post-hoc timing.
The author MUST NOT describe the correction as a new live batch or claim support as general factual accuracy.

### Failures

- Which final output is absent in F02, and which checks depend on its presence?
- How can X03 wording fail an incomplete lexical outcome classifier?
- Why is an unknown claim different from a proven false claim?
- What is missing from A01's structured rejection and A02's tool/outcome evidence?
- Which failures belong to the no-tool schema contract?
- Why do F04/F05 original failures require a gold-contract explanation?

Evidence: [failure log](FAILURE_LOG.md),
[selected JSON examples](../../eval/results/artifacts/course-evidence-20261003/failure-examples.json),
and [post-hoc record](../../wiki/phases/posthoc-gold-20261003.md).
Use exact case, repeat, condition, selector, and assessment fields.
These categories are root triage, not proven root causes.

### Limitations and next work

- Which findings apply only to this fixed corpus and the tested constraints?
- Which comparison claims fail because the correction is post-hoc or the baseline format differs?
- Why do 48 synthetic-sentinel turns fail to prove unrestricted secret safety?
- Why are purchase attempts unmeasured despite A04 refusal checks?
- Which sample price, nutrition, provider, shared-user, and hosting limits bind the conclusions?
- Which remaining tasks belong to the author, D4, and D5?

Evidence: [limitations](LIMITATIONS.md),
[benchmark record](../../wiki/phases/benchmark-20261003.md),
[post-hoc record](../../wiki/phases/posthoc-gold-20261003.md), and [backlog](../FEATURE_BACKLOG.md).
No population confidence claim or causal conclusion follows from these observations.

### References

- Which sources did you inspect before making each claim?
- Can a reader locate each figure, denominator, failure selector, and source revision?
- Does each table identify its evidence class and distinguish expectations from observations?

Use the [pack source map](README.md), [course transcript](../CAP6938%20August%2025.txt),
and [artifact manifest](../../eval/results/artifacts/course-evidence-20261003/artifact-manifest.json).
Repository artifacts support implementation and evaluation claims.
They do not replace related-work sources that the author reads and cites.
The author MUST NOT invent citations or treat synthetic data as verified retailer, financial, or population evidence.
