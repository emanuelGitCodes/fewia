# Log

Append-only. Newest entry last. Do not edit or delete an entry.

## 2026-08-31 — Plan approved

The user approved the FEWIA build plan: ten phases, real Bedrock from
day one, frontend after the MVP checkpoint, private GitHub repo with
stacked PRs. The plan lives in `project-plan.md`. Decisions 0001–0003
record the choices.

## 2026-08-31 — Phase 0 complete

Bootstrapped the repo: git + private GitHub repo, `CLAUDE.md`, six
agents in `.claude/agents/`, `docs/DELEGATION.md`, and the seeded
knowledge graph (69 nodes, 9 communities). Details in
[phases/phase-0.md](phases/phase-0.md).

## 2026-08-31 — Graph copied to graphify-hub

Copied `graphify-out/graph.json` to
`~/GitHub/graphify-hub/out/fewia.graph.json`, next to the graphs from
other projects. The local copy stays for `/graphify query`.

## 2026-08-31 — Wiki created

Adopted the llm-wiki pattern (Karpathy gist) to record work and
decisions: `wiki/` with schema, index, this log, four decision pages,
and the Phase 0 record. `CLAUDE.md` now requires agents to maintain it.

## 2026-08-31 — project-plan.md marked Phase 0 complete

Added a status banner and a Phase 0 completion note to
`project-plan.md` so an executor starts at Phase 1. Closes the open
item in [phases/phase-0.md](phases/phase-0.md).

## 2026-08-31 — Phase 1 complete

Shipped the skeleton as four stacked branches: Compose plus `/healthz`,
the six SQLAlchemy models, the first Alembic migration, and the GitHub
Actions workflow. `docker compose up` serves HTTP 200 on `/healthz`,
`alembic upgrade head` builds the six tables of MVP doc §4 on a clean
database, and ruff, mypy, and pytest pass. CI stays unproven until the
user pushes. Details in [phases/phase-1.md](phases/phase-1.md).

## 2026-08-31 — Phase 1 merged to main

Pushed the four Phase 1 branches and opened pull requests #1 to #4. CI
ran for the first time and passed. The stack then merged into itself,
not into `main`: only #1 reached `main`, because each child pull
request kept its parent branch as its base. Pull request #5 corrected
the state and put all four work items on `main` at `82cbd70`. CI passed
again on `main`. A clean rebuild served HTTP 200 on `/healthz`, built
the six tables, and passed 9 tests. The four `feat/phase1-*` branches
are deleted, local and remote. Details in
[phases/phase-1.md](phases/phase-1.md).

## 2026-08-31 — project-plan.md marked Phase 1 complete

Moved the status banner to Phase 2 and added a Phase 1 completion note
to `project-plan.md`, so an executor does not rebuild the skeleton.

## 2026-08-31 — Phase 1 cleanup

Closed the three review findings on the Phase 1 skeleton: uvicorn now
reloads in Compose so the bind mount takes effect, CI push runs only on
`main`, and revision `0002` adds `uq_predictions_run_user_date` on
`predictions`.

## 2026-08-31 — Decision 0005: human-gated agent learning

Recorded how the agents learn: facts in the wiki, behavioral lessons
through dedicated agent-file PRs, mechanical rules as hooks. Added the
retro step to tech-lead, the rule to `CLAUDE.md`, and the layer guide
to `docs/DELEGATION.md`. Decision:
[decisions/0005-human-gated-agent-learning.md](decisions/0005-human-gated-agent-learning.md).

## 2026-08-31 — Decision 0006: Codex writes, Claude verifies

Adopted the writer/verifier split: Claude drives Codex through
`codex exec`, verifies the diff independently, and reports findings
until they close. `AGENTS.md` now binds Codex to the repo rules.
Decision:
[decisions/0006-codex-writes-claude-verifies.md](decisions/0006-codex-writes-claude-verifies.md).

## 2026-08-31 — Phase 2 synthetic data stack

Added versioned records, a seeded generator, a PostgreSQL loader, and a
CLI. With seed 42, 90 days, and end date 2026-06-30, the loader writes
4 users, 360 finance rows, 360 environment rows, and 341 health rows.

## 2026-09-01 — Phase 2 merged to main

