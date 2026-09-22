# Grocery evaluation evidence

This directory contains saved evaluation outputs for the local grocery stack.
Use the relative paths below.

These artifacts do not prove global model quality.
They do not prove deployment.
They do not prove Plaid Sandbox access.
They do not prove live Instacart prices.

Every grocery estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

The catalog supports ten meals.
A request MAY include one to three (1-3) meals.
A meal MAY include one to eight (1-8) servings.

Writers MUST separate deterministic, sandbox, live, and deployed evidence.
Synthetic or sample data MUST NOT become verified retailer, financial, or population claims.

## Saved artifacts

| File | Role |
| --- | --- |
| [grocery-evaluation-2026-09-22.json](grocery-evaluation-2026-09-22.json) | Final mixed 90-slot batch JSON |
| [grocery-evaluation-2026-09-22.md](grocery-evaluation-2026-09-22.md) | Rendered Markdown report |

Revision: `a473bb1a6b7691a479365f9061daedfac792ce46`.
Model: `us.amazon.nova-2-lite-v1:0`.
Region: `us-east-1`.

Batch SHA256:

`828a0830820f7f056b44858d9342e8f9fabb10c39f9598aaedbfb0971de22aab`

Report SHA256:

`4b82dccb81f7eb35d90acf16e8732c7bc8ed5f8af2435a264591b45734d7b4c9`

The artifacts MUST NOT contain vendor overlay prices.
The artifacts MUST NOT contain private credentials.
The artifacts MUST NOT contain raw model reasoning.

The CLI MUST NOT overwrite these files.
Use a new output path for any rerender.

## Reproduction

Start at the repository root.
Then change into `backend`.
`--input` MUST be the saved JSON path.
`--output` MUST be a new Markdown path.
`--rates` MUST be the dated Nova 2 Lite rate file.

```bash
cd backend
mkdir -p ../artifacts/evaluation
uv run python -m app.evaluation_report \
  --input ../docs/evidence/grocery-evaluation-2026-09-22.json \
  --output ../artifacts/evaluation/grocery-evaluation-2026-09-22-rerender.md \
  --rates tests/evaluation/pricing/nova2-lite-use1-20260922.json
```

The report CLI does not call providers.
It accepts only `metrics_status` `unassessed`.
It MUST NOT certify global quality.
It MUST NOT default, fetch, or guess rates.
A model or region mismatch fails.

Commands live in [GROCERY_EVALUATION.md](../GROCERY_EVALUATION.md).

## Final batch counts

Keep this run distinct from earlier mixed runs and from the fixture-only CLI.

- 51 fixture pass
- 30 real completed
- 9 unassessed
- 0 execution failed
- 15 final-plan structural checks pass
- 15 reference comparisons pass
- Six A03/A04 refusal observations matched fixed public text with no tools
- Those refusal checks are separate from a global quality score
- P04 has three controlled passes and stays unassessed as a model target
- P05 local PostgreSQL and Floci proof is complete
- P05 evaluator batch routing stays unassessed
- A02 real provider-text injection stays pending
- Observer covers ten cases
- 30 known usage slots and 0 unknown slots
- Tokens: 195,499 in, 40,205 out
- Latency nearest-rank on summed user-turn durations: p50 8.53608062598505s, p95 16.49669574998552s
- Dated token estimate USD 0.17507842. This figure is not a bill

Earlier failed runs remain preserved in
[GROCERY_VERIFICATION_PLAN.md](../GROCERY_VERIFICATION_PLAN.md)
and
[wiki/phases/grocery-completion-20260922.md](../../wiki/phases/grocery-completion-20260922.md).

## Evidence classes

| Class | What this directory may hold |
| --- | --- |
| Deterministic | Fixture guards and planner arithmetic labels |
| Fixture | Demo spending and sample catalog prices |
| Emulator | Local Floci SQS and S3 path labels |
| Sandbox | Plaid Sandbox labels only. Live Sandbox proof is blocked by absent credentials |
| Live | Real Bedrock observations in the saved batch. Spoonacular overlay stays outside these files |
| Deployed | Nothing. Deployed AWS stays outside the local MVP |

## Pending items

- Clarification scorer
- Public-claims scorer
- Comprehensive synthetic secret-boundary audit
- A02 real provider-text injection
- P05 evaluator batch routing
- P04 as a model target
- Plaid Sandbox live proof after credentials exist outside source

Instacart stays parked per [0010](../../wiki/decisions/0010-usda-spoonacular-overlay.md).
Deployed AWS evidence stays outside the local MVP.

## Handoff

New feature work stopped for this run at 2026-09-22 09:15:18 UTC.
Review the stack in [plans/APP_COMPLETION_STACK.md](../../plans/APP_COMPLETION_STACK.md).
Review the [open pull requests](https://github.com/emanuelGitCodes/fewia/pulls).
Agents MUST NOT merge.
Agents MUST NOT push to `main`.
The results above are local. Check the linked pull requests for remote CI and publication status.
Graphify outputs are checkout-local and gitignored. Consult graphify-out/GRAPH_REPORT.md and health.json for coverage and integrity diagnostics.
