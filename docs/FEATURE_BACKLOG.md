# FEWIA feature backlog

This document lists every feature the project committed to build, its
state on `main` at `8bfd4b8` (2026-10-03, after #313 to #320), and the open work ranked from
easiest to hardest. It is the handoff for the next writer. The senior
coordinator verifies each item after the writer reports.

Sources: `PRODUCT.md`, `.codex/project-context.md`, `project-plan.md`,
`docs/EVALUATION.md`, `docs/GROCERY_VERIFICATION_PLAN.md`, the pages under
`wiki/phases/`, the decisions under `wiki/decisions/`, the ledgers under
`.claude/loop/`, the pending briefs under
`wiki/artifacts/evaluation-recovery-20261003/pending-briefs/`, and the code.

## Rules for the writer

- One pull request per item. A pull request MUST NOT add more than 150
  code lines. Tests and docs do not count. Split a larger item into a stack
  and name the parent in each body.
- Base independent branches on `main`. Base each stacked child on its parent.
  Writers MUST NOT merge. The coordinator needs explicit merge authorization.
- The coordinator or junior runs the gates before reporting:
  `uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main`.
- Prose follows ASD-STE100. Requirement words are MUST, MUST NOT, SHOULD,
  SHOULD NOT, and MAY.
- Do not start Plaid live work, live Instacart handoff, or any health-era
  phase. C4 permits the handoff button against a fixture provider only.
- Do not claim a live-provider result from a fixture run. Label evidence
  as fixture, emulator, Sandbox, live, or deployed.

## Part 1. Built and verified

These need no work. They are listed so the writer does not rebuild them.

| Area | What exists | Evidence |
|---|---|---|
| Local stack | React and TypeScript chat, FastAPI, PostgreSQL, worker, Floci SQS and S3, nginx, in Docker Compose. 7 migrations. 12 routes across 6 routers plus `/healthz`, every route tested. | `docker compose up -d`; CI green on `main` |
| Chat loop | Bedrock `LLMProvider` with tool calling, 8 model turns and 3 planner revisions per job, refusal parser, typed unsupported-diet and unsupported-ingredient errors, read-only `get_budget_summary`. | `backend/app/agent/`; live Nova 2 Lite chat verified 2026-09-08 |
| Planning | 40-meal catalog `sample-prices-v2`, 1 to 3 meals, 1 to 8 servings, pantry, exclusions, diet validation, shared-ingredient aggregation before package rounding, labeled sample prices. | `backend/app/domain/`, decision 0017 |
| Budget | Manual spending source as default. User limit minus posted spending, clamped to zero. Pending cents separate. Stale-spending rule. Explicit plan cap. | decision 0016, `backend/app/services/` |
| Templates | `POST /grocery/templates` with six presets filtered by budget, diet, pantry, and exclusions. Frontend meal-ideas picker. | moderate backlog item 15 |
| Nutrition | USDA FoodData Central facts per meal and per plan. Spoonacular average-cost overlay at read time, never stored. | decisions 0010 and 0016 |
| Jobs | PostgreSQL jobs, outbox, leases, duplicate-delivery handling, dead letters, evidence revisions. Floci queues `fewia-sync` and `fewia-agent` with dead-letter queues, bucket `fewia-eval`. | `backend/app/services/`, `infra/floci_bootstrap.py` |
| Providers | `BedrockConverseProvider` for us-east-1 and us-west-2, active only when `FEWIA_BEDROCK_MODEL_ID` is set. `PlaidSandboxProvider` and `sync_item`. `InstacartDevelopmentProvider` with `POST /grocery/handoffs`, `GET`, and `/retry`, hidden in the UI unless `instacart_configured`. | `backend/app/providers/`, `backend/app/api/handoff.py` |
| Frontend | App, BudgetForm, Conversation, ChatPanel, ChatWorkspace, Estimate, Nutrition, TemplatePicker, HandoffControls (hidden). Manual-plan to chat context transfer. | `frontend/src/`, 238 or more tests |
| Evaluation components | 49 `evaluation_*.py` modules: inputs, manifest, capture, adversarial scenarios, fault provider, plan facts and scoring, claim scoring, outcome scoring, refusal actions, telemetry, cost, matrix, summaries, model and no-tool observers, duplicate and handoff and refresh drivers, SQLite evidence, JSON output. | `backend/app/evaluation_*.py`; 6831 backend tests |
| Legacy runner | `run_evaluation` scores the deterministic groups: 42 scored, 48 unassessed. | `backend/app/evaluation_runner.py` |
| Tooling | `dev_supervisor` writer, gates, review, usage, lease. Tooling CI. Migration drift check. Dependency audits. ESLint. | `dev_supervisor/`, `.github/workflows/` |
| Repair loop | Nine review findings from the evaluation PRs repaired and merged. | #302 to #312 |

## Part 2. Open work, ranked from easiest to hardest

Difficulty: 1 is a one-file change with a known pattern. 5 is a new
subsystem with a live provider or a contract that other code depends on.

Each item names the acceptance check the coordinator runs. The writer MUST
make that check pass.

### Tier A. Small, isolated, deterministic

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| A1 | Refresh the two stale ledger State columns so they match their event logs. | merged, #315 | 1 | `.claude/loop/tech-debt-2.md`, `.claude/loop/delegation-efficiency.md` | Every row's State agrees with the last event for that item. Prose only. |
| A2 | Close or record the Phase 1 to 3 open items: alembic in the lint path, Node 20 actions, mypy on tests, alembic in the backend image. | merged, #317 | 1 | `wiki/phases/phase-1.md`, `phase-3.md`, `.github/workflows/*.yml` if a fix is small | Each item is either fixed in CI or recorded as closed with a reason. |
| A3 | Add `pip-audit --no-deps` and extend Ruff to the `I` and `E501` rule sets, per the debt-guardrails follow-ups. | already present before this backlog | 1 | `.github/workflows/tooling.yml`, `backend/pyproject.toml` | Tooling CI passes with the new rules. No file-level suppressions. |
| A4 | Record the retention decision for stored Spoonacular totals and the retired health tables. Write decision 0018. No data deletion. | published, unmerged: [#325](https://github.com/emanuelGitCodes/fewia/pull/325), stacked on #321 | 1 | `wiki/decisions/0018-*.md`, `wiki/index.md`, `wiki/log.md` | Decision 0018 retains existing records only and states the future deletion review requirements. |
| A5 | Quantity-scaled nutrition totals: scale USDA per-100g facts by the planned ingredient quantity and servings. | already present before this backlog | 2 | `backend/app/services/meal_nutrition.py`, its tests | A 4-serving plan reports double the 2-serving totals. Labels say the totals are estimates. |
| A6 | Reset the supervisor DB-test skip counter per session and release the lease on a pre-spawn crash. | already present before this backlog | 2 | `dev_supervisor/lease.py`, `dev_supervisor/__main__.py`, `tests/supervisor/` | A crash before spawn leaves no lease file. Tests cover both paths. |
| A7 | Add the missing unit tests for `frontend/src/usePolledJob.ts` and `backend/app/domain/spoonacular_catalog.py`. | merged, #314 | 1 | the two test files | Each file has a direct test. Removing the polling stop condition fails a test. |

### Tier B. Bounded code with a fixed contract

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| B1 | Grok fallback for the review command when Codex is unavailable, with the deviation recorded in the review output. | merged, #316; see B6 | 2 | `dev_supervisor/review.py`, `tests/supervisor/test_review.py` | With Codex forced unavailable, the review runs on Grok and the JSON names the fallback. |
| B2 | Independent review of the 2026-09-21 nutrition compatibility change, recorded in the wiki. | merged, #320 | 2 | `wiki/log.md`, `wiki/phases/grocery-mvp-checkpoint.md` | A review verdict and SHA appear in the log. |
| B3 | Delegation-efficiency item 09: record a limited tier S documentation pilot beside the Phase 1 baseline. | measured; publication pending (limited documentation pilot; [record](../wiki/phases/backlog-resume-20261003.md)) | 2 | `.claude/loop/delegation-efficiency.md`, `wiki/log.md` | Record per-item and total CLI tokens beside the baseline. State the cohort limits. Do not claim a percentage reduction, a causal efficiency gain, or a like-for-like speed comparison. |
| B4 | Browser checks from the verification plan: desktop and mobile layout, focus order, polling stop on completion, handoff consent dialog. Record each as pass or fail with a screenshot path. | published, unmerged: [#327](https://github.com/emanuelGitCodes/fewia/pull/327); all 7 GitHub CI checks passed at the latest snapshot | 3 | `docs/GROCERY_VERIFICATION_PLAN.md`, `frontend/src/*.test.tsx` for any gap found | The record preserves the original consent failure and the repaired 14-check fixture pass. Desktop and mobile layout checks passed. Initial focus order passed for the listed controls only. Broader browser scope remains open. |
| B5 | Evaluation item 27: `render_report(output) -> str` in `backend/app/evaluation_markdown.py`. Coverage-first Markdown: per-condition numerators and denominators, failures, unassessed reasons, token use, p50 and p95 latency, cost. It MUST NOT state that a target is met. | partial: strict-value helper is published, unmerged in [#322](https://github.com/emanuelGitCodes/fewia/pull/322); data branch `codex/backlog-resume-b5-data` has latest clean checkpoint `98a2db8` at 109 source lines and 7,088 tests, with findings-context work in progress, no PR, and no complete review; report-sections branch `codex/backlog-resume-report-sections` is at `411b0d0` with 147 source lines and backend gates passing 7,142 tests, review pending; telemetry branch `codex/backlog-resume-report-telemetry` is in progress | 3 | `backend/app/evaluation_markdown.py`, `backend/tests/test_evaluation_markdown.py` | Rendering a fixture output with 42 scored and 48 unassessed shows both counts and no target claim. Labels are escaped. |
| B6 | Review fallback matcher: match a structured Codex error on both `code` and `message`. Today only `code` is matched when present, so `{"code":"api_error","message":"HTTP 503 service unavailable"}` does not fall back to Grok. Recorded at #316 merge. | published, unmerged: [#324](https://github.com/emanuelGitCodes/fewia/pull/324) | 2 | `dev_supervisor/review.py`, `tests/supervisor/test_review.py` | That error shape falls back with `fallback_reason == "codex_unavailable"`. Existing fallback tests still pass. |

### Tier C. New contracts that other code depends on

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| C1 | Evaluation item 21: `run_slot(slot, runtime: EvaluationRuntime) -> dict` in `backend/app/evaluation_dispatch.py`. Route each matrix slot to the fixture evaluator, the model observer, the no-tool observer, the reference driver, or a provider-failure driver P01 to P05, then attach assessments. A missing local service reports `unassessed`, never a pass. | partial: runtime published in [#328](https://github.com/emanuelGitCodes/fewia/pull/328) on `codex/backlog-resume-runtime` at `26fe9148da0c12bd5c55218b063fcc15d54ee7c4`; 92 source lines, backend gates passed 6,889 tests, 18-fixture smoke passed with no model calls, empty-check mutation caused 3 failures, independent Luna high review approved; dispatch branch `codex/backlog-resume-dispatch` is in progress with no PR; no CI result is recorded for #328 | 4 | `backend/app/evaluation_dispatch.py`, `backend/tests/test_evaluation_dispatch.py` | Every slot kind in `evaluation_matrix.py` dispatches. With PostgreSQL absent, database slots return `unassessed` with a reason. No provider is called for fixture slots. |
| C2 | Evaluation item 22: `run_evaluation_batch(corpus, manifest, runtime, on_slot)` in `backend/app/evaluation_batch.py`. Freeze corpus, manifest, and revision. Run 90 primary, 33 no-tool, and 15 deterministic slots, 138 in total. Call `on_slot` with a deep copy after each slot. | incomplete; pending brief exists | 4 | `backend/app/evaluation_batch.py`, `backend/tests/test_evaluation_batch.py` | A fixture run produces 138 slot records in order. A failure in slot 50 keeps slots 1 to 49 in the journal. Depends on C1. |
| C3 | Evaluation item 28: `python -m app.evaluate` CLI with `--live-bedrock` as an explicit opt-in, Nova 2 Lite US profile only, optional `--local-services`, exclusive output and journal paths, exit codes 0, 1, and 130. | incomplete; pending brief exists | 4 | `backend/app/evaluate.py`, `backend/tests/test_evaluate_cli.py` | Without `--live-bedrock`, no network call occurs. An existing output path exits 1. SIGINT exits 130 with a partial journal. Depends on C2 and B5. |
| C4 | Handoff button flow in the frontend: validate the handoff URL before navigation and surface the existing `POST /grocery/handoffs/{id}/retry` as a visible retry on an uncertain write. The backend routes exist. Instacart itself stays parked; the flow runs against a fixture provider with `instacart_configured` true. | published, unmerged: [#323](https://github.com/emanuelGitCodes/fewia/pull/323); consent follow-up: [#327](https://github.com/emanuelGitCodes/fewia/pull/327) | 3 | `frontend/src/HandoffControls.tsx`, `frontend/src/useHandoff.ts`, `frontend/src/handoffApi.ts`, tests | With `instacart_configured` false, nothing renders. With a fixture provider, a link appears only after URL validation, and an uncertain write shows a retry button that calls the retry route once per click. |

### Tier D. Live evidence and release work

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| D1 | Run the 138-slot benchmark with deterministic fixtures and publish the report. Then run it once with `--live-bedrock` on Nova 2 Lite. Record task success, valid tools, supported claims, clarification, latency, and cost against the 90% and 95% targets. State pass or fail for each target. | not run | 5 | `eval/results/`, `docs/EVALUATION.md`, `wiki/phases/evaluation-completion.md` | The report names the manifest hash, the model, the region, 138 slots, and per-target numerators and denominators. Depends on C1 to C3. |
| D2 | Evaluation item 29: update `docs/EVALUATION.md`, the completion page, the index, and the log with the final benchmark artifacts. | deferred until D1 | 2 | the four files above | Every number in the docs matches a file under `eval/results/`. |
| D3 | Course deliverables: 8-page paper, demo script, failure log with one example per failure class, limitations. | required, no status | 4 | `docs/` | Each section cites an artifact in the repository. |
| D4 | Plaid Sandbox live evidence: run `/transactions/sync` against Sandbox, serialize item syncs, apply changes and cursor atomically, and record posted and pending grocery spend. Last feature by decision. | paused | 5 | `backend/app/services/plaid_sync.py`, tests, `wiki/log.md` | A Sandbox run records posted and pending cents with the `plaid_sandbox` label. No real account. |
| D5 | Public hosting: ECS Fargate, RDS PostgreSQL, Secrets Manager, CloudWatch, Bedrock. Every mutating AWS step confirmed by the owner first. | not started | 5 | `infra/` | The deployed stack answers one chat turn with live Bedrock and the deployed label. |

## Part 3. Items that need no writer

- **Secret scanning and push protection.** A GitHub repository setting. The owner turns it on.
- **Renew the AWS MFA session** before the next live test. Owner action.
- **Instacart handoff.** Parked until the Instacart Developer Platform reopens. C4 builds the flow against a fixture only.
- **Health-era Phases 4 to 9** in `project-plan.md`. Historical. Do not resume.
- **Comparison tool** from decision 0012. Build only after a measured need.

## Part 4. Suggested order

1. Done: A1, A2, A7, B1, B2. Already present: A3, A5, A6.
2. A4, B3, B4, B6 in any order. Each is one pull request and one review round.
3. B5, then C1, then C2, then C3. These form one stack and MUST merge in that order.
4. C4 in parallel with the C stack.
5. D1, then D2.
6. D3 after D1 so the paper cites real numbers.
7. D4, then D5, only if time remains.