Pull requests #10, #11, and #12 put the synthetic data stack on `main`
at `4e47640`. CI passed on each pull request and on `main`. Two runs of
`python -m app.synth --seed 42 --days 90` wrote identical rows, so the
Phase 2 check holds. Codex wrote the code and Claude verified it
through three rounds of findings. Mutation testing found two defects
that ruff, mypy, and the tests all passed: the loader left the `users`
identity sequence behind, and `--end-date` defaulted to `date.today()`.
Merging #11 with `--delete-branch` deleted the base of #12 and closed
it; recovery restored the branch and retargeted #12. Details in
[phases/phase-2.md](phases/phase-2.md).

## 2026-09-01 — Synthetic environment generator coverage

Added aggregate tests for profile-day rows, stable location types,
venue-count variation, and nonnegative integer counts.

## 2026-09-01 — Decision 0007: evidence ID format

Locked the `evidence_id` string before Phase 3 tools use it. A whole
calendar month keeps the `health:user-1:2026-08` shorthand from the MVP
plan. Every other range uses `health:user-1:2026-07-15..2026-08-04`.
`build_evidence_id` in `backend/app/tools/base.py` is the only writer.
Decision: [decisions/0007-evidence-id-format.md](decisions/0007-evidence-id-format.md).

## 2026-09-01 — Compare evidence preserves both periods

Updated `compare_periods` to sort and retain both evidence spans. Each
period summary now cites its health and finance values separately.
Comparison warnings now identify their period and domain.

## 2026-09-01 — Tool contract fixes B

Closed five tool-contract defects on top of the compare evidence fix.
`get_health_context` now returns `average_intensity_minutes`, so the
`null_fields` warning names no field the caller cannot read. The new
`average_sample_counts` field reports how many non-null values stand
behind each nullable average, so a 1-day average no longer looks like a
30-day one. The prediction stub warning uses the new `stub_result`
code. A FastAPI validation 422 now returns the `error` envelope with
the code `validation_error` and keeps the field list under
`error.detail`. `build_compare_evidence_id` in
`backend/app/tools/base.py` replaces the string surgery in
`compare.py`, and one private helper owns the span format. Five
mutations, one per defect, each failed a test. Codex wrote the code and
Claude verified it. Decisions:
[0006](decisions/0006-codex-writes-claude-verifies.md),
[0007](decisions/0007-evidence-id-format.md).

## 2026-09-01 — Phase 3 complete

The Phase 3 pull requests put the deterministic tools and FastAPI endpoints
on `main` at `fb5c3c8`. PostgreSQL 16 verification returned live August 2026
data with the required evidence fields and error envelope. Details in
[phases/phase-3.md](phases/phase-3.md).

## 2026-09-01 — Compare evidence ID direction

Compare evidence IDs now record period A first and period B second. The
ID identifies the comparison direction and matches the signs of the
returned step and spending deltas. Decision:
[0007](decisions/0007-evidence-id-format.md).

## 2026-09-02 — Model run metadata columns

`model_runs` could not hold the output of a Phase 4 training run.
Migration `0003` adds eight columns: `model_version`, `random_seed`,
`sample_size_train`, `sample_size_test`, `feature_list`,
`split_method`, `missing_data_policy`, and `baseline_mae`. MVP section
7 requires a run to disclose each one. The columns sit on `model_runs`
instead of a second `model_run_details` table, because the table is
small and Phase 6 reads the values in one query. `feature_list` uses
`sqlalchemy.JSON`, not `JSONB`, because the test suite runs on SQLite
and the API runs on PostgreSQL. `model_version` is unique and not null;
a later item writes the value and fixes the format. The names differ
from the tech-lead proposal: `random_seed` replaces `seed`, two count
columns replace three, and `missing_data_policy` is new. Later Phase 4
items MUST use the merged names. PostgreSQL 16 verification applied the
migration, returned the table to nine columns on downgrade, and
restored it. Two mutations failed the new tests. PR #32.

## 2026-09-02 — Machine learning foundation

The backend held no ML dependency and no `app/ml/` package. This work
item adds `scikit-learn`, `pandas`, `numpy`, and `joblib` as runtime
dependencies, and `pandas-stubs` to the dev group. `pandas` and `numpy`
are declared directly, because the feature code imports both. A mypy
override covers `sklearn.*` and `joblib.*`, which ship no type
information. `pandas` and `numpy` are typed and get no override. The
`app/ml/` package holds one docstring and no exports. The `.gitignore`
entry `backend/artifacts/` ignored the artifact directory itself, so a
fresh clone gave training no place to write. The entry now ignores the
contents and keeps `backend/artifacts/.gitkeep`. `pandas` resolves to
3.0.5, because no dependency states a floor. PR #33.

