# FEWIA feature backlog

This document records the feature backlog and its state on `main` at
`26f6b0e` (2026-10-07, after #401 to #419). The historical built-feature
table keeps the earlier snapshot. The merged-work tables record merged work,
the [first benchmark](../wiki/phases/benchmark-20261003.md), and the
[fresh benchmark](../wiki/phases/benchmark-20261005.md) of 2026-10-05.
A merge does not imply deployment or release certification.
The senior coordinator verifies each item after the writer reports.

The [integrity check](../wiki/phases/integrity-20261004.md) of 2026-10-04
exercised every merged subsystem on the local stack. Its follow-up loop
merged #384 to #390 the same day. Its findings merged as E1 to E4 in #392
to #395. The fresh benchmark of 2026-10-05 (#398) measured the fixes. Its
eight failed slots are the work items in Part 2, Tier G. #399 and #408
address two of the three failing scenarios. Only G3 measures them. #401 to #417 added the agent
hooks under [decision 0020](../wiki/decisions/0020-shared-hooks-for-every-agent-cli.md).
The [final record](../wiki/phases/backlog-final-20261003.md)
and the [hosting snapshot](../wiki/phases/hosting-preparation-20261003.md) are
dated checkpoints from before the merges.

## Handoff to `gpt-6-astra`

This section is for a coordinator session that starts from this file with no
other context. Read it first. Read Part 2 next. Parts 1 and 3 are the record.

**Role.** The coordinator designs, delegates, verifies, and publishes. It
MUST NOT write application, test, or infrastructure code. It MAY edit prose,
`wiki/`, `docs/`, and agent configuration. Writers run through
`dev_supervisor`, which starts each writer with `FEWIA_WRITER=1`. The hooks in
`.claude/hooks/` enforce these rules in Claude Code, Codex, and Grok. A Codex
session MUST trust the hooks once with `/hooks` before the first edit.

**Binding files, in precedence order.** `AGENTS.md`, then
[docs/DELEGATION.md](DELEGATION.md), then `.codex/TEAM.md`, then
`.codex/project-context.md`, then [docs/DEV_SUPERVISOR.md](DEV_SUPERVISOR.md).
[.claude/README.md](../.claude/README.md) maps the hooks, agents, skills, and
ledgers.

**Writer ladder.** Every writer run MUST pass `--only --model MODEL --effort
LEVEL` with one rung from the ladder in [docs/DELEGATION.md](DELEGATION.md):
`gpt-6-luna xhigh`, `grok-4.6 low`, `grok-4.6 medium`, `gpt-6.1-sol medium`,
`gpt-6.1-sol high`. `gpt-6-astra` is not a rung. The owner MUST add it to the
ladder before a `dev_supervisor` run names it as a writer. Codex Spark and
Sonnet do not write code.

**Commands.**

```bash
docker compose up -d
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
cd backend && uv run pytest
cd frontend && npm run lint && npm test && npm run build
```

The gates need a dedicated PostgreSQL server. Start a throwaway `postgres:16`
with database `fewia_eval`. The shared Compose server fails the fixture guard.
The gates print `LINES n/1000`.

**Definition of done.** The diff matches the brief, the added code lines are
1000 or fewer, the gates pass in the coordinator's own run, and the review
command returns `APPROVE` on the head SHA. A writer report is a claim until
the diff and the gates confirm it.

**External writes.** A push, a pull request, a merge, an AWS change, and a
provider write each need the owner's confirmation. Under Codex the hook
denies them and the owner runs the command.

**Open writer work.** No code item is ready for a writer. G3 is a live
batch and waits on the owner. G4 is optional. Everything else in Part 2
waits on an owner decision, owner input, or the author. Do not start Plaid, live
Instacart, hosting deployment, or the course paper.

**Owner decisions outstanding.** The A02 gold alignment, the
refusal-override lever, GitHub Actions billing, and the repository secret
scanning setting. See "Owner decisions" in Part 2 and Part 4.

**Loop state.** Ledgers live in `.claude/loop/<slug>.md`. The ledger State
column for a tier S item MAY lag this file. This file wins for the backlog
state. The ledger wins for round counts, worktrees, and tokens.

Sources: `PRODUCT.md`, `.codex/project-context.md`, `project-plan.md`,
`docs/EVALUATION.md`, `docs/GROCERY_VERIFICATION_PLAN.md`, the pages under
`wiki/phases/`, the decisions under `wiki/decisions/`, the ledgers under
`.claude/loop/`, and the code.

## Rules for the writer

- One pull request per item. A pull request MUST NOT add more than 1000
  code lines. Tests and docs do not count. The owner raised the cap from 150
  on 2026-10-06 because GitHub Actions is out of minutes. Split a larger
  item into a stack and name the parent in each body.
- Base independent branches on `main`. Base each stacked child on its parent.
  Writers MUST NOT merge. The coordinator needs explicit merge authorization.
- The coordinator or junior runs the gates before reporting:
  `uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main`.
  The gates need a dedicated PostgreSQL server. The shared Compose server
  fails the fixture guard.
- Prose follows ASD-STE100. Requirement words are MUST, MUST NOT, SHOULD,
  SHOULD NOT, and MAY.
- Do not start Plaid live work, live Instacart handoff, or any health-era
  phase. C4 permits the handoff button against a fixture provider only.
- Do not claim a live-provider result from a fixture run. Label evidence
  as fixture, emulator, Sandbox, live, or deployed.
- Do not write model prose into an evaluation record. Do not draft the
  course paper. The owner closed both paths on 2026-10-04.

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
| Local stack | React and TypeScript chat, FastAPI, PostgreSQL, worker, Floci SQS and S3, nginx, in Docker Compose. 7 migrations. 13 routes across 6 routers plus `/healthz`, every route tested. The web container runs as the unprivileged nginx user on port 8080. | `docker compose up -d`; local gates green on `main` at `b21a854` per the integrity page: backend 9074, hosting 1778, frontend 492, tooling 359; GitHub CI blocked by Actions billing since 2026-10-04 |
| Chat loop | Bedrock `LLMProvider` with tool calling, 8 model turns and 3 planner revisions per job, refusal parser, typed unsupported-diet, unsupported-ingredient, and `diet_conflict` errors, read-only `get_budget_summary`. Every `plan_groceries` schema field carries a description. The system prompt defines a purchase narrowly and passes an unknown restriction term verbatim to the tool. Only an order, checkout, payment, or retailer link gets the purchase refusal. A buy or rebuy request goes to the shopping list. A follow-up turn carries the earlier plan's sorted catalog ingredient ids as `previous_ingredient_ids`; the server reads them from the previous job. | `backend/app/agent/`; live Nova 2 Lite chat verified 2026-09-08; #387 to #390; #399; #408 |
| Planning | 40-meal catalog `sample-prices-v2`, 1 to 3 meals, 1 to 8 servings, pantry, exclusions, diet validation, shared-ingredient aggregation before package rounding, labeled sample prices. | `backend/app/domain/`, decision 0017 |
| Budget | Manual spending source as default. User limit minus posted spending, clamped to zero. Pending cents separate. Stale-spending rule. Explicit plan cap. | decision 0016, `backend/app/services/` |
| Templates | `POST /grocery/templates` with six presets filtered by budget, diet, pantry, and exclusions. Frontend meal-ideas picker. | moderate backlog item 15 |
| Nutrition | USDA FoodData Central facts per meal and per plan. Live Kroger price on the chat read, never stored. | decisions 0010 and 0016; proposal D6 |
| Jobs | PostgreSQL jobs, outbox, leases, duplicate-delivery handling, dead letters, evidence revisions. Floci queues `fewia-sync` and `fewia-agent` with dead-letter queues, bucket `fewia-eval`. | `backend/app/services/`, `infra/floci_bootstrap.py` |
| Providers | `BedrockConverseProvider` for us-east-1 and us-west-2, active only when `FEWIA_BEDROCK_MODEL_ID` is set. `PlaidSandboxProvider` and `sync_item`. `InstacartDevelopmentProvider` with `POST /grocery/handoffs`, `GET`, and `/retry`, hidden in the UI unless `instacart_configured`. | `backend/app/providers/`, `backend/app/api/handoff.py` |
| Frontend | App, BudgetForm, Conversation, ChatPanel, ChatWorkspace, Estimate, Nutrition, TemplatePicker. Manual-plan to chat context transfer. | `frontend/src/`, 492 tests |
| Evaluation components | 60 `evaluation_*.py` modules plus `evaluate.py`: inputs, manifest, capture, adversarial scenarios, fault provider, plan facts and scoring, claim scoring, outcome scoring, refusal actions, telemetry, cost, matrix, summaries, model and no-tool observers, duplicate and handoff and refresh drivers, SQLite evidence, JSON output. | `backend/app/evaluation_*.py` |
| Legacy runner | `run_evaluation` scores the deterministic groups: 42 scored, 48 unassessed. | `backend/app/evaluation_runner.py` |
| Live benchmark | Two 138-slot live batches on Nova 2 Lite with archived artifacts and SHA-256 manifests. The fresh batch reports task 25/33 and claims 109/112. Release is not certified. | `eval/results/artifacts/benchmark-20261003/`, `eval/results/artifacts/benchmark-20261005/` |
| Hosting | CDK stacks for ECS Fargate, RDS PostgreSQL, Secrets Manager, CloudWatch, Bedrock, and a Cognito edge. Fixed availability zones. Preflight CLI and runbook. Nothing deployed. | `infra/hosting/`, `docs/HOSTED_DEMO.md`, decision 0019 |
| Tooling | `dev_supervisor` writer, gates, review, usage, lease. The gates print `LINES n/1000`. Tooling CI. Migration drift check. Dependency audits. ESLint. Gitleaks in pre-commit. | `dev_supervisor/`, `.github/workflows/`; #407 |
| Agent hooks | One hook set in `.claude/hooks/` for Claude Code, Codex, and Grok. The senior edit guard denies code in every checkout and allows a writer with `FEWIA_WRITER=1`. Bash guard, pull request size, done, and agents checks, append-only wiki log, prose lint. The pull request hooks read the checkout from the hook input. | `.claude/README.md`, decision 0020; #401 to #405, #410 to #417; `tests/supervisor/test_edit_guard.py`, `tests/supervisor/test_pr_hooks.py` |
| Repair loops | Nine review findings from the evaluation PRs repaired and merged. Seven integrity follow-ups merged. Four integrity findings merged. Two benchmark follow-ups merged. | #302 to #312; #384 to #390; #392 to #395; #399; #408 |

## Part 2. Open work, ranked from easiest to hardest

Difficulty: 1 is a one-file change with a known pattern. 5 is a new
subsystem with a live provider or a contract that other code depends on.

Each item names the acceptance check the coordinator runs. The writer MUST
make that check pass. Items E1 to E4 come from the integrity findings 5, 6,
4, and 7. Items F1 to F4 continue the D tier. Items G1 to G4 come from the
eight failed slots of the fresh benchmark and the G2 follow-up.

### Tier E. Integrity findings

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| E1 | Add the host Floci endpoints `http://127.0.0.1:4567` and `http://localhost:4567` to `ALLOWED_ENDPOINTS`. Compose maps the host port 4567 to the container port 4566, so the benchmark cannot run from the host with `--local-services` today. | merged, #393 | 1 | `backend/app/providers/local_sqs.py`, `backend/tests/test_local_sqs*.py`, `backend/tests/test_evaluation_cli_config.py` | With `FEWIA_EVALUATION_FLOCI_ENDPOINT=http://127.0.0.1:4567`, the CLI accepts `--local-services`. A non-loopback endpoint still raises `Invalid evaluation CLI input`. No other endpoint joins the set. |
| E2 | Record the Plaid grant rule. `RUNTIME_GRANTS` gives SELECT only on `plaid_items` and `plaid_transactions`. The paused sync service writes them. The hosted app task runs no sync worker. | merged, #392; see the [finding 6 disposition](../wiki/phases/integrity-20261004.md#finding-6-disposition-2026-10-05) | 1 | `wiki/log.md`, `docs/HOSTED_DEMO.md`, `backend/app/runtime_database_policy.py` comment if needed | The wiki states that the runtime role stays SELECT-only on the Plaid tables until D4 resumes, and that D4 MUST widen the grants with a policy test before any Sandbox run. No grant changes now. Prose only. |
| E3 | Isolate the P05 duplicate-delivery slots from a running worker. Today they share the global `fewia-agent` queue and fail when another consumer is up. | merged, #394 | 3 | `backend/app/evaluation_duplicate.py`, `backend/app/providers/local_sqs.py`, `backend/tests/test_evaluation_duplicate.py` | With a worker consuming `fewia-agent`, each P05 slot either passes on its own queue or reports `unassessed` with a named reason. No P05 slot fails because of a foreign consumer. Fixture runs still call no provider. |
| E4 | Publish the outbox off the long-poll path. `run_worker` calls `publish_pending` once per loop and then blocks up to 10 s in `WaitTimeSeconds` on an empty queue, so a 50 ms job takes 0.5 to 11 s. | merged, #395 | 3 | `backend/app/worker.py`, `backend/app/services/outbox_publisher.py`, `backend/tests/test_worker.py` | With an empty queue and one pending outbox row, the row publishes within 1 s. The stop event still ends the loop within one wait. The backoff and `PublicationError` tests still pass. Duplicate publication stays impossible. |

### Tier F. Live evidence and release work

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| F1 | D1 fresh live batch: run the 138-slot benchmark once more with `--live-bedrock` on Nova 2 Lite after the four application fixes in #387 to #390. The analysis estimates 27 to 31 of 33; the 90% target needs 30. Depends on E1 for a host run, or runs inside the Compose network. | done, 2026-10-05: task 25/33 (75.8%), 90% target FAIL; claims 109/112 (97.3%), 95% target PASS; see the [benchmark record](../wiki/phases/benchmark-20261005.md) | 4 | `eval/results/`, `docs/EVALUATION.md`, `wiki/phases/evaluation-completion.md`, `wiki/log.md` | The report names the manifest hash, the model, the region, 138 slots, and per-target numerators and denominators. Task success states pass or fail against 90%. The original 17/33 and post-hoc 23/33 records stay unchanged. |
| F2 | D5 deployment: the owner supplies the hostname, the ACM certificate, and the deployment credentials, then confirms each mutating step in [docs/HOSTED_DEMO.md](HOSTED_DEMO.md). Source, preflight CLI, and runbook are on `main`. Hosting findings F1 and F2 are closed. | blocked on owner input | 5 | `infra/`, `docs/HOSTED_DEMO.md`, `wiki/log.md` | The deployed stack limits access to the owner and invited users and answers one chat turn with live Bedrock and the deployed label. Every AWS mutation has an owner confirmation in the log. |
| F3 | D3 course deliverables: the author writes the paper and records the video from the pack under `docs/course/`. The course rule forbids a model-generated report. No draft exists in the repository. | author work | none | `docs/course/` as support only | The author owns the acceptance. The pack cites original and post-hoc results and does not establish completion. |
| F4 | D4 Plaid Sandbox live evidence. Last feature by decision. Depends on the grant widening recorded in E2. | paused | 5 | `backend/app/services/plaid_sync.py`, `backend/app/runtime_database_policy.py`, tests, `wiki/log.md` | A Sandbox run records posted and pending cents with the `plaid_sandbox` label. No real account. |

### Tier G. Fresh benchmark follow-ups

The fresh batch failed eight slots: A02 three times, F04 three times, and F02
twice. G1 addressed F02. G2 addressed F04. G3 measures both. A02 waits on the
owner decision below.

| ID | Item | Status | Difficulty | Owned files | Acceptance check |
|---|---|---|---|---|---|
| G1 | Narrow the purchase refusal so a buy or rebuy request reaches the planner (F02). On "Buy the beans again." the model returned the purchase refusal. | merged, #399 | 2 | `backend/app/agent/chat_loop.py`, `backend/tests/test_chat_loop.py` | Targeted live checks on Nova 2 Lite: F02 5/5 on the branch and 1/5 on `main`; A04 5/5; X03 14/15. Small samples. The 90% target is not measured until G3. |
| G2 | Give the follow-up turn the earlier plan's ingredient ids (F04). The owner chose option B on 2026-10-06. `plan_ingredient_ids(plan)` in `chat_context.py` returns the sorted catalog ids. `build_messages`, `run_chat`, `ChatJobInput`, and `load_chat_context` carry `previous_ingredient_ids`. The server reads the ids from the previous job's plan; the client cannot send them. The evaluation path carries the ids across turns. | merged, #408; the live F04 check did not run; G3 measures it | 3 | `backend/app/agent/chat_context.py`, `backend/app/agent/chat_loop.py`, `backend/app/api/chat.py`, `backend/app/services/chat_job.py`, `backend/app/evaluation_model.py`, `backend/app/evaluation_model_turn.py`, tests | Gates passed and the review returned `APPROVE` on `b06f8e0`. The 90% target is not measured until G3. |
| G3 | Fresh live batch after G1, G2, and the A02 decision. Runs the 138-slot benchmark once more with `--live-bedrock` on Nova 2 Lite. The reachable result is 30/33 while A02 fails. The `f1-live` ledger holds the wrapper, the local services, and the expired-session guard. | not started; depends on the A02 decision; the owner renews the Bedrock session with `infra/bedrock_session.py` | 4 | `eval/results/`, `docs/EVALUATION.md`, `wiki/phases/`, `wiki/log.md` | Same as F1. The report names the manifest hash, the model, the region, 138 slots, and per-target numerators and denominators. Task success states pass or fail against 90%. Earlier records stay unchanged. F02 and F04 each pass 3/3. |
| G4 | Align the API and evaluation paths after a no-plan turn. Through the API, a follow-up after a turn with no plan sends `previous_ingredient_ids` as null. The evaluation path keeps the last known ids. F04 is a two-turn scenario and is not affected. | open; no owner; build only if a three-turn scenario needs it | 2 | `backend/app/services/chat_job.py`, `backend/app/evaluation_model_turn.py`, tests | Both paths return the same ids for the same turn sequence. A fixture test covers a plan turn, a no-plan turn, and a follow-up. |

### Owner decisions, no writer until decided

- **A02 gold alignment (F3-A).** Scenario A02 injects provider text that asks
  the model to conceal a vegan conflict. The gold expects a typed planner
  conflict. The live model clarified once and planned twice. A gold rewrite
  changes the evidence contract, so the owner decides. While A02 fails, the
  task result cannot exceed 30/33.
- **Refusal-override loop lever.** Rejected by the owner on 2026-10-08. The
  chat loop MUST NOT force a planner call after a model refusal. The model
  selects the tools. G1 and G2 cover the affected slots.

## Part 3. Merged work record

### Tier A. Small, isolated, deterministic

| ID | Item | Status | PR |
|---|---|---|---|
| A1 | Refresh the two stale ledger State columns. | merged | #315 |
| A2 | Close or record the Phase 1 to 3 open items. | merged | #317 |
| A3 | `pip-audit --no-deps` and Ruff `I` and `E501`. | present before this backlog | none |
| A4 | Decision 0018: retain stored Spoonacular totals and retired health tables. | merged | #325 |
| A5 | Quantity-scaled nutrition totals. | present before this backlog | none |
| A6 | Supervisor skip counter reset and lease release on a pre-spawn crash. | present before this backlog | none |
| A7 | Unit tests for `usePolledJob.ts` and `spoonacular_catalog.py`. | merged | #314 |

### Tier B. Bounded code with a fixed contract

| ID | Item | Status | PR |
|---|---|---|---|
| B1 | Grok fallback for the review command. | merged | #316 |
| B2 | Independent review of the nutrition compatibility change. | merged | #320 |
| B3 | Delegation-efficiency item 09: tier S documentation pilot. Partial: two items, no percentage claim. | merged | #331 |
| B4 | Browser checks from the verification plan. Broader browser scope stays open. | merged | #327 |
| B5 | `render_report(output) -> str` in `evaluation_markdown.py`. | merged | #322, #332 to #336 |
| B6 | Review fallback matcher on `code` and `message`. | merged | #324 |

### Tier C. New contracts that other code depends on

| ID | Item | Status | PR |
|---|---|---|---|
| C1 | `run_slot` dispatch in `evaluation_dispatch.py`. | merged | #328, #329 |
| C2 | `run_evaluation_batch` with 138 slots and a journal. | merged | #338 |
| C3 | `python -m app.evaluate` CLI with `--live-bedrock` opt-in. | merged | #339, #341 |
| C4 | Handoff button flow against a fixture provider. | merged | #323, #327 |

### Tier D. Live evidence and release work

| ID | Item | Status | PR |
|---|---|---|---|
| D1 | 138-slot benchmark, fixture and one live batch. Task success 17/33 original and 23/33 after the [post-hoc correction](../wiki/phases/posthoc-gold-20261003.md); 90% target FAILS. Claims 98/100; 95% target PASSES. Four application fixes from the failure analysis merged. The fresh batch (F1, #398) reports 25/33 and 109/112. Continues as G3. | partial | #349, #353, #387 to #390, #398 |
| D2 | `docs/EVALUATION.md`, completion page, index, and log updated with the benchmark artifacts. | merged | #349, #353 |
| D3 | Course supporting pack. The paper draft was deleted by owner decision. Continues as F3. | partial | #361 |
| D4 | Plaid Sandbox live evidence. Continues as F4. | paused | none |
| D5 | Restricted hosting source, preflight CLI, runbook, fixed availability zones, non-root nginx. Nothing deployed. Continues as F2. | partial | #337 to #381, #384, #386 |

### Integrity follow-ups, 2026-10-04

| PR | Change | Closes |
|---|---|---|
| #385 | Backlog, hosting README, decision 0019, runbook, and integrity page record the merged state | cosmetic findings |
| #384 | Both hosting stacks override `availability_zones` | hosting F1 |
| #386 | The web container runs as uid 101 on port 8080; edge and security groups follow | hosting F2 |
| #387 | Every `plan_groceries` schema field carries a description | D1 fix F4 |
| #388 | A diet conflict is a typed `diet_conflict` error on every path | integrity finding 1; D1 fix F3-B |
| #390 | An unknown restriction term passes verbatim to the tool; X03 gold expects the call | D1 fix F1 |
| #389 | The system prompt defines a purchase narrowly | D1 fix F2 |
| #391 | The wiki records the follow-up loop | none |

### Integrity findings and benchmark follow-ups, 2026-10-05

| PR | Change | Closes |
|---|---|---|
| #396 | Gitleaks in pre-commit and the `Secrets` workflow | secret scanning |
| #392 | The integrity page records the Plaid grant rule for D4 | E2 |
| #393 | The host Floci endpoints on port 4567 join the local endpoint set | E1 |
| #394 | Each P05 run creates, uses, and deletes a private Floci queue | E3 |
| #395 | The worker publishes the outbox on its own thread | E4 |
| #397 | The backlog records the merged E tier and secret scanning | none |
| #398 | The fresh live benchmark record and archive | F1 |
| #399 | Only an order, checkout, payment, or retailer link gets the purchase refusal | G1 |
| #400 | The wiki records #399 and the open F04 decision | none |

### Benchmark follow-ups and agent hooks, 2026-10-06 to 2026-10-07

| PR | Change | Closes |
|---|---|---|
| #401 | The `.claude/` map and the first three hooks: senior edit guard, Bash guard, pull request size | decision 0020 start |
| #402 | The pull request hooks: size, done, and agents checks | stack under #405 |
| #403 | The wiki log guard and the prose linter | stack under #405 |
| #404 | The gates, wiki-log, and worktree-cleanup skills | stack under #406 |
| #405 | The pull request hooks fail closed, read the base branch, and measure `HEAD` | none |
| #406 | The pull request cap is 1000 code lines in the backlog, the hook, and the OpenCode agents | cap change |
| #407 | The gates print `LINES n/1000` | followups-20261006 item 02 |
| #408 | The follow-up model context carries the earlier plan's ingredient ids | G2 option B |
| #409 | Closed without a merge; #418 carries the same wiki log entry | none |
| #410 | `dev_supervisor` starts writers with `FEWIA_WRITER=1`; the edit guard allows them and judges worktree paths | Grok writer denial |
| #411 | The edit guard judges a path in every checkout from `git worktree list` | cross-checkout edits |
| #412 | `stop()` retries a transient `EPERM` from `os.killpg` | none |
| #413 | `edit-targets.py` reads Codex `apply_patch` targets | Codex hooks, part 1 |
| #414 | `.codex/hooks.json` runs the `.claude/hooks/` scripts; a Codex patch cannot insert into the wiki log | Codex hooks, part 2 |
| #415 | Decision 0020 and the merged hook fixes in the wiki | none |
| #416 | `runbooks/durable-jobs.md` describes the running worker and the lease rule | runbook gap |
| #417 | The pull request hooks read the checkout from the hook input `cwd` | worktree pull request denial |
| #418 | The wiki records G2 option B and the gates label; replaces the closed #409 | none |
| #419 | `AGENTS.md` states the writer ladder rule instead of a default order | writer order conflict |

#402, #403, and #404 merged through their stack parents, so `main` holds no
merge commit for them. #409 closed without a merge. GitHub Actions did not
run on #401 to #419. Each merge rests on the local gates and the review
command.

Dropped by owner decision: item 10, sanitized model text per observed turn,
because the evidence rule forbids model prose; item 05, a model-drafted paper,
because the course rule forbids a generated report.

D1 retains the original 17/33 task result and 98/100 bounded-claim result.
The separate [post-hoc record](../wiki/phases/posthoc-gold-20261003.md)
rescores the exact saved observations with corrected F04/F05 final-turn gold.
Six tools assessments change. Task success becomes 23/33 (69.7%), with ten
failed and zero unassessed. The 90% target still FAILS. Claims and the 0/33
no-tool result stay unchanged. No scoring code or allowed outcomes change.
This is not a fresh batch, model retest, or independent benchmark.
A failed assessment alone does not establish a model or application defect.
The four fixes in #387 to #390 are measured by the fresh batch of
2026-10-05: 25/33. The #399 fix is proven with fixture tests and targeted live
checks only. The #408 fix is proven with fixture tests only. Only G3 measures
both against the target.

D5 accepts shared demo access under decision 0019. Invitees share one application user.
The design uses an authenticated HTTPS edge with administrator-created Cognito users,
private ECS tasks, retained isolated RDS with verified TLS, separate secrets, and narrow roles.
Manual budget defaults are USD 100 monthly and a USD 40 plan cap.
The owner-entered monthly limit remains the whole budget.
The owner MUST confirm every mutating AWS step first, including users and invitations.
No AWS resources, users, or invitations have been created.
Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Part 4. Items that need no writer

- **GitHub Actions billing.** Every workflow run on `main` is refused because the account spending limit or payment failed. The runs at 2026-10-05 01:15 UTC report "The job was not started because recent account payments have failed". No job started on #401 to #419. The owner restores billing, then reruns the latest workflows on `main`. Local gates substitute until then. Do not repair code because of a failed CI job.
- **Codex hook trust.** Each user MUST trust the hooks once with `/hooks` in an interactive Codex session. `dev_supervisor` writers and reviews run with `--ignore-user-config`, so project hooks do not load there.
- **Add `gpt-6-astra` to the writer ladder** in [docs/DELEGATION.md](DELEGATION.md) and `docs/DEV_SUPERVISOR.md` before a writer run names it. Owner decision.
- **Secret scanning and push protection.** Gitleaks runs in pre-commit and in the `Secrets` workflow since #396. The GitHub repository setting is separate. The owner turns it on. The repository API did not return the `security_and_analysis` field to this token on 2026-10-05, so the setting is unverified from the CLI.
- **Renew the AWS MFA session** before G3 and before any F2 step. Owner action. `infra/bedrock_session.py` renews it. The G3 wrapper exits 3 on an expired session before any provider call.
- **Instacart handoff.** Retired by [decision 0023](../wiki/decisions/0023-retire-instacart-adapter.md). The frozen suite keeps a fixture handoff scenario (P02).
- **Health-era Phases 4 to 9** in `project-plan.md`. Historical. Do not resume.
- **Comparison tool** from decision 0012. Build only after a measured need.
- **Broader browser scope** from B4. Open, no owner yet.

## Part 5. Suggested order

1. Done: A1 to A7, B1 to B6, C1 to C4, D2, hosting F1 and F2, integrity
   finding 1, D1 application fixes F1 to F4.
2. Done: E1 to E4 (#392 to #395) and gitleaks secret scanning (#396).
3. Done: F1 (#398). The fresh batch reports 25/33; the 90% target still
   FAILS. Eight slots failed: A02 three times, F04 three times, and F02
   twice.
4. Done: G1 (#399). F02 passes 5/5 in targeted live checks.
5. Done: G2 option B (#408) and the agent hooks under decision 0020 (#401 to
   #417).
6. Owner: decide the A02 gold alignment. Restore GitHub Actions billing. Turn
   on secret scanning. Add `gpt-6-astra`
   to the writer ladder if it writes code.
7. G3: the owner renews the Bedrock session, then the fresh batch runs. The
   reachable result is 30/33 while A02 fails, so the 90% target needs the A02
   decision too.
8. G4: build only if a three-turn scenario needs it.
9. F2: the owner supplies hostname, certificate, and credentials and confirms
   each mutating step in [docs/HOSTED_DEMO.md](HOSTED_DEMO.md).
10. F3: the author writes the paper and records the video.
11. Keep F4 paused. When D4 resumes, widen the Plaid grants first, as the
    finding 6 disposition requires.
