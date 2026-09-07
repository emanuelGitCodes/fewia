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

## 2026-09-06 — Bounded development process supervision

Added bounded process execution and process-group cleanup before handoff.
Silence requests inspection; it does not trigger fallback. Confirmation tokens
apply to one attempt and cannot override known tool activity or permission waits.
Tests cover silence, confirmed stalls, permissions, failed tasks, and stopping a
child before it writes. Workers cannot detach processes under the task contract.

## 2026-09-06 — Development supervisor workflow integration

Added the CLI entry point, role handoff, bounded fallback, and private progress
checkpoints. Updated writer routing and bounded worker-context instructions.
Exploration can propose alternatives; implementation gets targeted integration
context. Graph access is on demand; this worktree has no graph.

All four backend gates passed: ruff clean, 53 formatted files, strict mypy clean
for 30 files, and 247 tests passed with 3 PostgreSQL skips and 1 warning. Supervisor
checks passed: ruff clean, 11 formatted files, strict mypy clean for 6 files, and
24 tests passed. Claude independent review failed with expired OAuth (401).
The private-file Grok probe was rejected by automatic review and did not run;
the isolated synthetic fixture passed. Full evidence and the local stack are in
`docs/DEV_SUPERVISOR_VERIFICATION.md`. Nothing was pushed, merged, or activated
in the saved checkout. No application worker was launched.

## 2026-09-06 — Codex and Grok independent review policy

The user removed Claude Code from active FEWIA development. Decision 0009
supersedes the earlier writer/verifier contract. Current rules, role policies,
and delegation guidance now require a separate Codex or Grok reviewer with
read-only ownership. Historical Claude files and log entries remain intact.

Corrected stale Luna-only spawning, obsolete role ownership examples, and
assumptions about retained CLI session context. Added a tested exact-file
permission library for Grok. All 14 role TOML files parsed. No global settings,
accounts, subscriptions, installations, pushes, or merges changed.

## 2026-09-06 — Reviewed supervisor runtime and scoped Grok writes

A separate Codex reviewer reproduced lifecycle, question-state, permission-path,
and cleanup-order defects. Grok repaired the assigned files through the CLI
supervisor. Exact Write/Edit rules resolved headless file authorization; command
permissions remained active. The permanent --write-file interface completed the
final repair runs. No permission cancellation triggered provider fallback.

Final independent review found no remaining actionable defects in its scope.
It passed 35 tests and proved six regression mutations fail. Coordinator ruff,
formatting, strict mypy, and 35 supervisor tests passed. Backend gates passed:
247 tests passed, 3 PostgreSQL tests skipped, and 1 Starlette warning remained.
Evidence and activation limits are in docs/DEV_SUPERVISOR_VERIFICATION.md.
The local stack is unpublished. Saved-checkout integration remains separate.

## 2026-09-06 — Supervisor integrated into saved checkout

The user authorized local integration. Saved main was clean at 1dec7d4 and
matched freshly fetched origin/main. A fast-forward integrated the reviewed
six-branch stack at 10cf543. Saved-checkout backend gates passed with 247 tests,
3 PostgreSQL skips, and 1 existing warning. Supervisor gates passed with 35 tests.
All 14 role TOMLs parsed, and the supervisor CLI help exposed the expected flags.

The ignored graph remains an older snapshot: 90 of 96 indexed files match;
6 instruction/wiki files changed. Supervisor files and all role TOMLs lack graph
coverage. Current role files and runbooks remain the source for delegation.
Detailed results and graph gaps are in docs/DEV_SUPERVISOR_VERIFICATION.md.
No remote push, deployment, global change, or application worker was performed.
## 2026-09-06 Repair lease atomics, nondecreasing renew, and lease tests (backend reliability assignment).

Added atomic claim, renewal, and completion helpers on
`codex/job-worker-leases`, based on `0fa4852`. The slice adds 140 application
lines. Claims use fresh tokens and bounded attempts. Expired owners cannot
renew or complete reclaimed jobs. Renewal cannot shorten an existing lease.
The caller owns transactions. The runbook records time, ORM refresh, result,
and acknowledgement contracts. Queue consumption remains the next slice.

Grok 4.6 wrote the initial files. Its first run ended with `task_failed`.
Coordinator checks found six Ruff errors, four mypy errors, and three failing
SQLite timestamp assertions. Independent Codex review found lease shortening
and missing PostgreSQL reclaim and rollback evidence. A second Grok run ended
with `task_failed` and no repair. The coordinator explicitly assigned Spark
through the supervisor. No automatic provider fallback occurred.

