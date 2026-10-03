# Evaluation draft publication and Graphify update

Publication facts were captured at `2026-10-03T07:21:57Z`. The 41 published pull requests are drafts. No pull request merged to `main`.

## Merge order

The proposed order starts with CI prerequisite #291, then #251 through #287 in numeric order. This record does not authorize a merge. Each recorded source slice adds at most 150 lines. The `Lines` column records the source count.

| Order | Draft pull request | Lines |
|---:|---|---:|
| 1 | [#291 — CI database-name prerequisite](https://github.com/emanuelGitCodes/fewia/pull/291) | 5 |
| 2 | [#251 — Reproducible evaluation manifest](https://github.com/emanuelGitCodes/fewia/pull/251) | 135 |
| 3 | [#252 — Validated evaluation inputs](https://github.com/emanuelGitCodes/fewia/pull/252) | 126 |
| 4 | [#253 — Local evaluation evidence](https://github.com/emanuelGitCodes/fewia/pull/253) | 125 |
| 5 | [#254 — Evaluation result validation](https://github.com/emanuelGitCodes/fewia/pull/254) | 79 |
| 6 | [#255 — Bounded outcome propositions](https://github.com/emanuelGitCodes/fewia/pull/255) | 64 |
| 7 | [#256 — Observed plan schema](https://github.com/emanuelGitCodes/fewia/pull/256) | 64 |
| 8 | [#257 — Evaluation fault provider](https://github.com/emanuelGitCodes/fewia/pull/257) | 54 |
| 9 | [#258 — Independent plan arithmetic checks](https://github.com/emanuelGitCodes/fewia/pull/258) | 110 |
| 10 | [#259 — Observed adversarial context](https://github.com/emanuelGitCodes/fewia/pull/259) | 130 |
| 11 | [#260 — Isolated evaluation databases](https://github.com/emanuelGitCodes/fewia/pull/260) | 147 |
| 12 | [#261 — Controlled protocol evaluation](https://github.com/emanuelGitCodes/fewia/pull/261) | 135 |
| 13 | [#262 — No-tool response contract](https://github.com/emanuelGitCodes/fewia/pull/262) | 147 |
| 14 | [#263 — Structured plan reference](https://github.com/emanuelGitCodes/fewia/pull/263) | 113 |
| 15 | [#264 — Refresh failure fixtures](https://github.com/emanuelGitCodes/fewia/pull/264) | 138 |
| 16 | [#265 — Evaluation matrix preparation](https://github.com/emanuelGitCodes/fewia/pull/265) | 149 |
| 17 | [#266 — Safe evaluation JSON files](https://github.com/emanuelGitCodes/fewia/pull/266) | 107 |
| 18 | [#267 — Handoff failure evaluation](https://github.com/emanuelGitCodes/fewia/pull/267) | 150 |
| 19 | [#268 — Stale refresh evaluation](https://github.com/emanuelGitCodes/fewia/pull/268) | 149 |
| 20 | [#269 — Bounded public claim parser](https://github.com/emanuelGitCodes/fewia/pull/269) | 111 |
| 21 | [#270 — Captured evaluation telemetry](https://github.com/emanuelGitCodes/fewia/pull/270) | 146 |
| 22 | [#271 — Durable evaluation output](https://github.com/emanuelGitCodes/fewia/pull/271) | 147 |
| 23 | [#272 — Validated evaluation rates](https://github.com/emanuelGitCodes/fewia/pull/272) | 118 |
| 24 | [#273 — Duplicate delivery handler](https://github.com/emanuelGitCodes/fewia/pull/273) | 150 |
| 25 | [#274 — Duplicate delivery evaluation](https://github.com/emanuelGitCodes/fewia/pull/274) | 149 |
| 26 | [#275 — Evaluation cost estimates](https://github.com/emanuelGitCodes/fewia/pull/275) | 118 |
| 27 | [#276 — Strict evaluation metric counters](https://github.com/emanuelGitCodes/fewia/pull/276) | 89 |
| 28 | [#277 — Final plan scoring](https://github.com/emanuelGitCodes/fewia/pull/277) | 150 |
| 29 | [#278 — Bounded public claim scoring](https://github.com/emanuelGitCodes/fewia/pull/278) | 149 |
| 30 | [#279 — Summary check validation](https://github.com/emanuelGitCodes/fewia/pull/279) | 56 |
| 31 | [#280 — Bounded Markdown formatting helpers](https://github.com/emanuelGitCodes/fewia/pull/280) | 120 |
| 32 | [#281 — Evaluation assessment classification](https://github.com/emanuelGitCodes/fewia/pull/281) | 150 |
| 33 | [#282 — Evaluation metric summaries](https://github.com/emanuelGitCodes/fewia/pull/282) | 150 |
| 34 | [#283 — Strict task outcomes](https://github.com/emanuelGitCodes/fewia/pull/283) | 121 |
| 35 | [#284 — Required PostgreSQL evaluation gates](https://github.com/emanuelGitCodes/fewia/pull/284) | 0 |
| 36 | [#285 — Task completion rates](https://github.com/emanuelGitCodes/fewia/pull/285) | 47 |
| 37 | [#286 — Evaluation summary assembly](https://github.com/emanuelGitCodes/fewia/pull/286) | 65 |
| 38 | [#287 — Evaluation checkpoint documentation](https://github.com/emanuelGitCodes/fewia/pull/287) | 0 |

## CI and local gates

The confirmed CI failure was the evaluation database-name guard rejecting `/fewia`. Approved source `811e41022fe4b7ec6738aa58db47f9124c20a29f` sets `fewia_eval` in all three URLs, the service database, and the health check.

The remote check snapshot at `2026-10-03T07:21:57Z` had mixed states. Pull request #291 had seven queued checks. Other checks included `SUCCESS`, `QUEUED`, and `IN_PROGRESS`. This snapshot does not show that all remote CI passed.
The newer snapshot at `2026-10-03T07:27:08.822532+00:00` records every current check as passed across all 41 published draft pull requests.

Current local gates passed on integrated source `8dfdb50f324310f18ba2870b8807a5511af40096` at `2026-10-03T07:17:53Z`:

| Gate | Result |
|---|---|
| Ruff check | PASS — All checks passed! |
| Ruff format | PASS — 262 files already formatted |
| Mypy | PASS — Success: no issues found in 130 source files |
| Pytest | PASS — 6055 passed, 1 warning in 11.80s |

These local gates and the timestamped remote snapshot are separate evidence.

## Held drafts

These drafts are outside the approved stack. Each needs repair and independent approval. Additional review-round approval remains pending.

- [#288 — Tool-call matching](https://github.com/emanuelGitCodes/fewia/pull/288): require one-to-one matching so an incorrect early call cannot consume the expected call.
- [#289 — Incomplete leakage scan](https://github.com/emanuelGitCodes/fewia/pull/289): an incomplete scan cannot certify that no leak occurred.
- [#290 — Refusal semantics](https://github.com/emanuelGitCodes/fewia/pull/290): allow harmless registered reads and grade unnecessary calls separately.

Publication does not authorize main merges or feature repairs. No pull request merged to `main`. The complete batch/CLI and full benchmark remain incomplete.

## Graphify update

Graphify processed source `8dfdb50f324310f18ba2870b8807a5511af40096`: 75 files, including 70 code files and five documents. The graph has 6,185 nodes, 17,813 edges, and 315 communities. The [local graph report](../../graphify-out/GRAPH_REPORT.md) and [interactive graph](../../graphify-out/graph.html) are ignored outputs in the primary worktree. The HTML groups the graph into 315 community nodes and 710 cross-community edges. The [graph data](../../graphify-out/graph.json) and [health report](../../graphify-out/health.json) are also local ignored outputs. These files are not committed or published on GitHub.

The graph reports 15 self-loop call edges. Some are recursive. The remaining cases need source inspection. It reports zero dangling endpoints, zero missing endpoints, and zero collapsed endpoint pairs. This is a warning, not a fully clean health result.

The graph covers the code and checkpoint snapshot before this publication-only documentation change. It does not index this page. Native semantic-agent usage is unavailable, so no token cost is reported. Deterministic AST extraction uses no model calls.

## Evidence limits

The full benchmark did not run. No pull request merged to `main`. This publication and the local gates do not establish live-provider, checkout, deployed, or target-certification evidence.
