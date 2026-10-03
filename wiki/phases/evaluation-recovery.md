# Evaluation recovery checkpoint

The archive was captured at `2026-10-03T13:55:52.234401Z`. It records the
published source, current integration, gates, reviews, probes, and Graphify
summary. See the [recovery manifest](../artifacts/evaluation-recovery-20261003/manifest.json).

## Main and integration source

Verified `main` at `5e5cdc9c06bc1d25d921ecba4fd42f89b911a4bd` matches the
exact tree of prior published snapshot `9e8e55f`. It also includes the
observed user merge of integration PR
[#292](https://github.com/emanuelGitCodes/fewia/pull/292). This recovery run
did not merge `main`.

The current integration source
`e119a2d4a12c532e333bd43ac49c38ab52a1e49f` is pushed on
`codex/evaluation-resume`. Seven approved source slices are open as draft
pull requests. Each slice adds no more than 150 source lines.

| Item | Draft PR | Source SHA | Source lines | Local tests passed | Review | Remote CI |
|---|---|---|---:|---:|---|---|
| 02 | [#288](https://github.com/emanuelGitCodes/fewia/pull/288) | `05abadb17e8de4e5cb089d82bb524924de28e52a` | 148 | 6,214 | APPROVE | 7/7 SUCCESS |
| 04 | [#289](https://github.com/emanuelGitCodes/fewia/pull/289) | `3b4c47fedb2c81ec0c4620db410307b0cc46eb8c` | 150 | 6,116 | APPROVE | 7/7 SUCCESS |
| 08b | [#293](https://github.com/emanuelGitCodes/fewia/pull/293) | `62e77e243b9a67f685c7c89ef15754034fb6a4a4` | 53 | 6,153 | APPROVE | 7/7 SUCCESS |
| 11a | [#294](https://github.com/emanuelGitCodes/fewia/pull/294) | `36556715fc0c0a37930c998097c965faf902b03e` | 141 | 6,170 | APPROVE | 7/7 SUCCESS |
| 07a | [#295](https://github.com/emanuelGitCodes/fewia/pull/295) | `de7267be983fc122bb78b3461c4818254dd289d8` | 118 | 6,144 | APPROVE | 7/7 SUCCESS |
| 11 | [#296](https://github.com/emanuelGitCodes/fewia/pull/296) | `2e8a6fdf58968536965071595cb707c0dd8caf6a` | 109 | 6,201 | APPROVE | 7/7 SUCCESS |
| 07 | [#297](https://github.com/emanuelGitCodes/fewia/pull/297) | `b227f19ecd81f6a5b6d53f486c32fa5328060d4a` | 150 | 6,195 | APPROVE | 7/7 SUCCESS |

The local test counts, source lines, reviews, and remote CI states come from
the archived [manifest](../artifacts/evaluation-recovery-20261003/manifest.json).
Each remote check is completed with `SUCCESS`. Archived per-slice evidence:

| Item | Gate record | Review record | Probe record |
|---|---|---|---|
| 02 | [gate](../artifacts/evaluation-recovery-20261003/gates/02.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/02.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/02.txt) |
| 04 | [gate](../artifacts/evaluation-recovery-20261003/gates/04.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/04.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/04.txt) |
| 08b | [gate](../artifacts/evaluation-recovery-20261003/gates/08b.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/08b.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/08b.txt) |
| 11a | [gate](../artifacts/evaluation-recovery-20261003/gates/11a.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/11a.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/11a.txt) |
| 07a | [gate](../artifacts/evaluation-recovery-20261003/gates/07a.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/07a.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/07a.txt) |
| 11 | [gate](../artifacts/evaluation-recovery-20261003/gates/11.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/11.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/11.txt) |
| 07 | [gate](../artifacts/evaluation-recovery-20261003/gates/07.json) | [review](../artifacts/evaluation-recovery-20261003/reviews/07.md) | [probe](../artifacts/evaluation-recovery-20261003/probes/07.txt) |

## Merge order and held draft

The recorded merge order has these constraints:

- PR #288 is independent.
- PR #293 is independent and comes before held PR #290.
- PR #289 comes before PR #294, then PR #296.
- PR #289 comes before PR #295, then PR #297.

Draft PR #290 is pushed but held. Its fourth review asks for a captured
result when a refusal calls the budget read. The approved helper permits a
call without a result. The [review record](../artifacts/evaluation-recovery-20261003/reviews/08.md)
describes the finding. The coordinator reproduced A03 and A04 passing that
case. A request for one further round is pending. No answer is assumed.
See the held-item [gate](../artifacts/evaluation-recovery-20261003/gates/08.json),
[review](../artifacts/evaluation-recovery-20261003/reviews/08.md), and
[probe](../artifacts/evaluation-recovery-20261003/probes/08.txt) records.

## Integrated gates and remaining work

The coordinator recorded integrated gates for source
`e119a2d4a12c532e333bd43ac49c38ab52a1e49f` at
`2026-10-03T13:44:59.711277Z`:

| Gate | Result |
|---|---|
| Ruff check | PASS — All checks passed! |
| Ruff format | PASS — 276 files already formatted |
| Strict mypy | PASS — no issues in 137 source files |
| Pytest | PASS — 6,537 passed, 1 warning |

See the archived [integrated gate record](../artifacts/evaluation-recovery-20261003/integrated-gates.json).
The seven source slices add 869 application lines in total. They are seven
separately capped slices, not one compliant pull request.

Items [21 dispatch](../artifacts/evaluation-recovery-20261003/pending-briefs/21-dispatch.txt),
[22 batch](../artifacts/evaluation-recovery-20261003/pending-briefs/22-batch.txt),
[27 report](../artifacts/evaluation-recovery-20261003/pending-briefs/27-render-report.txt),
and [28 CLI](../artifacts/evaluation-recovery-20261003/pending-briefs/28-cli.txt)
remain queued. Item [29](../artifacts/evaluation-recovery-20261003/pending-briefs/29-records.txt)
is deferred until final evidence. The full benchmark did not run. The planned
matrix has 90 primary slots (30 cases repeated three times) and 48 baseline
slots; it is not execution evidence.

## Evidence classes

| Evidence class | Recorded evidence |
|---|---|
| Deterministic | Local gates and test counts. They do not establish live behavior. |
| Sandbox | No sandbox run is recorded. |
| Live | No full live benchmark ran. |
| Deployed | No deployed evaluation is recorded. |

Remote pull request checks are separate CI evidence. They do not show
live-provider behavior. Do not present planned or fixture results as retailer,
financial, or population facts.

## Graphify record

Graphify processed source `e119a2d4a12c532e333bd43ac49c38ab52a1e49f`.
It found 18 changed files: 14 code files and four semantic files. All four
semantic files were processed and saved to the cache. The graph has 6,564
nodes, 19,238 edges, and 322 communities.

The health report records 18 self-loop edges. It reports zero unverified
nodes, non-object edges, missing or dangling endpoint edges, external
references, exact duplicate edges, and directed or undirected collapsed
endpoint pairs. The self-loops remain a health warning. They do not prove code
corruption or establish a fully clean graph.
See the archived [Graphify report](../artifacts/evaluation-recovery-20261003/GRAPH_REPORT.md),
[update record](../artifacts/evaluation-recovery-20261003/graph-update.json),
and [health record](../artifacts/evaluation-recovery-20261003/graph-health.json).

These archived summaries are committed. Full `graph.json` and HTML remain
ignored local outputs. The graph covers code and the historical wiki snapshot
before this recovery page. It does not index this page. Native semantic token
usage is unavailable. Deterministic AST extraction uses no model calls.

## Supervisor usage and budget

The manifest records 223 CLI supervisor attempts. Known totals are 62,290,497
input tokens, 1,276,775 output tokens, and 568,470 reasoning tokens. Input
counts include cached tokens. These known sums are lower bounds where attempts
have unknown counts. Per-item counts appear in the manifest's `usage.items`
record. Coordinator and native junior usage are unavailable and excluded.

| Phase | Attempts | Input tokens (unknown attempts) | Output tokens (unknown attempts) | Reasoning tokens (unknown attempts) | Process elapsed |
|---|---:|---:|---:|---:|---:|
| Implement | 55 | 26,361,436 (5) | 626,427 (5) | 241,591 (5) | 24,141,312 ms |
| Repair | 95 | 25,107,913 (2) | 400,583 (2) | 146,934 (2) | 14,932,462 ms |
| Review | 73 | 10,821,148 (0) | 249,765 (0) | 179,945 (0) | 6,535,299 ms |

Process elapsed values overlap and do not show wall-clock duration. The
manifest records an 8% weekly stop reserve, 92% used, and 8% remaining at
`2026-10-03T13:53:14.872961Z`. New development had stopped at that threshold.
This reading predates this documentation edit. It is not a current balance.