Spark repaired the source and tests. PostgreSQL exposed a test that attempted
reclaim before the renewed expiry: one failed and 265 passed. Spark corrected
the test to the exact expiry boundary. Writer checks encountered uv cache
permissions and PostgreSQL connectivity restrictions. Coordinator checks ran
with cache and database access. Spark also appended the entry heading outside
its assigned source/test files; the coordinator retained it and supplied this
record. Scoped CLI permissions do not provide an OS write boundary.

Final coordinator commands from `backend/` passed:

- `uv run ruff check app tests`: `All checks passed!`
- `uv run ruff format --check app tests`: `56 files already formatted`
- `uv run mypy --strict app`: `Success: no issues found in 31 source files`
- `uv run pytest`, with `FEWIA_JOB_TEST_DATABASE_URL` set to an isolated
  migrated PostgreSQL 16 container: `266 passed, 1 warning in 1.30s`

The warning is the existing Starlette/httpx deprecation. No tests skipped.
Independent Codex reviewer `/root/lease_review` approved the final working
tree on `0fa4852`. Its targeted lease suite passed 16 tests with one warning.
It verified queued and expired claim races, old-token rejection, and caller
rollback from separate PostgreSQL sessions. Three temporary-copy mutations
failed: shortening renewal, bypassing renewal tokens, and bypassing completion
tokens. Source SHA-256:
`1e0b25a40ba0f885b1f11e0524180489ebdfc2ac7d72f5eab59be225d162d7f0`.

No SQS consumer, provider execution, deployment, push, or merge was performed.

## 2026-09-06 — Local SQS consumer transport

Added typed receive, visibility extension, and acknowledgement operations.
The adapter uses explicit dummy credentials and bounded long polling. It
validates the expected queue path and normalizes known Floci host aliases to
the configured endpoint. Malformed URLs and receipt handles fail with static
errors. This slice adds 150 application lines.

Independent review found alternate-origin acceptance, parser text leakage,
and empty-receipt acceptance in the initial Grok handoff. Luna repaired these
issues after Spark reached its usage limit. Live Floci returned its container
hostname to host clients, so the reviewed normalization contract replaced
strict alias rejection. A final import-order failure was repaired.

Coordinator gates passed: Ruff clean, 58 files formatted, strict mypy clean
for 32 files, and 333 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex runtime_design_review passed
67 adapter tests and approved credential and URL handling. Source SHA-256:
f99a4508a14411379c1d7c845147d5fc7614e6addb47cd47598b4d24ce1f5e4b.
A live isolated Floci queue passed receive, visibility hide, redelivery, and
acknowledgement checks. The temporary queue was deleted. No application queue
messages, external providers, deployments, pushes, or merges were performed.

## 2026-09-06 — Expired job recovery

Added a bounded recovery sweep that locks jobs and outbox entries. Safe jobs
return to queued state with pending publication. Exhausted jobs fail. Unsafe
jobs receive recovery_required without automatic replay. Pending, active, and
terminal jobs remain unchanged. The caller supplies a bounded replay classifier.

Coordinator gates passed: Ruff clean, 60 files formatted, strict mypy clean
for 33 files, and 354 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex runtime_design_review passed 21
recovery tests and PostgreSQL probes for claim locks, publisher locks, atomic
reset, pending preservation, and a final-attempt crash. Its unique temporary
schema was removed. Source SHA-256:
78882ca15e9b3d8d955983ff38fe2ec4733adebcab44dcaecbe72743c17e621a.
Real provider replay safety remains an explicit classifier responsibility.

## 2026-09-06 — Versioned grocery recipe catalog

Added ten recipes with per-serving integer quantities, package sizes, dietary
facts, and labeled sample prices. Missing prices remain representable. Pantry
metadata does not authorize omission. Recipe base servings are fixed at one.
The slice adds 142 source/data lines. Grok wrote the initial files; Luna repaired
formatting and interface drift after Spark reached its usage limit.

Coordinator gates passed: Ruff clean, 58 files formatted, strict mypy clean
for 32 files, and 288 tests passed with isolated PostgreSQL enabled. One
existing Starlette warning remains. Independent Codex reviewer domain_review
passed 22 catalog tests and found no blocking defect. It checked malformed
records, optional prices, base servings, and catalog completeness.
Source SHA-256: 4909325b925f888ca71c41474ad34955072bdd932ec82ea80a9ede8e509714d8.
No live pricing, inventory, provider call, push, or merge was performed.

## 2026-09-06 — Deterministic grocery budget

