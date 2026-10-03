# Backlog resume checkpoint

- Date: 2026-10-03
- Baseline: `8bfd4b80`, verified as `origin/main` at intake.
- Starting weekly usage: 9 percent used.
- New stop: 92 percent used, leaving 8 percent. This replaces the earlier stop.
- Weekly usage totals are deferred until the final snapshot.
- The user authorizes implementation, commits, branch pushes, and pull requests.
- Merges remain subject to separate owner authorization.
- The user chose to retain legacy data pending a separate deletion decision.
- The requested graph update is Graphify.

## Work items

| Item | Branch | PR | Source SHA | State and verification |
|---|---|---|---|---|
| B5 strict-value helper | `codex/backlog-resume-b5-values` | [#322](https://github.com/emanuelGitCodes/fewia/pull/322) | `98fde259ebc2281cf652d045eb26add13f07172e` | Published, unmerged. 28 code lines. Backend Ruff, format, strict mypy, and 6,874 tests passed. Independent Luna high review approved. GitHub CI reported all 7 checks successful at this snapshot. This verifies the helper only. |
| C4 fixture handoff guards | `codex/backlog-resume-c4` | [#323](https://github.com/emanuelGitCodes/fewia/pull/323) | `0246c9b1c249f719b1f10b4a9bf99db499a1f26b` | Published, unmerged. 10 code lines. Frontend install, lint, tests, and build passed. Independent Luna high review approved. GitHub CI reported all 7 checks successful at this snapshot. |
| B6 structured error matching | `codex/backlog-resume-b6` | [#324](https://github.com/emanuelGitCodes/fewia/pull/324) | `578df44aa0fa5107167dadec1e8f7773ce9e041f` | Published, unmerged. 12 code lines. Tooling Ruff, format, strict mypy, and 326 tests passed. Independent Luna high review approved. GitHub CI reported all 7 checks successful at this snapshot. |
| A4 retention decision | `codex/backlog-resume-a4` | [#325](https://github.com/emanuelGitCodes/fewia/pull/325) | `36843e7e2d01590c29ad3655691c6bfbc161ae58` | Published, unmerged; documentation stacked on #321. Independent Sol low review approved. Decision 0018 retains existing records only; it does not authorize new Spoonacular price storage or data deletion. Latest GitHub CI snapshot: all 7 checks successful. |
| Writer protocol correction | `codex/backlog-resume-writer-protocol` | [#326](https://github.com/emanuelGitCodes/fewia/pull/326) | `e903429cb69f3d562d8c72e19f431000a34ab7af` | Published, unmerged; Sol low review approved and documentation gates passed. |
| B4 consent and browser evidence | `codex/backlog-resume-consent` | [#327](https://github.com/emanuelGitCodes/fewia/pull/327) | `85493df8ace8ff246df0c15dfccb40e22aef1a62` | Published, unmerged; 119 code lines, stacked on #323. Frontend gates passed. Independent Luna high review approved. Latest GitHub CI snapshot: all 7 checks successful. Browser results are recorded separately below. |

The GitHub CI snapshots for PRs #322 to #325 and #327 report all 7 checks
successful. No PR was merged by this run. No CI result is recorded for #328.
The documentation merge order is #321, #325, #326, then this evidence PR.

## B3 token pilot

Status: measured; publication pending (limited documentation pilot). The tier S pilot covers two completed documentation items: A4 retention and Writer protocol. It used no native junior or reviewer subagents. The CLI work totals 1,079,282 input tokens and 17,390 output tokens across 8 attempts, or 1,096,672 combined tokens. Coordinator tokens are excluded.

The Phase 1 baseline is about 1,820,000 native subagent tokens for about 270 code lines plus tests and docs. Its CLI writer and review totals are unknown. The pilot cohort differs from the baseline workload. This result supports tier S routing and measurement. It does not support a percentage reduction in total cost, a causal efficiency gain, or a like-for-like speed comparison.

See the [pilot evidence](../artifacts/backlog-resume-20261003/tier-s-pilot.json) and the [detailed ledger](../../.claude/loop/delegation-efficiency.md#tier-s-documentation-pilot).

## Remaining evaluation work

| Work | Branch | PR | Source SHA | State and verification limit |
|---|---|---|---|---|
| B5 data and manifest repair | `codex/backlog-resume-b5-data` | None | `98a2db8` | Manifest integrity is repaired. The latest clean checkpoint is SHA `98a2db8`, with 109 source lines and 7,088 tests recorded. A findings-context addition is in progress. No PR exists, and the branch is not fully reviewed. |
| B5 report sections | `codex/backlog-resume-report-sections` | None | `411b0d0` | 147 source lines; backend gates passed 7,142 tests. Review is pending. |
| B5 report telemetry | `codex/backlog-resume-report-telemetry` | None | In progress | Work is in progress; no final SHA or verification result is recorded. |
| C1 runtime | `codex/backlog-resume-runtime` | [#328](https://github.com/emanuelGitCodes/fewia/pull/328) | `26fe9148da0c12bd5c55218b063fcc15d54ee7c4` | Published, unmerged; 92 source lines. Backend Ruff, format, strict mypy, and 6,889 tests passed. The 18-fixture smoke passed with no model calls. An empty-check mutation caused 3 failures. Independent Luna high review approved. No CI result is recorded. |
| C1 dispatch | `codex/backlog-resume-dispatch` | None | In progress | Work is in progress; C1 is not complete. |
| C2, C3, and D1 benchmark | In progress | None | Not run | C2 and C3 are incomplete. D1 has not run. |

D2 and D3 remain dependent on the evaluation work. The requested Graphify
update remains open; this record does not claim a graph refresh.

The old B5 branch at `db4226f` remains an unchanged recovery source.
PR 321 supplies pending status documentation; it is not merged at intake.
The run uses its own PostgreSQL container on port 55447 and Compose project
`fewia-resume-20261003` on web 5186, API 8019, PostgreSQL 55452, and Floci 4578.
Existing FEWIA stacks remain untouched.
