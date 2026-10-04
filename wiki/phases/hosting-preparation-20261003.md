# Invitation-only hosting preparation

- Record date: 2026-10-03 (America/New_York).
- Access decision: [0019 — Invitation-only hosted demo](../decisions/0019-invitation-only-hosting.md), accepted.
- Source snapshot: `2026-10-04T01:18:06.107436+00:00` UTC.
- Usage snapshot: `2026-10-04T01:18:06.110352+00:00` UTC.
- Observed main: `8bfd4b80c71bca85cb1245446d933f965b17b86a`.
- State: open PR source; this run performed no merges or deployment.

This record is a bounded source checkpoint. Additional work continues beyond this snapshot.
The UTC captures fall on October 3 in America/New_York.
Saved PR heads, bases, and CI states describe the query time only.
They are not a continuous monitor or a claim about current GitHub state.

## Accepted access and product scope

The owner and invited users share one server-selected demo context.
The hosted demo MUST NOT allow public signup.
Cognito authentication does not give invited users private application accounts.
The proposed edge authenticates HTTPS access with administrator-created Cognito users.
Private ECS tasks use narrow roles and separate administrator/application secrets.
Retained RDS PostgreSQL uses isolated subnets and verified TLS.
The owner MUST confirm every mutating AWS step first, including users and invitations.
No AWS resources, users, or invitations have been created by this run.
No merge authorization exists.

The local product uses React and TypeScript chat, FastAPI, PostgreSQL, a worker, and Floci SQS/S3.
Real Bedrock calls go through `LLMProvider`.
Manual budgets remain the default. Proposed demo defaults are USD 100 monthly and a USD 40 plan cap.
The accepted catalog contains 40 meals, with 1-3 meals per request and 1-8 servings per meal.
Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Plaid Sandbox work stays paused. Live Instacart stays parked.
Instacart development shopping links prove handoff only; they do not verify retailer prices or availability.
Retired health and activity planning remains historical.
[Decision 0018](../decisions/0018-retain-legacy-data.md) retains existing records without data deletion.

## Published source at the saved query

The [source-status artifact](../artifacts/hosting-preparation-20261003/source-status.json) supplies every row below.
CI counts are saved `SUCCESS` states; the writer did not query GitHub.
The artifact records these PRs as open. It does not prove that their stacks are merged.
Local gates and independent-review verdicts are not supplied in this artifact.
Measured writer/review usage does not establish review approval.

