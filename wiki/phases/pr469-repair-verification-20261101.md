# PR 469 repair verification

PR [#469](https://github.com/emanuelGitCodes/fewia/pull/469) remains open and unmerged. Its repair head is `8cee7e1ad8c7a5e3ae6b74deaef14cf6c065cba6`, based on `main` at `34642bf1ea6c81960877b50f9c9070e354b88cd3`.

## Repairs

- Explicit restarts retain complete cursor filters and limits at offset zero, including named facets, catalog words, and pending no-tool state.
- Canonical conjunctive words preserve paging identity. Unknown-only and omnivore searches do not collide.
- Dairy aliases preserve words, clauses, contractions, and known claim formatting. Benign ingredient text and legacy non-dairy policy guards remain.
- The [repair review record](../../docs/reviews/pr-469-repairs.md) lists contracts and regression proofs.

## Evidence

### Deterministic and local

- Local gates report 15,442 passed, 1 skipped, and 1 warning. Ruff, strict mypy, frontend lint, tests, and build pass.
- Root checks pass: 250 core and 37 edge checks.
- Deterministic fixture `conversation-eval-v1.4` reports 96/96 tool, outcome, and gold checks, plus 57/57 scenario repeats.

### Hosted CI

The four hosted workflows passed nine jobs and 90 steps in total on the repair head:

- [CI run 41357451829](https://github.com/emanuelGitCodes/fewia/actions/runs/41357451829)
- [Tooling run 41357451834](https://github.com/emanuelGitCodes/fewia/actions/runs/41357451834)
- [Audit run 41357451819](https://github.com/emanuelGitCodes/fewia/actions/runs/41357451819)
- [Secrets run 41357451841](https://github.com/emanuelGitCodes/fewia/actions/runs/41357451841)

The PR adds 987 source lines against the 1,000-line limit. Astra approved round five at `8cee7e1a`. The formal runner used high effort; async writers and advisers used xhigh. GitHub credits `@codex` on all 14 new commits.

### Sandbox

No sandbox evidence is recorded for these repairs.

### Live

No new live Nova calls tested these repairs. Fixture checks do not establish live quality, latency, or cost. The older batch accepted 13 of 43 prose attempts with validator fallbacks; see the [historical report](../../eval/results/artifacts/conversation-20261101b/report.md).

### Deployed

There is no deployment claim. Auto-merge is off.

## Proposed follow-ups

These proposals are not built or released. This record adds no numbered decision.

1. Run capped live Nova and browser QA on the fixed head with separate live-call approval.
2. Route questions about selected meals to current-plan facts.
3. Add clear end-of-results messages and retain search state after blocked turns.
4. Keep proposal cards consistent with their explanatory replies.
5. Compare accepted model prose with measured results while retaining guards.

New implementation belongs in follow-up pull requests given the current 987-line count.
