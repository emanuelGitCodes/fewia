# Backlog build checkpoint

- Date: 2026-10-03
- Source revision: `be7470aac8212dc297ac8c651e643e272cf1aec2`
- Publication: branches and pull requests authorized; merges are not authorized.
- Stop condition: stop model work at 8 percent total weekly Codex usage.
- Starting weekly usage: 1 percent.
- Weekly usage at stop: 8 percent. No further implementation or model review runs.

## Status

This record separates source inspection from runtime verification.
Open pull requests do not establish that a change reached `main`.

| Item | State | Evidence or next step |
|---|---|---|
| A1 | Published, CI green | [PR 315](https://github.com/emanuelGitCodes/fewia/pull/315), `23ca51a`; independent Sol review approved. |
| A2 | Draft; CI blocked | [PR 317](https://github.com/emanuelGitCodes/fewia/pull/317), `6c6d189`; review approved, but GitHub cannot resolve `astral-sh/setup-uv@v10`. |
| A3 | Present and checked locally | Both audit commands use `--no-deps`. Import and line-length lint passes. |
| A4 | Awaiting retention choice | No data deletion is authorized by this build. |
| A5 | Present and tested | Quantity and serving scaling already exists; nutrition and catalog tests pass. |
| A6 | Present and tested | Session counter reset and pre-launch recovery already exist; focused tests pass. |
| A7 | Published, CI green | [PR 314](https://github.com/emanuelGitCodes/fewia/pull/314), `fdb89cb`; 12 new tests, mutation caught, Luna review approved. |
| B1 | Published, CI green | [PR 316](https://github.com/emanuelGitCodes/fewia/pull/316), `38657a7`; 243 tooling tests, mutation caught, Luna review approved. |
| B2 | Draft repair; independent review pending | [PR 320](https://github.com/emanuelGitCodes/fewia/pull/320), `24ba3d6`; frontend gates and 51 focused tests pass. Historical review requested changes. |
| B3 | Partial measurement | CLI usage is recorded below; junior/coordinator totals and one timed-out writer remain unavailable. |
| B4 | Open | Browser checks need screenshots and recorded results. |
| B5 | Committed and pushed; gates fail | `db4226f` on `codex/backlog-20261003-b5`; 6914 tests pass, strict mypy has two errors, and the gate counts 158/150 lines. Split before opening a code PR. Renderer remains open. |
| C1 | Open | Implement slot dispatch after the report contract is fixed. |
| C2 | Open | Implement the 138-slot batch after C1. |
| C3 | Open | Implement the opt-in CLI after C2 and B5. |
| C4 | Draft recovery record; no code change | [PR 319](https://github.com/emanuelGitCodes/fewia/pull/319) preserves findings and the corrected writer constraints. The requested guards remain open. |
| D1 | Blocked by C1 to C3 | Fixture and live benchmarks have not run in this build. |
| D2 | Blocked by D1 | Record final benchmark artifacts only after execution. |
| D3 | Blocked by D1 | The paper needs benchmark evidence. |
| D4 | Paused by product decision | Plaid Sandbox remains the last feature. |
| D5 | Open | Each mutating AWS step needs owner confirmation. |

## Local checks

- `uv run --project backend pytest -q backend/tests/test_meal_nutrition.py backend/tests/test_spoonacular_catalog.py`: 24 passed, one Starlette warning.
- `PYTHONPATH=.:backend uv run --project backend pytest -q backend/tests/test_database_gate.py tests/supervisor/test_lease.py tests/supervisor/test_execution.py`: 36 passed, one Starlette warning.
- `uv run --project backend ruff check backend/alembic`: all checks passed.
- `uv run --project backend ruff check --select I,E501 backend/app backend/tests dev_supervisor tests infra --exclude infra/bedrock`: all checks passed.

These commands used a temporary uv cache. An initial combined pytest command
failed collection without the repository root on `PYTHONPATH`. The corrected
command above passed. These focused checks do not replace each changed
branch's gates or its independent review.

## Runtime isolation

The container `fewia-backlog-20261003-postgres` belonged to this build.
It used host port 55447 and was stopped at the usage limit.
Existing FEWIA containers remain untouched.
The build creates no deployed AWS evidence.

## Review artifacts

The [artifact directory](../artifacts/backlog-20261003/) preserves completed
reviews and the gate/probe records. The historical nutrition review returned
`REQUEST_CHANGES`; it does not approve the existing compatibility code.

Two A7 writer runs made no edits under a blanket command prohibition.
The corrected brief permitted the Codex file-reading shell commands that
`AGENTS.md` permits. The next writer run produced the tests.

## Measurement limits

The historical delegation-efficiency baseline estimates 1.8 million junior,
reviewer, and audit tokens. It omits writer and review-model tokens.
This run's CLI ledger measures writer and review-model tokens. It does not
provide the coordinator and junior totals. These scopes cannot establish a
token reduction. A timed-out B5 helper attempt also has unknown token counts.

The user asked about Grafana. No Grafana configuration was found in this
checkout. Clarification between Grafana and Graphify remains pending.

## Stop and resume

The account reached 8 percent weekly usage. All writers stopped.
Shutdown preserved eight work branches and seven pull requests.
The B5 branch is pushed without a code PR because its 158-line change needs a split.
The evidence update is [draft PR 318](https://github.com/emanuelGitCodes/fewia/pull/318),
stacked on PR 315. Its review artifacts describe the underlying revisions;
the evidence document has not had a separate independent review.

Resume with the failed setup-uv action reference in PR 317, the B5 split and
two redundant casts, and independent review of PR 320. C4 has no implementation.
The renderer, dispatcher, batch, CLI, benchmarks, browser verification, course
deliverables, and deployment remain incomplete. No merge or deployment occurred.
