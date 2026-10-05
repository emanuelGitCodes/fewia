# FEWIA feature backlog

This document records the feature backlog and its state on `main` at
`ed00904` (2026-10-04, after #313 to #383). The historical built-feature
table keeps the earlier snapshot. The work tables record merged work and the
[benchmark evidence](../wiki/phases/benchmark-20261003.md).
A merge does not imply deployment or release certification.
The senior coordinator verifies each item after the writer reports.

The [integrity check](../wiki/phases/integrity-20261004.md) of 2026-10-04
exercised every merged subsystem on the local stack and records the open
findings. The [final record](../wiki/phases/backlog-final-20261003.md) and the
[hosting snapshot](../wiki/phases/hosting-preparation-20261003.md) are dated
checkpoints from before the merges.

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

## Part 1. Historical built-feature snapshot

These entries preserve the earlier snapshot. Their test counts and CI
statements are historical, not new verification of the current branch.
The current product supports 40 meals under
[decision 0017](../wiki/decisions/0017-forty-meal-catalog.md) and the
[project scope](../.codex/project-context.md). It supports 1-3 meals per
request and 1-8 servings per meal. The benchmark does not provide exhaustive
catalog coverage. Retired health and activity planning remains historical.

| Area | What exists | Evidence |
|---|---|---|
| Local stack | React and TypeScript chat, FastAPI, PostgreSQL, worker, Floci SQS and S3, nginx, in Docker Compose. 7 migrations. 13 routes across 6 routers plus `/healthz`, every route tested. | `docker compose up -d`; local gates green on `main` at `ed00904`; GitHub CI blocked by Actions billing since 2026-10-04 |
| Chat loop | Bedrock `LLMProvider` with tool calling, 8 model turns and 3 planner revisions per job, refusal parser, typed unsupported-diet and unsupported-ingredient errors, read-only `get_budget_summary`. | `backend/app/agent/`; live Nova 2 Lite chat verified 2026-09-08 |
| Planning | 40-meal catalog `sample-prices-v2`, 1 to 3 meals, 1 to 8 servings, pantry, exclusions, diet validation, shared-ingredient aggregation before package rounding, labeled sample prices. | `backend/app/domain/`, decision 0017 |
| Budget | Manual spending source as default. User limit minus posted spending, clamped to zero. Pending cents separate. Stale-spending rule. Explicit plan cap. | decision 0016, `backend/app/services/` |
| Templates | `POST /grocery/templates` with six presets filtered by budget, diet, pantry, and exclusions. Frontend meal-ideas picker. | moderate backlog item 15 |
| Nutrition | USDA FoodData Central facts per meal and per plan. Spoonacular average-cost overlay at read time, never stored. | decisions 0010 and 0016 |
| Jobs | PostgreSQL jobs, outbox, leases, duplicate-delivery handling, dead letters, evidence revisions. Floci queues `fewia-sync` and `fewia-agent` with dead-letter queues, bucket `fewia-eval`. | `backend/app/services/`, `infra/floci_bootstrap.py` |
| Providers | `BedrockConverseProvider` for us-east-1 and us-west-2, active only when `FEWIA_BEDROCK_MODEL_ID` is set. `PlaidSandboxProvider` and `sync_item`. `InstacartDevelopmentProvider` with `POST /grocery/handoffs`, `GET`, and `/retry`, hidden in the UI unless `instacart_configured`. | `backend/app/providers/`, `backend/app/api/handoff.py` |
| Frontend | App, BudgetForm, Conversation, ChatPanel, ChatWorkspace, Estimate, Nutrition, TemplatePicker, HandoffControls (hidden). Manual-plan to chat context transfer. | `frontend/src/`, 492 tests |
| Evaluation components | 60 `evaluation_*.py` modules plus `evaluate.py`: inputs, manifest, capture, adversarial scenarios, fault provider, plan facts and scoring, claim scoring, outcome scoring, refusal actions, telemetry, cost, matrix, summaries, model and no-tool observers, duplicate and handoff and refresh drivers, SQLite evidence, JSON output. | `backend/app/evaluation_*.py`; 9046 backend tests |
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
| A4 | Record the retention decision for stored Spoonacular totals and the retired health tables. Write decision 0018. No data deletion. | merged, #325 | 1 | `wiki/decisions/0018-*.md`, `wiki/index.md`, `wiki/log.md` | Decision 0018 retains existing records only and states the future deletion review requirements. |
| A5 | Quantity-scaled nutrition totals: scale USDA per-100g facts by the planned ingredient quantity and servings. | already present before this backlog | 2 | `backend/app/services/meal_nutrition.py`, its tests | A 4-serving plan reports double the 2-serving totals. Labels say the totals are estimates. |
| A6 | Reset the supervisor DB-test skip counter per session and release the lease on a pre-spawn crash. | already present before this backlog | 2 | `dev_supervisor/lease.py`, `dev_supervisor/__main__.py`, `tests/supervisor/` | A crash before spawn leaves no lease file. Tests cover both paths. |
| A7 | Add the missing unit tests for `frontend/src/usePolledJob.ts` and `backend/app/domain/spoonacular_catalog.py`. | merged, #314 | 1 | the two test files | Each file has a direct test. Removing the polling stop condition fails a test. |

### Tier B. Bounded code with a fixed contract

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| B1 | Grok fallback for the review command when Codex is unavailable, with the deviation recorded in the review output. | merged, #316; see B6 | 2 | `dev_supervisor/review.py`, `tests/supervisor/test_review.py` | With Codex forced unavailable, the review runs on Grok and the JSON names the fallback. |
| B2 | Independent review of the 2026-09-21 nutrition compatibility change, recorded in the wiki. | merged, #320 | 2 | `wiki/log.md`, `wiki/phases/grocery-mvp-checkpoint.md` | A review verdict and SHA appear in the log. |
| B3 | Delegation-efficiency item 09: record a limited tier S documentation pilot beside the Phase 1 baseline. | merged, #331; partial: a two-item documentation pilot, not one loop of Phase 1 follow-ups | 2 | `.claude/loop/delegation-efficiency.md`, `wiki/log.md` | Record per-item and total CLI tokens beside the baseline. State the cohort limits. Do not claim a percentage reduction, a causal efficiency gain, or a like-for-like speed comparison. |
| B4 | Browser checks from the verification plan: desktop and mobile layout, focus order, polling stop on completion, handoff consent dialog. Record each as pass or fail with a screenshot path. | merged, #327; broader browser scope stays open | 3 | `docs/GROCERY_VERIFICATION_PLAN.md`, `frontend/src/*.test.tsx` for any gap found | The record preserves the original consent failure and the repaired 14-check fixture pass. Desktop and mobile layout checks passed. Initial focus order passed for the listed controls only. Broader browser scope remains open. |
| B5 | Evaluation item 27: `render_report(output) -> str` in `backend/app/evaluation_markdown.py`. Coverage-first Markdown: per-condition numerators and denominators, failures, unassessed reasons, token use, p50 and p95 latency, cost. It MUST NOT state that a target is met. | merged, #322 and #332 to #336 | 3 | `backend/app/evaluation_markdown.py`, `backend/tests/test_evaluation_markdown.py` | Rendering a fixture output with 42 scored and 48 unassessed shows both counts and no target claim. Labels are escaped. |
| B6 | Review fallback matcher: match a structured Codex error on both `code` and `message`. Today only `code` is matched when present, so `{"code":"api_error","message":"HTTP 503 service unavailable"}` does not fall back to Grok. Recorded at #316 merge. | merged, #324 | 2 | `dev_supervisor/review.py`, `tests/supervisor/test_review.py` | That error shape falls back with `fallback_reason == "codex_unavailable"`. Existing fallback tests still pass. |

### Tier C. New contracts that other code depends on

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| C1 | Evaluation item 21: `run_slot(slot, runtime: EvaluationRuntime) -> dict` in `backend/app/evaluation_dispatch.py`. Route each matrix slot to the fixture evaluator, the model observer, the no-tool observer, the reference driver, or a provider-failure driver P01 to P05, then attach assessments. A missing local service reports `unassessed`, never a pass. | merged, #328 and #329 | 4 | `backend/app/evaluation_dispatch.py`, `backend/tests/test_evaluation_dispatch.py` | Every slot kind in `evaluation_matrix.py` dispatches. With PostgreSQL absent, database slots return `unassessed` with a reason. No provider is called for fixture slots. |
| C2 | Evaluation item 22: `run_evaluation_batch(corpus, manifest, runtime, on_slot)` in `backend/app/evaluation_batch.py`. Freeze corpus, manifest, and revision. Run 90 primary, 33 no-tool, and 15 deterministic slots, 138 in total. Call `on_slot` with a deep copy after each slot. | merged, #338 | 4 | `backend/app/evaluation_batch.py`, `backend/tests/test_evaluation_batch.py` | A fixture run produces 138 slot records in order. A failure in slot 50 keeps slots 1 to 49 in the journal. Depends on C1. |
| C3 | Evaluation item 28: `python -m app.evaluate` CLI with `--live-bedrock` as an explicit opt-in, Nova 2 Lite US profile only, optional `--local-services`, exclusive output and journal paths, exit codes 0, 1, and 130. | merged, #339 and #341 | 4 | `backend/app/evaluate.py`, `backend/tests/test_evaluate.py` | Without `--live-bedrock`, the public CLI exits 1 before provider calls. An existing output path exits 1. SIGINT exits 130 with a partial journal. Exit 0 means artifact completion only. Depends on C2 and B5. |
| C4 | Handoff button flow in the frontend: validate the handoff URL before navigation and surface the existing `POST /grocery/handoffs/{id}/retry` as a visible retry on an uncertain write. The backend routes exist. Instacart itself stays parked; the flow runs against a fixture provider with `instacart_configured` true. | merged, #323 and #327 | 3 | `frontend/src/HandoffControls.tsx`, `frontend/src/useHandoff.ts`, `frontend/src/handoffApi.ts`, tests | With `instacart_configured` false, nothing renders. With a fixture provider, a link appears only after URL validation, and an uncertain write shows a retry button that calls the retry route once per click. |

### Tier D. Live evidence and release work

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| D1 | Run the 138-slot benchmark with deterministic fixtures and publish the report. Then run it once with `--live-bedrock` on Nova 2 Lite. Record task success, valid tools, supported claims, clarification, latency, and cost against the 90% and 95% targets. State pass or fail for each target. | merged, #349 and #353; partial: task success 17/33 (51.5%) original and 23/33 (69.7%) after the [post-hoc correction](../wiki/phases/posthoc-gold-20261003.md), 90% target FAILS; claims 98/100 (98%), 95% target PASSES; a fresh live batch is required to change the task result | 5 | `eval/results/`, `docs/EVALUATION.md`, `wiki/phases/evaluation-completion.md` | The report names the manifest hash, the model, the region, 138 slots, and per-target numerators and denominators. Depends on C1 to C3. |
| D2 | Evaluation item 29: update `docs/EVALUATION.md`, the completion page, the index, and the log with the final benchmark artifacts. | merged, #349 and #353 | 2 | the four files above | Every number in the docs matches a file under `eval/results/`. |
| D3 | Course deliverables: maximum eight-page paper in two columns, code repository, demo video, script, failure examples, and limitations. | merged, #361; partial: the supporting pack exists; the paper draft is in progress; the recorded video remains author work | 4 | `docs/course/`, assigned backlog and wiki records | Each outline section cites a repository artifact or source. The pack preserves original and post-hoc results and supports the author's own writing. |
| D4 | Plaid Sandbox live evidence: run `/transactions/sync` against Sandbox, serialize item syncs, apply changes and cursor atomically, and record posted and pending grocery spend. Last feature by decision. | paused | 5 | `backend/app/services/plaid_sync.py`, tests, `wiki/log.md` | A Sandbox run records posted and pending cents with the `plaid_sandbox` label. No real account. |
| D5 | Restricted hosting for the owner and invited users: ECS Fargate, RDS PostgreSQL, Secrets Manager, CloudWatch, Bedrock. | merged, #337 to #381 hosting stack; partial: source, preflight CLI, and runbook are on `main` under [decision 0019](../wiki/decisions/0019-invitation-only-hosting.md); nothing is deployed; two synth findings (fixed availability zones, non-root nginx) are open; hostname, ACM certificate, and deployment credentials await owner input | 5 | `infra/` | The owner MUST confirm every mutating AWS step first. The deployed stack limits access to the owner and invited users and answers one chat turn with live Bedrock and the deployed label. |

D1 retains the original 17/33 task result and 98/100 bounded-claim result.
The separate [post-hoc record](../wiki/phases/posthoc-gold-20261003.md)
rescores the exact saved observations with corrected F04/F05 final-turn gold.
Six tools assessments change. Task success becomes 23/33 (69.7%), with ten
failed and zero unassessed. The 90% target still FAILS. Claims and the 0/33
no-tool result stay unchanged. No scoring code or allowed outcomes change.
This is not a fresh batch, model retest, or independent benchmark.
A failed assessment alone does not establish a model or application defect.

D5 accepts shared demo access under decision 0019. Invitees share one application user.
The proposed design uses an authenticated HTTPS edge with administrator-created Cognito users,
private ECS tasks, retained isolated RDS with verified TLS, separate secrets, and narrow roles.
Manual budget defaults are USD 100 monthly and a USD 40 plan cap.
The owner-entered monthly limit remains the whole budget.
Source, preflight CLI, and runbook are merged on `main`.
The owner MUST confirm every mutating AWS step first, including users and invitations.
No AWS resources, users, or invitations have been created.
Hostname, ACM certificate, and deployment credentials await owner input.
D4 remains paused; live Instacart remains parked.
Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Part 3. Items that need no writer

- **GitHub Actions billing.** Every workflow run on `main` is refused since 2026-10-04 because the account spending limit or payment failed. The owner restores billing, then reruns the latest workflows on `main`. Local gates substitute until then.
- **Secret scanning and push protection.** A GitHub repository setting. The owner turns it on. The API reports it disabled on 2026-10-04.
- **Renew the AWS MFA session** before the next live test. Owner action.
- **Instacart handoff.** Parked until the Instacart Developer Platform reopens. C4 builds the flow against a fixture only.
- **Health-era Phases 4 to 9** in `project-plan.md`. Historical. Do not resume.
- **Comparison tool** from decision 0012. Build only after a measured need.

## Part 4. Suggested order

1. Done: A1 to A7, B1 to B6, C1 to C4, D2.
2. Owner: restore GitHub Actions billing; turn on secret scanning.
3. D5 follow-ups from the integrity check: fixed availability zones on both
   hosting stacks, and a non-root nginx container on port 8080. Then the
   owner supplies hostname, certificate, and credentials and confirms each
   mutating step in [docs/HOSTED_DEMO.md](HOSTED_DEMO.md).
4. D1: the 90% task target fails at 23/33. A failure analysis of the ten
   failed slots drives prompt or tool changes, each proven with fixture tests
   before one fresh live batch on Nova 2 Lite.
5. D3: the author finishes the paper from the draft under `docs/course/paper/`
   and records the video.
6. Integrity findings in order: typed diet-conflict error over HTTP, per-run
   queue isolation for the P05 duplicate check and the host Floci port in the
   endpoint allowlist, worker publish latency, Plaid write grants.
7. Keep D4 paused.