Added integer-cent budget calculation with posted net spending, separate
pending spending, New York month boundaries, and explicit temporary caps for
stale snapshots. Independent review reproduced daylight-saving freshness and
future-time defects. The repaired calculation compares UTC instants.

Grok stopped without files; Spark reached its usage limit. Luna implemented
and repaired this 110-line source slice. Coordinator gates passed: Ruff clean,
58 files formatted, strict mypy clean for 32 files, and 296 tests passed with
isolated PostgreSQL enabled. One existing Starlette warning remains.
Independent Codex reviewer domain_review passed 30 budget tests. Removing UTC
normalization in a temporary copy caused both regression tests to fail.
Source SHA-256: 8558ece83d83e1e114fa95d709a3332a0d1293d6856a4f97b2022beb6734b0e4.
No bank access, provider call, push, or merge was performed.

## 2026-09-06 — Bedrock provider boundary

Added LLMProvider and a bounded Converse adapter with an explicit real AWS
endpoint. Floci credentials and endpoints are not substituted. Independent
review reproduced malformed role, content, and stop-reason acceptance. The
writer repaired structural validation and preserved static failure errors.

Coordinator gates passed: Ruff clean, 68 files formatted, strict mypy clean
for 38 files, and 443 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex provider_contracts passed 37
mocked provider tests and malformed-message probes. Provider source SHA-256:
11a4443c268dff95140f9aa7f4d4bbc09e960549da5b17f67cbf0b99047c3729.
The combined source slice is 147 lines. Tool names and argument schemas remain
the agent loop's responsibility. No live Bedrock invocation was performed.

## 2026-09-06 — Delivery contracts and envelope validation

Added typed queue and handler contracts with bounded canonical job envelopes.
Duplicate JSON keys and oversized input are rejected. This 57-line layer
precedes the cooperative execution layer. Its direct tests do not import the
consumer. Combined coordinator gates passed: Ruff clean, 61 files formatted,
strict mypy clean for 34 files, and 295 tests passed with isolated PostgreSQL.
One existing Starlette warning remains. Independent Codex runtime_design_review
passed 29 delivery and execution tests. Delivery source SHA-256:
13ec4846f60fa258fbb458857d2d2ae10a5995856e0e2c784bbe28e4751a1edf.

## 2026-09-06 — Cooperative SQS job execution

Added committed claims, duplicate handling, cooperative heartbeats, bounded
retry delay, and committed terminal results before acknowledgement. Independent
review found a nonterminal acknowledgement bug and permissive envelope parsing.
The repairs retain nonterminal messages and reject malformed envelopes. Delivery
validation and execution ship as separate 57-line and 128-line source layers.

Coordinator gates passed 295 tests with isolated PostgreSQL, plus Ruff, formatting,
and strict mypy. Independent Codex runtime_design_review passed 29 targeted tests.
Its real PostgreSQL/Floci probe verified committed claims and results, harmless
terminal redelivery, active duplicate retention, and invalid-message retention.
The unique queue and schema were cleaned up. Execution source SHA-256:
6a78865e2bc82ba06f67960f23a0c8e28f4f261c8edce9214d71c95f0b279a3b.
The final transport hash in this probe was
baaea517c75b4ebe01de9b273b75f3e5505471d573b9460194f289df2c384b0d.
Background heartbeats and real-provider operation intents remain separate work.

## 2026-09-06 — Deterministic meal estimates

Added a planner that aggregates ingredients before package rounding, preserves
servings, validates diet and exclusions before pantry removal, and labels all
sample estimates. Explicit pantry items remain visible. Missing purchase prices
prevent acceptance. Temporary-cap warnings remain visible for stale spending.

Coordinator gates passed: Ruff clean, 62 files formatted, strict mypy clean
for 34 files, and 335 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex domain_review passed 17 planner
tests. It found a weak aggregation test; the writer replaced its quantities
with a discriminating case. Per-meal rounding then failed the regression in a
temporary copy. Request and mapping preservation checks also pass.
Source SHA-256: c4860d76bea9ce55cf260e4e633a80f3021005e44d29851031c648112a05e880.
The slice adds 149 application lines. No provider or purchase call was made.

## 2026-09-06 — Model-facing planning tool

Added a typed Bedrock tool schema and deterministic execution boundary. Model
caps can only reduce the server budget. Invalid arguments and catalog conflicts
produce static errors. Evidence IDs use the existing formatter with a content
hash over request, budget, plan, and source.