| Source publication | Observed head SHA | Observed base branch | Observed CI |
|---|---|---|---|
| [#325](https://github.com/emanuelGitCodes/fewia/pull/325) — Record decision 0018 to retain legacy data | `36843e7e2d01590c29ad3655691c6bfbc161ae58` | `claude/backlog-status-20261003` | 7 SUCCESS |
| [#340](https://github.com/emanuelGitCodes/fewia/pull/340) — Add a task-role SQS sender for future hosting | `345acfc1dc4e094812366a0faef9fe092fb728f5` | `main` | 7 SUCCESS |
| [#342](https://github.com/emanuelGitCodes/fewia/pull/342) — Add a task-role SQS consumer for future hosting | `13b0ae290091406d7a68f7ad38b5ec23e1909d48` | `codex/backlog-resume-aws-sender` | 7 SUCCESS |
| [#343](https://github.com/emanuelGitCodes/fewia/pull/343) — Add a task-role S3 report adapter for future hosting | `5eceecebebc2885bf537aef7b499e49f552b0861` | `codex/backlog-resume-aws-consumer` | 7 SUCCESS |
| [#344](https://github.com/emanuelGitCodes/fewia/pull/344) — Define private queues and artifact storage for hosting | `1068f642d3b039ff1cc880797d1af03bb2e47d94` | `codex/backlog-resume-gate-cache` | 7 SUCCESS |
| [#345](https://github.com/emanuelGitCodes/fewia/pull/345) — Gate and audit the hosting CDK project | `bac57e53606147dd49c0ec2dceeaec1dfde0c407` | `codex/backlog-resume-hosting-resources` | 8 SUCCESS |
| [#347](https://github.com/emanuelGitCodes/fewia/pull/347) — Add an explicit service-free database bootstrap command | `a5f44e05a8ba1dbcb12182a53696b27a8f694f8b` | `main` | 7 SUCCESS |
| [#348](https://github.com/emanuelGitCodes/fewia/pull/348) — Align follow-up tool gold with final-turn scoring | `e63d68f62cf8ae70dfd60d919bcc04f1d135c8a6` | `codex/backlog-resume-cli` | 7 SUCCESS |
| [#349](https://github.com/emanuelGitCodes/fewia/pull/349) — Record the fixture and live benchmark evidence | `dde72370811523c5d8d118ced60f3a85dfc3d6e7` | `codex/backlog-resume-cli` | 7 SUCCESS |
| [#350](https://github.com/emanuelGitCodes/fewia/pull/350) — Validate local and task-role job transport settings | `535f29e6bbf34679c7fc0fe7e340d31b741155cf` | `codex/backlog-resume-aws-artifacts` | 7 SUCCESS |
| [#351](https://github.com/emanuelGitCodes/fewia/pull/351) — Select job providers from validated transport settings | `f4f9daa147aacdcce87c157dc5e59e42c95da609` | `codex/backlog-resume-transport-settings` | 7 SUCCESS |
| [#352](https://github.com/emanuelGitCodes/fewia/pull/352) — Define isolated hosting subnets and restricted network rules | `dde56e843fecb4b182c330bcaf136a09ed7d9631` | `codex/backlog-resume-hosting-gates` | 8 SUCCESS |
| [#353](https://github.com/emanuelGitCodes/fewia/pull/353) — Preserve the separate post-hoc gold rescore | `07bec2dc32b19b21197a8058279781815bbcb4cd` | `codex/backlog-resume-benchmark-evidence` | 7 SUCCESS |
| [#354](https://github.com/emanuelGitCodes/fewia/pull/354) — Define retained private PostgreSQL and separate credentials | `108f0cc0a3946e8cc7c87ed061089d749cfc3a8d` | `codex/backlog-resume-hosting-network` | 8 SUCCESS |
| [#355](https://github.com/emanuelGitCodes/fewia/pull/355) — Route the worker through validated local or AWS transport | `81108b5cf96a04ae9b3ceb23964d6359179fdf8a` | `codex/backlog-resume-transport-factory` | 7 SUCCESS |
| [#356](https://github.com/emanuelGitCodes/fewia/pull/356) — Define retained container repositories and task logs | `f6f9b160e556691904980947f7cd118f287710aa` | `codex/backlog-resume-hosting-database` | 8 SUCCESS |
| [#357](https://github.com/emanuelGitCodes/fewia/pull/357) — Route bounded job commands through validated transport | `2d0d577f67121c94d58d60114ba1e0464397853b` | `codex/backlog-resume-worker-transport` | 7 SUCCESS |
| [#358](https://github.com/emanuelGitCodes/fewia/pull/358) — Scope ECS image, log and secret execution permissions | `98c21db1e8b7c1d31521607d0078213b1095ace8` | `codex/backlog-resume-hosting-assets` | 8 SUCCESS |
| [#359](https://github.com/emanuelGitCodes/fewia/pull/359) — Build cloud database URLs with verified TLS | `0c38e1c0665587fba93f230cdb1e527f206cc7aa` | `codex/backlog-resume-bootstrap-database` | 7 SUCCESS |
| [#360](https://github.com/emanuelGitCodes/fewia/pull/360) — Validate nginx upstreams for Compose and ECS task networking | `16714fb2910777e132af3c00d58eafa747a9af24` | `codex/backlog-resume-consent` | 7 SUCCESS |
| [#361](https://github.com/emanuelGitCodes/fewia/pull/361) — Prepare the author-owned course evidence pack | `484caf434084f7d9c5995c0bac1165ee7034e85c` | `codex/backlog-resume-posthoc-evidence` | 7 SUCCESS |

All publications named in the assignment are included in the saved query.
Later publications reported by the coordinator MUST be labeled coordinator-reported.
Their CI stays unknown unless a separate artifact records it.
The writer MUST NOT carry this snapshot's CI result onto a newer head.

## Merge-order groups for coordinator review

These groups name the parents recorded in the source artifact.
They describe source dependencies, not merge authorization.
The coordinator MUST verify the current heads, review results, and CI before requesting merge authorization.
The coordinator MUST NOT bypass review or CI.

| Group | Parent and child order at the snapshot |
|---|---|
| Backend transport | `main` → #340 (`codex/backlog-resume-aws-sender`) → #342 (`codex/backlog-resume-aws-consumer`) → #343 (`codex/backlog-resume-aws-artifacts`) → #350 (`codex/backlog-resume-transport-settings`) → #351 (`codex/backlog-resume-transport-factory`) → #355 (`codex/backlog-resume-worker-transport`) → #357 (`codex/backlog-resume-bounded-job-transport`). |
| Bootstrap and TLS | `main` → #347 (`codex/backlog-resume-bootstrap-database`) → #359 (`codex/backlog-resume-cloud-database-settings`). Application-role bootstrap and cloud integration remain open. |
| Frontend | `main` → #323 (`codex/backlog-resume-c4`) → #327 (`codex/backlog-resume-consent`) → #360 (`codex/backlog-resume-nginx-upstream`). Handoff evidence remains fixture-only. |
| Hosting infrastructure | `main` → #337 (`codex/backlog-resume-gate-cache`) → #344 (`codex/backlog-resume-hosting-resources`) → #345 (`codex/backlog-resume-hosting-gates`) → #352 (`codex/backlog-resume-hosting-network`) → #354 (`codex/backlog-resume-hosting-database`) → #356 (`codex/backlog-resume-hosting-assets`) → #358 (`codex/backlog-resume-hosting-execution-roles`). Runtime roles and identity are unpublished checkpoints. |
| Evidence documents | #349 bases on `codex/backlog-resume-cli` (#341). #353 bases on `codex/backlog-resume-benchmark-evidence` (#349). #361 bases on `codex/backlog-resume-posthoc-evidence` (#353). |
| Retention | #325 bases on `claude/backlog-status-20261003`. The saved query does not include that parent's PR identity or head. |

## Evidence classes and validation limits

| Evidence | What this record establishes | Limit |
|---|---|---|
| Published source | Saved PR URLs, head SHAs, parent branches, and source scope. | Publication is separate from review, merge, or deployment. |
| Local checks | Historical checks in earlier wiki records retain their original scope. | No new local gates run by this writer; the hosting artifacts supply no gate output. |
| Independent review | Coordinator review remains a separate validation step. | No hosting review verdict is supplied here; CLI usage is not approval. |
| CI | The source table records successful checks at the saved heads and query time. | No later-head or current-state CI claim. |
| Deterministic/local emulator | Existing local stack uses fixtures, PostgreSQL, and Floci SQS/S3. | Local transport checks do not prove AWS deployment or live model quality. |
| Sandbox | Plaid Sandbox adapter/source remains distinct from real financial data. | D4 stays paused; this snapshot supplies no Sandbox execution proof. |
| Live provider | Original benchmark includes saved real Bedrock observations. | No new batch; no live Instacart or hosted access-control proof. |
| Merged | Saved main remains the SHA above; named publications are open in the artifact. | This run merges nothing. |
| Deployed | None supplied. | No AWS resources, users, invitations, or live hosted chat created by this run. |

The [original benchmark](benchmark-20261003.md) retains 17/33 task passes (51.5%).
The [post-hoc correction](posthoc-gold-20261003.md) reports 23/33 (69.7%) from the same saved observations.
The 90% task target fails under both. Claims remain 98/100 (98%) within the bounded public-output scope.
No-tool task quality remains 0/33. Purchase attempts remain unmeasured.
The correction changes six F04/F05 tool assessments; it is not an independent benchmark or model retest.
Sample, synthetic, and sandbox evidence MUST NOT become verified retailer, financial, or population claims.
Paper evidence tables MUST retain revision, timestamp, class, scope, denominator, and artifact citation.
The [course pack](../../docs/course/README.md), published in #361, supports the author's own work.
The author still writes the final paper within eight pages in two columns and records/submits the video.
Immutable course sources remain unchanged.

## Measured CLI loop snapshot

The [CLI usage artifact](../artifacts/hosting-preparation-20261003/cli-usage.json) measures supervisor writer and review records with `resume-` prefixes.
The table preserves the artifact's item identities and recorded runs.
Published items have bounded source records; usage for active items is partial.
This documentation item is not included in the saved totals.

| Item | Snapshot scope | Runs | Input tokens | Output tokens | Cached subset | Reasoning subset | Process duration (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| `resume-b5-values` | recorded source item | 5 | 639413 | 15700 | 534528 | 7974 | 524859 |
| `resume-c4` | recorded source item | 3 | 749071 | 11421 | 615424 | 5151 | 322015 |
| `resume-writer-protocol` | recorded source item | 1 | 167305 | 4390 | 142848 | 2903 | 87261 |
| `resume-a4` | recorded source item | 3 | 490204 | 7281 | 403328 | 3329 | 184185 |
| `resume-b6` | recorded source item | 3 | 716136 | 9339 | 609152 | 4544 | 299357 |
| `resume-protocol` | recorded source item | 4 | 421773 | 5719 | 332672 | 2849 | 177218 |
| `resume-b5-data` | recorded source item | 7 | 1614420 | 29578 | 1350656 | 9394 | 1032435 |
| `resume-b4-consent` | recorded source item | 2 | 802872 | 13647 | 713472 | 5471 | 486991 |
| `resume-report-sections` | recorded source item | 4 | 1000762 | 24138 | 834560 | 11574 | 836588 |
| `resume-manifest-check` | recorded source item | 5 | 591011 | 19634 | 482688 | 10705 | 626551 |
| `resume-runtime` | recorded source item | 3 | 742419 | 15063 | 634496 | 6812 | 457141 |
| `resume-records` | recorded source item | 3 | 3075256 | 57203 | 2885376 | 33122 | 1623847 |
| `resume-dispatch` | recorded source item | 3 | 1339615 | 24058 | 1166976 | 8151 | 706720 |
| `resume-report-telemetry` | recorded source item | 3 | 1009547 | 22066 | 884608 | 10121 | 728619 |
| `resume-batch` | recorded source item | 5 | 1334861 | 34946 | 1108096 | 18271 | 989744 |
| `resume-pilot` | recorded source item | 2 | 893462 | 15289 | 811008 | 9224 | 334171 |
| `resume-render-report` | recorded source item | 3 | 1017427 | 20958 | 902400 | 7486 | 717652 |
| `resume-cli-config` | recorded source item | 3 | 777477 | 17326 | 663936 | 6858 | 596015 |
| `resume-gate-cache` | recorded source item | 2 | 630002 | 14897 | 539264 | 5787 | 444597 |
| `resume-aws-sender` | recorded source item | 2 | 878161 | 11356 | 741376 | 3477 | 364767 |
| `resume-cli` | recorded source item | 3 | 1329520 | 20224 | 1176704 | 8606 | 605422 |
| `resume-aws-consumer` | recorded source item | 3 | 655381 | 13015 | 575744 | 3639 | 444288 |
| `resume-hosting-resources` | recorded source item | 4 | 854235 | 14860 | 711296 | 4164 | 515346 |
| `resume-aws-artifacts` | recorded source item | 2 | 376858 | 11901 | 316032 | 3616 | 354410 |
| `resume-bootstrap-database` | recorded source item | 3 | 636544 | 18466 | 556032 | 8649 | 577315 |
| `resume-hosting-gates` | recorded source item | 2 | 504645 | 7761 | 430976 | 2279 | 250015 |
| `resume-benchmark-docs` | recorded source item | 3 | 2266977 | 28118 | 2051200 | 5723 | 959454 |
| `resume-tool-gold` | recorded source item | 2 | 552514 | 6316 | 473472 | 1808 | 223913 |
| `resume-role-catalog` | recorded source item | 2 | 1114711 | 22384 | 1026432 | 15706 | 669893 |
| `resume-transport-settings` | recorded source item | 4 | 779078 | 16400 | 661760 | 6265 | 564196 |
| `resume-transport-factory` | recorded source item | 3 | 567420 | 9111 | 476416 | 2834 | 329430 |
| `resume-hosting-network` | recorded source item | 4 | 824597 | 18026 | 691200 | 8253 | 665321 |
| `resume-posthoc-evidence` | recorded source item | 4 | 1839398 | 20423 | 1661312 | 4316 | 691952 |
| `resume-hosting-database` | recorded source item | 3 | 484137 | 10992 | 383616 | 3966 | 388973 |
| `resume-worker-transport` | recorded source item | 2 | 719248 | 15865 | 626176 | 5444 | 536640 |
| `resume-hosting-assets` | recorded source item | 3 | 421919 | 8993 | 359680 | 3463 | 293085 |
| `resume-bounded-job-transport` | recorded source item | 3 | 762778 | 18421 | 650880 | 4845 | 571778 |
| `resume-course-evidence` | recorded source item | 5 | 2162996 | 25875 | 1942016 | 5277 | 805760 |
| `resume-hosting-execution-roles` | recorded source item | 3 | 543365 | 11582 | 467840 | 3566 | 381271 |
| `resume-nginx-upstream` | recorded source item | 2 | 311754 | 5514 | 267776 | 1637 | 178880 |
| `resume-cloud-database-settings` | recorded source item | 3 | 582164 | 13827 | 487296 | 5429 | 455234 |
| `resume-hosting-task-roles` | active; partial | 2 | 399874 | 9283 | 332928 | 2956 | 301147 |
| `resume-cloud-database-integration` | active; partial | 2 | 287320 | 8592 | 232960 | 3561 | 264546 |
| `resume-hosting-identity` | active; partial | 2 | 422966 | 10601 | 376832 | 3121 | 338881 |
| `resume-hosting-task-settings` | active; partial | 1 | 233946 | 7263 | 205696 | 1757 | 237929 |
| Loop total, including active partial items | bounded snapshot | 136 | 38525539 | 727822 | 33499136 | 294083 | 23145812 |

All 136 recorded runs have known CLI usage; `unknown_usage_runs` is zero.
Input plus output totals 39,253,361 tokens.
Cached counts are a subset of input. Reasoning counts are a subset of output.
The coordinator MUST NOT add these subsets again.
Native-agent token counts are unknown (`null`), not zero.
The recorded process duration is 23,145,812 ms across CLI processes.
Processes can overlap. This sum is not total loop wall time.
The snapshot supports no savings percentage, causal efficiency claim, or like-for-like speed comparison.
`resume-protocol` and `resume-writer-protocol` remain separate artifact keys.
The earlier tier S pilot has a different scope; its historical log entry remains unchanged.

## Work still in progress

| Work | Status and missing evidence |
|---|---|
| Runtime roles | Coordinator-reported source checkpoint `573dd0b`; publication and independent review pending. CI unknown. No deployed permissions proof. |
| Identity | Coordinator-reported source checkpoint `14dd9e41`; publication and independent review pending. CI unknown. No Cognito users or invitations created. |
| ECS deployment composition | Task definitions, services, listeners, and stack composition remain in progress. |
| Database application role | Application-role bootstrap and cloud integration remain in progress. Separate secrets and verified TLS need runtime evidence. |
| Deployment procedure | Deployment runbook and preflight remain in progress. |
| Owner inputs | Hostname, ACM certificate, and deployment credentials pending. No values invented or credentials recorded. |
| Live demo | Authenticated hosted access, restricted network paths, and one deployed live Bedrock chat turn remain unverified. |
| Review and publication | Coordinator validates this record; a separate Codex or Grok agent independently reviews it. No merge authority exists. |

The owner MUST confirm every mutating AWS step before execution.
Additional source work continues beyond this bounded checkpoint.

## Later status on 2026-10-04

This section is a later checkpoint. The tables and CI counts above stay the 2026-10-03 snapshot.

The [final record](backlog-final-20261003.md) dated 2026-10-04 lists created pull requests #322-#381 as unmerged.
Observed main remains `8bfd4b80c71bca85cb1245446d933f965b17b86a`.
Runtime roles are published in #362 at `573dd0b4a21b38b73d19e4b70482686854299b46`.
Identity is published in #364 at `14dd9e41aaa2b16aca3562d7227f1c5f063e9f2a`.
Preflight CLI is published in #380 at `7b2e370d081e9c79e80fd41863708a3735fddfe5`.
The runbook is published in #381 at `d43d606df795a6a6e748fdc9263554349867ae9c`.
D5 source, preflight, and runbook publication is complete in that later record.
Live deployment still awaits owner inputs and confirmations.
No merge or deployed health is recorded here.