## 2026-09-03 — Plaid and Instacart repository update plan

Added a reference plan for the proposed pivot to a budget-aware grocery
planning agent. The plan preserves the existing course sources and requires
Plaid and Instacart access proof before implementation. It defines the target
architecture, data model, security boundary, evaluation, stacked pull-request
order, MVP checkpoint, and legacy cleanup gates. No application code changed.

## 2026-09-05 — Grocery bot development agent roles

Updated the project agent team for Plaid, Instacart, real Bedrock, and Floci.
Added AI, provider, catalog, database, reliability, security, evaluation, and
documentation roles. Preserved `ml-dev` as a compatibility role without health
training. Each role selects `gpt-5.6-luna` with `xhigh` effort. The shared
project brief records local web chat and sample-price estimates. The team
guide defines file ownership, parallel work, and independent review boundaries.
Agent configuration is complete before application implementation starts.

## 2026-09-05 — Grocery request and Floci foundation

Started the grocery implementation from merged main at `132614c`. Added
strict meal-request contracts and the sample-price notice. Added Floci 2.0.1
with a pinned digest and persistent local storage. The bootstrap creates two
queues, their dead-letter queues, and an evaluation bucket. It rejects remote
endpoints before client creation. Ruff, format checks, strict app mypy, and
188 tests passed. One existing Starlette/httpx warning remains. Live local
checks passed repeated provisioning, queue round trips, S3 readback, and
restart persistence. An in-memory endpoint mutation failed the guard test.
Claude found no correctness defects; its typing and formatting findings were
corrected. Provider credentials are not configured. Worker execution, provider
adapters, budgeting, Bedrock orchestration, and web chat remain future work.

## 2026-09-05 — Durable jobs and outbox schema

Added jobs and job_outbox through migration 0004. The schema enforces request
idempotency scope, valid states, nonnegative attempts, and one outbox row per
job. Ruff, formatting, strict mypy, and 205 tests passed. Claude reviewed the
schema without blocking findings and independently ran the preceding 201-test
snapshot. Isolated PostgreSQL checks passed clean upgrade, upgrade from 0003,
downgrade, and ORM agreement. The downgrade preserved the existing synthetic
user fixture. The running development database was not migrated.

## 2026-09-05 — Atomic job submission

Added create_job to persist a job and outbox record in the caller's transaction.
Scoped request keys reuse identical jobs and reject different canonical JSON.
Savepoints handle concurrent inserts without committing caller state. Ruff,
formatting, strict mypy, and 228 tests passed with isolated PostgreSQL tests
enabled. Claude independently passed 226 tests plus the two opt-in PostgreSQL
checks and found no blocking defects. A memory-only canonicalization mutation
failed the conflict test. Documented READ COMMITTED isolation and the caller's
rollback and payload-sanitization responsibilities. Queue publication and
leased worker execution remain separate slices.

## 2026-09-05 — Outbox publication to Floci SQS

Added a bounded outbox publisher and local-only SQS adapter. PostgreSQL row
locks let parallel publishers select separate entries. Messages contain only
job IDs. Publication markers commit after successful sends; failed entries
remain pending without blocking later entries in the same batch. Root checks
passed 250 tests with isolated PostgreSQL enabled. Claude independently passed
247 tests plus the publisher PostgreSQL check and found no defects. Live Floci
checks published two synthetic jobs, verified their messages and markers, then
published zero on a repeat run. PR 39 carries the earlier submission code to
main because PR 38 merged into its feature base. Worker execution remains next.

## 2026-09-06 — Development writer policy and worktree lease

Added model routing for Grok 4.6 medium, Spark at its CLI default effort, and
Luna xhigh. Explicit models run first; model-only assignments forbid fallback.
Added a worktree lease with an orphan-group check. Policy and lease tests pass.
This is the first local slice of the development supervisor stack. No saved
checkout or native session configuration has been activated.

## 2026-09-06 — Development CLI event classification

Added structured provider-error and tool-lifecycle parsing. Unknown errors
stop. Tool output cannot trigger quota fallback. A successful final turn clears
an earlier recovered error. Grok 4.6 medium completed a no-tool compatibility
call and a read of an isolated synthetic fixture. The latter verified native
tool_call and tool_call_update events. Spark completed a no-tool call with no
reasoning override. Provider quota exhaustion remains simulated evidence.