Coordinator gates passed: Ruff clean, 76 files formatted, strict mypy clean
for 42 files, and 508 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex runtime_design_review passed 19
targeted tests and found no blocking issue. Grok corrected one formatting-only
test call afterward. Source SHA-256:
489fcf5b6385f6c8239708f999dbbff7c1bf61a12919999d4d6ef0a0ea637b7f.
This 134-line tool does not call a model or external provider. Content-derived
IDs alone do not prove an immutable storage layer.

## 2026-09-06 — SDK-native planning results

A no-network botocore check found tuple-valued plan fields were invalid Converse
documents. Grok normalized the planner output to JSON-native values. The SDK
parameter test now passes and a tuple mutation fails it. Independent Codex
runtime_design_review approved the fix; evidence hashing retains equivalent JSON.

## 2026-09-06 — Bounded model-message parsing

Added strict assistant message parsing, tool bounds, stop consistency, duplicate
ID checks, atomic seen-ID updates, and reasoning removal. Grok's broad initial
chat assignment reached its 30-turn limit; smaller assignments preserved its
work. Independent Codex runtime_design_review passed 21 parser tests. The parser
is 150 source lines. No live model call was made.

## 2026-09-06 — Deterministic model tool dispatch

Added a 38-line dispatcher for the single approved planning tool. Unsupported
or invalid calls clear the candidate and return static errors. Traces hold only
tool outcomes and evidence IDs. Coordinator gates passed 535 tests with isolated
PostgreSQL, Ruff, formatting, and strict mypy. Independent review passed 46 parser,
planner, dispatcher, and SDK tests. The loop remains a separate draft.

## 2026-09-06 — Public chat context

Added bounded public dialogue history and aggregate planning context. The helper
rejects injected roles and preserves unknown token usage. Independent review
found one SDK test fixture error. Grok repaired it. Ruff, formatting, strict
mypy, and all 574 backend tests passed with PostgreSQL tests enabled.

## 2026-09-07 — Bounded grocery chat loop

Added an eight-turn Bedrock loop with three planner attempts, public history,
static provider errors, and honest token usage. Incomplete responses discard
candidate plans. Grok repaired a provider exception subtype leak found in
independent review. Ruff, formatting, strict mypy, and all 607 backend tests
passed with PostgreSQL enabled. Live Bedrock validation remains pending.

## 2026-09-06 — Grocery job payload adapter

Added a strict typed job payload with declared budget, spending source, and
period agreement. The adapter calls the deterministic budget and planner tools
between cooperative heartbeats. This 67-line layer precedes the worker command.
Combined coordinator gates passed: Ruff clean, 72 files formatted, strict mypy
clean for 39 files, and 454 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex runtime_design_review passed 23
handler/CLI tests. Handler source SHA-256:
652dab5c9fe51237bc1245172587abfa6c9a85ea53f164c8e7743e61b0e2f76d.

## 2026-09-06 — Bounded grocery worker command

Added an agent-queue-only command with bounded message count, signal restoration,
and static failure summaries. This source layer is 97 lines. Coordinator gates
passed 454 tests with isolated PostgreSQL, Ruff, formatting, and strict mypy.
Independent Codex runtime_design_review passed 23 targeted tests and an actual
PostgreSQL/Floci pipeline from create_job through publication and CLI execution.
It stored a 1,703-cent fixture estimate, retained the published outbox, and
restored signal handlers. Temporary queue and schema cleanup passed.
CLI source SHA-256: 2f545d2548c25e8df0991ef597e5a3e8c82ad938fdad666eec15165b0d23d3e9.
This proves local fixture processing, not live provider provenance.

## 2026-09-06 — Grocery API request and response models

Added typed fixture API models and canonical caller-field comparison for stable
idempotent requests. This 65-line model layer precedes the router integration.
Combined coordinator gates passed: Ruff clean, 76 files formatted, strict mypy
clean for 41 files, and 485 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Model source SHA-256:
737e9820c06d4faeed223d3cc04af810e51109305115d31e802a87aa1d8ebf64.

## 2026-09-06 — Grocery job HTTP routes

Added fixture configuration, server-selected user job submission, and restricted
job polling. New requests receive actual-time snapshots. Identical caller fields
reuse the original job and snapshot across midnight or month rollover. Changed
requests conflict. Concurrent insert winners use the same comparison.

Independent review reproduced daily-snapshot idempotency and DST freshness bugs;
Grok repaired both, corrected a contradictory notice test, and fixed formatting.
Coordinator gates passed 485 tests with isolated PostgreSQL, Ruff, formatting,
and strict mypy. Independent Codex runtime_design_review passed 21 targeted tests
and PostgreSQL concurrent/midnight retry probes. Router source SHA-256:
a51739e321fac090f4d26faf3b30a55aee8d21f68d33e9496af42f807fb8bee7.
The router plus registration stays below 150 added source lines. This API reports
fixture provenance. It does not claim live Plaid or Bedrock integration.

