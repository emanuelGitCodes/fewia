# Backlog final record

- Record date: 2026-10-04 (America/New_York).
- Run slug: `20261003`.
- Observed main: `8bfd4b80c71bca85cb1245446d933f965b17b86a`.
- Collection time: `2026-10-04T04:38:04.659898+00:00` UTC.
- Usage capture: `2026-10-04T04:47:06.525010+00:00` UTC.
- State: 60 created pull requests remain OPEN and unmerged.
- Reference [#321](https://github.com/emanuelGitCodes/fewia/pull/321) is outside the created count.

This page records published backlog source and Graphify evidence.
It does not merge branches or certify a live hosted demo.
Exact heads, parents, gate files, and CI counts live in the
[PR registry](../artifacts/backlog-final-20261003/registry.json)
and the
[compact publication summary](../artifacts/backlog-final-20261003/publication-summary-writer.json).
The earlier [hosting snapshot](hosting-preparation-20261003.md) stays a historical 2026-10-03 record.

## Product and access boundary

The local product is React and TypeScript chat, FastAPI, PostgreSQL, a worker, and Floci SQS and S3.
Real Bedrock calls go through `LLMProvider`.
Plaid Sandbox stays paused. Live Instacart stays parked.
The accepted catalog contains 40 meals, with 1-3 meals per request and 1-8 servings per meal.
Manual budget defaults are USD 100 monthly and a USD 40 plan cap.
Application tools use USD integer cents.
[Decision 0018](../decisions/0018-retain-legacy-data.md) retains legacy records.
[Decision 0019](../decisions/0019-invitation-only-hosting.md) admits the owner and invited users only.
Invited users share one server-selected demo user. Public signup stays disabled.
Authentication does not create private per-user application isolation.
The owner MUST confirm every mutating AWS step and every invitation.
Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Created publications 322-381

This run created pull requests [#322](https://github.com/emanuelGitCodes/fewia/pull/322)
through [#381](https://github.com/emanuelGitCodes/fewia/pull/381). Count: 60.
All 60 remain unmerged. Saved main stays `8bfd4b80c71bca85cb1245446d933f965b17b86a`.
The runbook parent is `d43d606df795a6a6e748fdc9263554349867ae9c`, PR #381.

The CI snapshot records `COMPLETED_SUCCESS` for every created pull request.
Fifty heads have local gate category `PASS`.
Ten documentation heads have `NO_CHECKS_SELECTED`. Those ten records are not executed tests.
Independent review records `APPROVE` on each saved head.
Matching gate JSON lives under
[artifacts/gates](../artifacts/backlog-final-20261003/artifacts/gates/).
Matching review files live under
[artifacts/reviews](../artifacts/backlog-final-20261003/artifacts/reviews/).
Local gates, independent review, GitHub CI, merge, and deployment remain separate evidence classes.

`NO_CHECKS_SELECTED` documentation records: #325, #326, #330, #331, #346, #349, #353, #361, #366, #381.

## Merge order by stack group

These groups follow saved parents. They do not grant merge authorization.

| Group | Parent to child order |
|---|---|
| Evaluation report and CLI | `main` → #322 → #332 → #333 → #334 → #335 → #336 → #328 → #329 → #338 → #339 → #341. #348 and #349 base on #341. #353 bases on #349. #361 bases on #353. #366 bases on #361. #381 bases on #366. |
| Frontend handoff | `main` → #323 → #327 → #360. |
| Review matcher | `main` → #324. |
| Retention and documentation | Reference #321 → #325 → #326 → #330 → #331. |
| Hosting through preflight | `main` → #337 → #344 → #345 → #352 → #354 → #356 → #358 → #362 → #364 → #365 → #367 → #368 → #369 → #371 → #372 → #373 → #374 → #377 → #378 → #379 → #380. |
| AWS transport | `main` → #340 → #342 → #343 → #350 → #351 → #355 → #357. |
| Role catalog | `main` → #346. |
| Bootstrap, TLS, and application role | `main` → #347 → #359 → #363 → #370 → #375 → #376. |

## Integration evidence

The [integration summary](../artifacts/backlog-final-20261003/integration-summary.json)
describes an unmerged filesystem composition through PR #380, plus runbook PR #381.
The [verification record](../artifacts/backlog-final-20261003/integration-final-verification.json)
holds the detailed counts.

| Area | Recorded result | Limit |
|---|---|---|
| Backend | 9045 passed, 1 PostgreSQL 17-only skip on PostgreSQL 16, 1 warning; Ruff and strict mypy pass | Unmerged composition, not `main` |
| Hosting | 1775 passed; Ruff, format, and strict mypy pass; 43 files byte-identical to `7b2e370d081e9c79e80fd41863708a3735fddfe5` | Source identity only |
| Frontend | 492 tests and production build pass; 82 files unchanged in the final composition | Source reuse only |
| Tooling | 359 tests pass after a coordinator `PYTHONPATH` correction; the initial 9 collection errors stay in the record | Command repair is separate from product quality |
| Runbook | PR #381 head `d43d606df795a6a6e748fdc9263554349867ae9c`; local review `APPROVE`; gate `NO_CHECKS_SELECTED` | Documentation record |

The [runbook context summary](../artifacts/backlog-final-20261003/runbook-context-summary.json)
and [synth probe](../artifacts/backlog-final-20261003/runbook-synth-probe.json)
record an offline probe. Three phases passed with synthetic cached zones: foundation, bootstrap, and active.
Two unsafe assemblies were rejected: `unresolved_context` and `dummy_zone`.
CDK CLI version is `2.1130.0`. AWS calls: 0. Live AWS state: unknown.
Frontend, supervisor, and infra test files stay unchanged through the runbook SHA.

## Benchmark and course limits

The [original benchmark](benchmark-20261003.md) remains 17/33 task success (51.5%). The 90% target FAILS.
The [post-hoc gold correction](posthoc-gold-20261003.md) rescores the same saved observations.
Task success becomes 23/33 (69.7%). The 90% target still FAILS.
Bounded claims stay 98/100 (98%). The 95% target PASSES in that bounded scope.
No-tool task success stays 0/33. Purchase attempts remain unmeasured.
The corrected gold did not rerun the model.
D3 supporting pack is published. The final paper and video remain author work.
D4 remains paused. Live Instacart remains parked.

## D5 source status

Backlog source, evaluation, report, CLI, AWS transport, invitation-only hosting components,
bootstrap, preflight CLI, and the deployment runbook are published.
Live deployment still awaits owner account, profile, hostname, and `us-east-1` ACM certificate inputs.
Hosted authenticated Bedrock chat remains unverified.
No merge authorization exists.

Later published heads after the 2026-10-03 hosting snapshot include
#362 `573dd0b4a21b38b73d19e4b70482686854299b46`,
#364 `14dd9e41aaa2b16aca3562d7227f1c5f063e9f2a`,
preflight #380 `7b2e370d081e9c79e80fd41863708a3735fddfe5`,
and runbook #381 `d43d606df795a6a6e748fdc9263554349867ae9c`.

## Recorded repairs

These findings come from the frozen final facts. They describe repaired source, not deployed health.

- Runtime-policy CI used a fixture that failed 113 setups against exact database name `fewia_eval`. A portable guard fix passed, and CI is green on the saved head.
- An initial Sol provisioning run stalled. A same-Sol retry launched before routing correction. That recorded deviation does not change routing policy.
- Bootstrap command, environment, role, and resource override bypasses were repaired. Mutation tests recorded 167 failures.
- Unsupported submicrosecond timestamp truncation was rejected.
- CLI ECR repository length bounds were repaired. Mutation tests recorded 2 failures.
- Direct Python synthesis missed Availability Zone context, and a quoted CDK app command failed. The repaired path uses an executable CDK app, an `exec` prefix, and assembly guards.

## Graphify archive

Graphify describes a recorded unmerged filesystem composition.
It is not `main` and it is not one Git commit.
The snapshot covers published PR source 321-381, 61 components.
It excludes this final-record page and pull requests 382 and later.

| Identity | Value |
|---|---|
| Archive | [published-pr-source-composition-321-381-600cbe03008f.tar.gz](../artifacts/backlog-final-20261003/graphify/published-pr-source-composition-321-381-600cbe03008f.tar.gz) |
| Archive SHA-256 | `73581554e657c41fd1dae09badc383e1b0590e48f613275fcd62f75ebeedf08c` |
| Archive size | 795036 bytes |
| Source tree SHA-256 | `600cbe03008f4f7008dd640752378e4489de5ade64c3c6eef566adb90853eb82` |
| Source manifest SHA-256 | `03b20a93a4c998705416504be0a2c2d929c9bda027778f495f692ed1bbd08a22` |
| Report | [GRAPH_REPORT.md](../artifacts/backlog-final-20261003/graphify/GRAPH_REPORT.md) |
| Provenance | [source-provenance.json](../artifacts/backlog-final-20261003/graphify/source-provenance.json) |
| Health | [health.json](../artifacts/backlog-final-20261003/graphify/health.json) |

Supported corpus: 717 source files (544 code, 163 document, 1 paper, 9 image, 0 video).
Changed files in this Graphify update: 13 code and 2 document.
Processed AST code files: 153, with 0 AST failures.
Semantic files: 50. Manually extracted JSON examples: 3.
Graph: 8901 nodes, 26414 edges, 28 hyperedges, 433 communities.
HTML view: 433 community nodes and 1230 cross-community edges.
Health status: `ok`. Missing endpoints: 0. Dangling endpoints: 0. Duplicate edges: 0.
Quarantined false AST edges: 27 (19 new snapshot, 6 baseline, 2 tail PR376-380).
Retained verified recursive edges: 12.
Native semantic token counts are unknown.
The report labels 95% EXTRACTED and 5% INFERRED, with 1436 inferred edges.
This record does not claim that every graph relationship is independently verified.
`graph.json`, `graph.html`, `manifest.json`, and diagnostics remain inside the archive.

## Pricing inputs

The [pricing inputs](../artifacts/backlog-final-20261003/hosting-pricing-sources.json)
give an illustrative fixed list-price subtotal of USD 110.245392 for 730 hours.
This is not a quote or bill. Variable costs stay excluded.
The [runbook](../../docs/HOSTED_DEMO.md) keeps the same subtotal and official source links.

## CLI usage snapshot

The [resume CLI summary](../artifacts/backlog-final-20261003/cli-usage-resume-summary.json)
covers 209 resume CLI runs across 64 items.
Final-record writer and review work are excluded.

| Measure | Recorded value |
|---|---|
| Known input tokens | 57,504,770 |
| Known output tokens | 1,109,989 |
| Cached tokens (input subset) | 49,929,728 |
| Reasoning tokens (output subset) | 427,209 |
| Summed process time | 36,972,615 ms |
| Runs with unknown token metrics | 2 |
| Native-agent tokens | unknown |
| Coordinator tokens | unknown |
| Providers | Codex 209 |
| Models | `gpt-6-luna` 82, `gpt-6.1-sol` 127 |
| Phases | implement 61, repair 65, review 83 |
| Outcomes | completed 207, stalled 1, time_limit 1 |

Cached and reasoning counts are subsets. Elapsed sums overlap.
This snapshot supports no total cost or efficiency claim.

## Evidence classes

| Class | What this record supplies | Limit |
|---|---|---|
| Published source | Registry heads, parents, and titles for #322-#381 | Unmerged |
| Local gates | 50 `PASS` heads and 10 `NO_CHECKS_SELECTED` docs records | Not GitHub CI |
| Independent review | `APPROVE` files on saved heads | Not merge authority |
| CI | Dated `COMPLETED_SUCCESS` snapshot for all 60 created PRs | Query time only |
| Deterministic / integration | Backend, hosting, frontend, and tooling counts above | Unmerged composition |
| Sandbox | None new | D4 paused |
| Live provider | Original Bedrock benchmark observations | No new batch |
| Deployed | None | No AWS resources, users, or invitations from this run |

## Remaining work

Owner account, profile, hostname, and `us-east-1` ACM certificate remain required inputs.
The owner MUST confirm each AWS mutation and each invitation.
Merge authorization remains absent.
Temporary containers from this work stopped. The original FEWIA stack still runs.
Worktrees remain after forced removal was denied.
The coordinator verifies links, facts, the unchanged log prefix, owned paths, commits, and gates.
Independent review remains a separate Codex or Grok agent.
