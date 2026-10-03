# Phase 3 — Deterministic tools and FastAPI endpoints

- **Completed**: 2026-09-01
- **Plan**: [project-plan.md](../../project-plan.md), Phase 3
- **Source**: `docs/CAP6938_MVP_PROJECT_PLAN.md` §6
- **Writer**: Codex. **Verifier**: Claude, per
  [decisions/0006-codex-writes-claude-verifies.md](../decisions/0006-codex-writes-claude-verifies.md).

## What shipped

Eleven work items shipped through these pull requests, in merge order:

1. #15 `feat/tools-foundation` — `app/tools/base.py` with `ToolWarning`,
   `ContextResponse`, `ToolError`, `build_evidence_id`, `validate_range`,
   `require_user`, `missing_day_warnings`, `round_money`; `app/deps.py`;
   the empty `/context` router. 144 code lines.
2. #16 `docs/decision-0007-evidence-id` — decision 0007.
3. #20 `feat/health-context` — `get_health_context` and
   `GET /context/health`. 133 code lines.
4. #19 `feat/financial-context` — `get_financial_context` and
   `GET /context/financial`. 97 code lines.
5. #17 `feat/environment-context` — `get_environment_context` and
   `GET /context/environment`. 78 code lines.
6. #18 `feat/activity-prediction-stub` — `run_activity_prediction` with
   `model_version` `stub-v0` and `GET /predict/activity`. 119 code lines.
7. #21 `feat/compare-periods` — `compare_periods` and
   `GET /context/compare`. 117 code lines.
8. #22 `test/tools-foundation` — the shared fixtures and the base tests.
9. #24, #25, #23 — the tool tests, the endpoint tests, and the error tests.
10. #26 — recovery. #24, #25, and #23 had merged into
    `test/tools-foundation` after #22 already merged to `main`, so their
    content stayed off `main`. #26 carried all three across. Nothing was lost.
11. #27 `fix/compare-evidence` — five defects in `compare.py`.
12. #28 `fix/tool-contract` — four contract defects.
13. #29 `fix/http-error-envelope` — the Starlette `HTTPException` envelope.

`main` holds Phase 3 at commit `fb5c3c8`. 160 tests pass. `ruff check`,
`ruff format --check`, and `mypy --strict app` are clean on 20 source files.

## Verification

Verification ran on 2026-09-01 against PostgreSQL 16 in Docker Compose.

- `alembic upgrade head` reports `0002 (head)`.
- `python -m app.synth --seed 42 --days 90 --end-date 2026-08-31` wrote
  `users=4 finance=360 environment=360 health=341`. The generator default
  end date is `2026-06-30`. The check MUST pass `--end-date 2026-08-31` to
  hold August data.
- The five endpoints returned live data for user 1 in August 2026. Each had
  `evidence_id`, `record_count`, `source`, and `warnings`.
  - `health:user-1:2026-08` had 31 records and 7732 average steps.
  - `finance:user-1:2026-08` had 2112.12 total spending.
  - `environment:user-1:2026-08` had location type urban.
  - `compare:user-1:2026-07_vs_2026-08` returned.
  - `prediction:user-1:2026-08` had the `stub_result` warning.
- The error contract held: 404 `user_not_found`, 422 `invalid_range`, 422
  `validation_error`, 404 `not_found` on an unknown path, and 405
  `method_not_allowed`. Every body uses the `error` envelope.

## Defects that the gates did not catch

Mutation testing found these defects.

- Item 8 round 1: Codex passed every gate. The tool tests still passed when
  the `user_id` filter was deleted from both tools. Seven gaps closed in round
  2.
- `compare.py` shipped five defects: an unordered composite evidence ID, a
  month collision between two sub-ranges, a `PeriodSummary` that carried the
  health evidence ID beside the finance spending figure, merged warnings with
  no period or domain marker, and no direct `require_user` call. #27 closed
  them. The evidence ID is now
  `compare:user-1:2026-01-01..2026-01-15_vs_2026-01-16..2026-01-31`.
- `health.py` warned about `intensity_minutes`, a column it never returned.
  Its nullable averages narrowed their own denominator while `record_count`
  stayed at the full day count. #28 closed both.
- The prediction stub used the `null_fields` warning code. #28 added
  `stub_result`.
- A FastAPI validation 422 and a `ToolError` 422 returned different bodies.
  #28 unified them.
- Starlette's own `HTTPException` kept the body `{"detail": "Not Found"}`.
  An unknown path and a 405 broke the envelope. The live check confirmed it
  on `main`. #29 closed it. Two rounds of findings preceded the merge. The
  unnamed-status fallback carried no test. The first fallback test called
  `app.add_api_route` on the imported application, which leaked a route into
  every later test.

## Open items

- The compare evidence ID is symmetric and the deltas are not. Sorting the
  two periods makes the ID canonical, so a July-August pair and an
  August-July pair share one ID while `steps_delta` and `spending_delta`
  change sign. The project MUST settle this before Phase 6 writes the
  evaluation questions: either add a direction marker, or state in decision
  0007 that the ID names the pair and not the direction.
- The API image holds no `alembic.ini` and no migration directory, so
  `alembic upgrade head` runs from the host, not from `docker compose exec api`.
- `mypy --strict` covers `app` and not `tests`. `mypy --strict app tests`
  fails with 10 errors in `test_synth.py`, `test_synth_loader.py`, and
  `test_tools_base.py`.
- `~/.codex/config.toml` line 10 sets `model_reasoning_effort = "extra high"`,
  which is not a valid value. Every `codex exec` fails until a run overrides
  it with `-c model_reasoning_effort=high`. `codex exec resume` also rejects
  the `--cd` flag that `codex exec` accepts.
- A verifier MUST stage the work before it mutates a file. `git checkout --`
  on unstaged work destroyed one Codex change during item 5.

## Follow-up status — 2026-10-03

- Resolved: `backend/Dockerfile` already copies `backend/alembic` and
  `backend/alembic.ini` into the API image. This closes the historical
  migration-file item.
- Closed as not adopted: expansion of strict type checking to test modules.
  The current project rule keeps `mypy --strict` scoped to `app`. Test modules
  remain outside that scope. The test typing findings above remain as history.