## 2026-09-06 — Plaid ledger schema

Added provider Items with credential references and normalized USD transaction
rows. Migration 0005 preserves prior tables and rejects downgrade. The source
slice adds 113 lines including Alembic registration. Coordinator applied the
migration to a disposable database. Ruff, required formatting, strict mypy,
and 300 tests passed; one existing Starlette warning remains. A broader format
scan found an unchanged migration 0003 formatting issue; new migration files pass.

Independent Codex provider_contracts verified PostgreSQL uniqueness, composite
identity, orphan rejection, USD restriction, refund reload, and reflection parity.
All synthetic probe rows were rolled back. No access token or raw response is
stored by this schema. Source SHA-256:
dd07e388ba469a1ef43c061900484f26cfcc745c0a1b6881b3ad3f81e6e31d37.
No live Plaid sync, shared development migration, push, or merge was performed.

## 2026-09-06 — Normalized Plaid sync pages

Added strict normalized page records, exact signed cents, dates, pending flags,
removals, and grocery classification. Raw provider fields do not enter the DTO.
Independent review found Decimal underflow could silently convert tiny nonzero
amounts to zero. Coefficient/exponent conversion repaired that defect.

Coordinator gates passed: Ruff clean, 62 files formatted, strict mypy clean
for 34 files, and 339 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex provider_contracts passed 39 tests
and 1,509 exact-value probes under hostile Decimal settings. Grok completed a
file-tool-only constant cleanup to meet the 150-line source cap; coordinator
reran all gates, and independent review confirmed equivalent bounds.
Source SHA-256: 3fd11a6b07c0204ef21e8bb0abdddb8ccfc85efc5070a69d525d03f50fae0664.
No HTTP request or live Plaid sync was performed.

## 2026-09-06 — Plaid Sandbox HTTP adapter

Added a fixed Sandbox sync endpoint with exact Decimal decoding, one transport
attempt, bounded request timeouts, and caller-owned versus adapter-owned client
cleanup. httpx is now a runtime dependency. Independent review found injected
redirects could forward credentials, resolver failures could escape, and error
contexts retained originals. Grok repaired those paths with file tools.

Coordinator gates passed: Ruff clean, 64 files formatted, strict mypy clean
for 35 files, and 355 tests passed with isolated PostgreSQL. One existing
Starlette warning remains. Independent Codex provider_contracts passed 16 mocked
HTTP tests and redirect/timeout/error-context probes. No cross-origin request
occurred in the repaired redirect test. Provider source SHA-256:
83a4069abcbe8da2d0e53e3b8099abe67651b0cf0db053448e1912c514194a57.
No live Plaid request was made. Resolver failure is a static ValueError.

## 2026-09-06 — Atomic Plaid Item synchronization

Added bounded page collection under an owned Item lock. Mutation restarts discard
partial pages and reuse the original cursor. Ledger changes, final cursor, and
freshness commit together. Failures and heartbeat loss roll back the transaction.

Coordinator gates passed: Ruff clean, 66 files formatted, strict mypy clean for
36 files, and 368 tests passed with isolated PostgreSQL. One existing Starlette
warning remains. Initial tests failed on a negative fixture user and a stale
metadata inventory. Grok repaired both and scoped the lock probe to its own
backend PID. Independent Codex provider_contracts passed 20 targeted tests and
verified serialization, non-null cursor restart, and final-heartbeat rollback.
Source SHA-256: 64aecdfd51fdfd98d969dbe5c0427e4b4fa32fe3fcd5912312505d0a1047d0d6.
No live Plaid sync was performed.

## 2026-09-06 — Plaid history readiness guard

The HTTP adapter now requires HISTORICAL_UPDATE_COMPLETE before returning a
sync page. Missing, unknown, initial, and not-ready status cannot advance local
freshness. This follows the documented transactions_update_status contract:
https://plaid.com/docs/api/products/transactions/.

Coordinator gates passed: Ruff clean, 66 files formatted, strict mypy clean for
36 files, and 379 tests passed with isolated PostgreSQL. One existing Starlette
warning remains. Grok wrote the guard; the coordinator applied mechanical Ruff
newline normalization to its test. Independent Codex provider_contracts passed
27 targeted tests and readiness probes. Provider source SHA-256:
4358e880ef498dea32cc2fa755c62db9e971676f142d72e9a3509611c9ed3945.
No live Plaid request was made.
