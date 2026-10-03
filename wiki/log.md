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
training. Each role selects `gpt-6-luna` with `xhigh` effort. The shared
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

## 2026-09-06 — Consistent ledger spending snapshots

Added one-query aggregation of readiness, oldest sync time, posted spending,
and pending spending across owned Items. Left joins retain empty or uninitialized
Items. Exact signed totals and month/category filters are preserved. SQLite
fixtures now store UTC, matching the production sync path.

Coordinator gates passed: Ruff clean, 68 files formatted, strict mypy clean for
37 files, and 410 tests passed with isolated PostgreSQL. One existing Starlette
warning remains. Independent Codex provider_contracts passed 31 targeted tests
and PostgreSQL single-query, large-sum, filtering, and readiness probes.
Source SHA-256: 5485ed555289e98eb75c6df282fc24f3e07ea5c003a683e1a50ac3e3846814cb.
Missing or incomplete Item data does not silently become zero spending.

## 2026-09-06 — Shopping handoff records

Added migration 0006 and the shopping handoff model. Records bind each request
hash to its user and retain dispatch state, attempt tokens, and retry consent.
Independent review found model and migration parity. The isolated PostgreSQL
upgrade passed. Ruff, formatting, strict mypy, and all 428 backend tests passed.
The service still needs to enforce immutable payloads and fenced completion.

## 2026-09-06 — Grocery web shell

Added a responsive React/Vite shell with local fonts, truthful empty states,
and a loopback API proxy. The generated concept guides the complete surface;
its illustrative values will be replaced by actual planner results.

The initial writer could not resolve npm inside its sandbox. Coordinator
installation found incompatible Vite/plugin versions and missing Node type
libraries. Grok repaired both through file-tool-only assignments. npm install
then reported zero vulnerabilities, and the strict TypeScript/Vite build passed.
Independent Codex domain_review found no shell source blocker. Visual and
interactive review remain pending until controls are connected.

Backend gates on this branch passed: Ruff clean, 64 files formatted, strict
mypy clean for 35 files, and 406 tests passed with isolated PostgreSQL. One
existing Starlette warning remains. The shell is 148 source/config lines.
Only explicit source, lock, and design files are staged; generated dist files
are not included. No provider or purchase behavior is claimed by this shell.

## 2026-09-06 — Web API contracts and test tools

Added typed response contracts, primitive guards, and direct guard tests.
The first layer is independently testable. npm 10 hit a resolver crash; a
project-local npm 12 command regenerated the dependency tree without changing
global tools. Strict frontend build and 20 client tests passed. Independent
Codex domain_review passed the seven first-layer tests and the full client suite.
This is a source review, not completed visual or interaction verification.

## 2026-09-06 — Web response validation

Added independent parsers for config, job, budget, and plan responses. Valid
incomplete estimates remain visible. Unsafe or fractional cents and completed
jobs without results are rejected. Direct validation tests do not import HTTP
helpers. Independent review and the full 20-test client suite passed.

## 2026-09-06 — Web API transport

Added same-origin config, submission, and polling calls with cancellation and
static errors. The body-cancellation test waits until JSON reading begins.
Strict frontend build and all 20 client tests passed. No credentials enter the
browser. HTTP source is 111 lines and has independent tests.

## 2026-09-06 — Cancellable grocery job polling

Added idempotent retry keys, bounded polling, whole-attempt timeout, and stale
response suppression. New submissions clear prior job/error state. Independent
review found and returned incomplete-estimate, numeric, stale-state, and timeout
bugs; Grok repaired them. Strict frontend build and 20 tests passed, including
hung requests, body cancellation, key reuse, late response, and unmount cases.
Polling source is 143 lines. Controls and browser verification remain next.

## 2026-09-06 — Exact web money input

Added decimal-string parsing to safe integer cents and USD formatting. Invalid
negative, fractional-cent, and unsafe values are rejected. The 36-line helper
has direct tests. Independent Codex domain_review approved exactness and bounds.
Combined frontend build and 33 tests passed after adding the meal form.

## 2026-09-06 — Explicit meal and pantry controls

Added controlled meal, serving, budget, diet, pantry, and exclusion inputs.
Request construction copies state and validates catalog choices. Pantry flags
require user selection. Independent Codex domain_review passed 13 money/form
tests and approved labels, disabled semantics, and mutation guards. The strict
frontend build and all 33 frontend tests passed. Form source is 150 lines.
App wiring and browser verification remain separate work.

## 2026-09-06 — Server estimate view

Added the estimate view with exact sample costs, package counts, pantry controls,
and source labels. Missing prices remain incomplete. Draft changes retain the
previous server estimate. Independent review passed after the source-label repair.
All 45 frontend tests and the production build passed. Browser checks remain pending.

## 2026-09-06 — Grocery conversation status

Added example actions, job status, and retry controls. Errors suppress stale
conversation status. Independent review passed. All 45 frontend tests and the
production build passed. The app wiring follows in a separate layer.

## 2026-09-07 — Web request state

Connected configuration, meal drafts, submission, retry, and pantry state.
Grok repaired stale-configuration submission after independent review.
Original-body retries preserve ambiguous requests. All 56 frontend tests and
the production build passed. App rendering and browser checks follow.

## 2026-09-07 — Immutable grocery evidence schema

Added migration 0007 and content-addressed evidence records. Grok repaired a
PostgreSQL-only check that broke SQLite setup. Mechanical import sorting fixed
one Ruff error. Ruff, formatting, strict mypy, migration, and all 801 backend
tests passed. Independent PostgreSQL probes accepted a valid row and rejected
invalid hashes, foreign owners, updates, and deletes. Privileged table or trigger
changes remain outside the row-level immutability boundary. Persistence follows.

## 2026-09-07 — Background job lease renewal

Added serialized background and manual heartbeats. Completion waits for thread
shutdown and rejects late lease loss. Grok repaired the strict context-manager
return annotation and strengthened two contention tests after review. Ruff,
formatting, strict mypy, and all 501 backend tests passed.

Independent PostgreSQL checks observed five renewals through distinct sessions.
Seven renewal sessions applied local lock and statement timeouts. A held row
returned SQLSTATE 55P03 after 5.056 seconds. The worker returned lease_lost,
kept the result unset, skipped acknowledgment, and joined the renewal thread.
Connection, pool, and broken-socket timeouts remain a separate runtime concern.

## 2026-09-07 — Instacart development transport

Added one-attempt products-link requests to the fixed development endpoint.
The adapter blocks redirects and validates HTTPS response hosts. Grok repaired
deep JSON handling and encoded control rejection after independent review.
Ruff, formatting, strict mypy, and all 518 backend tests passed. Mocked HTTP
checks do not prove live provider access or a successful shopping handoff.

## 2026-09-07 — Verified evidence inputs

Added evidence normalization from server budget inputs and recomputed plans.
Forged costs, sources, and owner-dependent IDs are rejected. Grok repaired deep
JSON error handling after review. Ruff, formatting, strict mypy, and all 923
backend tests passed on the combined evidence branch.

## 2026-09-07 — Atomic evidence storage

Added full-hash evidence inserts and owner-filtered reads. Identical snapshots
reuse an ID. Conflicts never overwrite records. Grok repaired a SQLAlchemy
statement annotation after strict mypy failed. All four backend gates passed,
including 923 tests. Independent PostgreSQL concurrency tests passed. Migration
trigger probes remain the separate evidence for row immutability.

## 2026-09-07 — Grocery form styles

Added readable form and conversation styles as a foundation for app integration.
The combined UI branch passed 66 tests and its production build. Independent
source review passed. Browser verification follows after the app wiring layer.

## 2026-09-07 — Grocery estimate styles

Added responsive estimate rows, pantry controls, and sample-price states.
The stylesheet stays within its review layer. Independent source review passed.
The combined UI branch passed 66 tests and its build. Browser checks follow.

## 2026-09-07 — Grocery app wiring

Connected the meal form, submission state, server estimates, and retry controls.
Grok repaired enabled controls that did nothing during catalog failures.
The development proxy defaults to the isolated API on loopback port 8010.
Independent review, all 66 frontend tests, and the production build passed.
Browser verification remains pending. The interface does not claim live chat.

## 2026-09-07 — Browser-driven grocery refinements

Added a nearby rebuild action for changed estimates. Fixed the mobile servings
layout, desktop spacing, package wording, duplicate warnings, and favicon request.
Independent source review and all 72 frontend tests passed. The build passed.
Before these refinements, the real browser-to-SQS flow returned 17.03 dollars,
then 11.04 dollars after olive oil entered the pantry. Post-change browser checks
follow. Mobile document width matched its 390-pixel viewport in the baseline.

## 2026-09-07 — Deterministic shopping payload

Added ingredient-only Instacart payloads with canonical hashes. The builder
preserves required quantities and removes only confirmed pantry purchases.
Grok repaired malformed expiry, unit, recursion, and ingredient validation after
independent review. Ruff, formatting, strict mypy, and all 594 backend tests
passed. No live shopping link was created. Durable dispatch follows.

## 2026-09-07 — Database acquisition bounds

Added PostgreSQL connection and pool timeouts with statement and lock limits.
SQLite receives no PostgreSQL-only options. Grok repaired tests that assumed
unsupported URL aliases and an uninstalled driver. Independent review passed.
Ruff, formatting, strict mypy, and all 540 runtime-branch tests passed.

## 2026-09-07 — Continuous grocery worker

Added continuous recovery, outbox publication, and agent-job consumption.
Grok repaired standalone model registration and failure counter retention after
independent review. All 540 backend tests, Ruff, formatting, and strict mypy
passed. Actual continuous Floci execution follows; bounded consumer probes
already passed against the isolated emulator.

## 2026-09-07 — Ordered chat evidence revisions

Added evidence callbacks before tool-success publication. Traces keep ordered
call occurrences even when immutable snapshot IDs repeat. Limits and incomplete
results clear final revision IDs. Grok repaired an empty-string test assertion
after review. All 990 backend tests, Ruff, formatting, and strict mypy passed.
Independent targeted review passed 71 tests. Job adapters follow.

## 2026-09-07 — Recorded plan jobs

Plan jobs now return the validated request and accept an evidence recorder.
The job freezes its calculation time and records before returning a result.
Independent review and all four backend gates passed, including 1,011 tests
on the combined adapter branch.

## 2026-09-07 — Recorded chat jobs

Added typed chat-job input and server-budget calculation. Public history passes
the bounded context validator. Each valid tool result is stored before the next
model turn. Independent review and all 1,011 backend tests passed with the
required lint, format, and type checks. Live model calls remain unverified.

## 2026-09-07 — Agent job routing

Added a handler factory for the single demo user. Plans remain available without
a model. Chat requires a provider; unknown operations fail before execution.
Both paths record evidence. Independent review and all 1,011 backend tests
passed. Worker and HTTP configuration follow.

## 2026-09-07 — Bounded demo startup

Added migration, idempotent demo-user seeding, and local Floci provisioning.
Child commands use bounded timeouts and static status output. Grok repaired
one strict typing issue and a retry-test setup error. Independent review,
Ruff, formatting, strict mypy, and all 551 backend tests passed.

## 2026-09-07 — Grocery Compose stack

Added startup dependencies, a continuous worker, and the static web container.
Published ports bind to loopback. Separate Docker contexts exclude environment
files, secrets, and writer checkpoints. Independent review and Compose config
validation passed. Image builds need the integrated frontend checkout and follow
in the coordinator's isolated stack. No user containers were replaced.

## 2026-09-07 — Provider settings and secret files

Added bounded file-based provider settings with masked credentials. Grok repaired
malformed JSON depth and NUL-path error handling. All 1,027 backend tests and
static gates passed. The Codex reviewer reached its usage limit, so a separate
Grok source review checked the repaired code and approved it. That reviewer did
not execute tests. No real credentials or provider calls were used.

## 2026-09-07 — Lazy provider construction

Added provider factories and secret-free configuration flags. Disabled providers
have no file or network effects. Flags describe configuration, not connectivity.
All 1,027 backend tests and static gates passed. Independent source review
approved the factories. Live provider evidence remains pending.

## 2026-09-07 — Handoff cache validation contract

Added shared payload, URL, ownership, time, and database-error checks. Cached
payloads are revalidated by their canonical hash. Unsafe cached URLs are not
returned. Independent review and all 650 provider-branch tests passed with the
required lint, format, and type checks.

## 2026-09-07 — Durable handoff intents

Added per-user intent caching and explicit stale-state handling. Grok replaced
raw integrity-error parsing and a flaky SQLite concurrency claim after review.
PostgreSQL now supplies concurrency evidence. Independent review and all 650
backend tests passed with the required static gates. No live link was created.

## 2026-09-07 — Explicit shopping handoff dispatch

Added commit-before-request dispatch, uncertainty handling, and attempt fencing.
Initial attempts do not record retry consent. Explicit retries require the
current attempt count; late responses cannot replace a newer result. The first
writer stopped before dispatch tests, so the remaining work used a bounded
assignment. All 650 backend tests and static gates passed. Independent review
passed 41 PostgreSQL-enabled handoff tests. Live Instacart remains unverified.

## 2026-09-07 — Chat history repair and alignment

Preserved the user's 84355a2 checkpoint. Repaired static history errors so they
retain no raw validation context. Added owner checks and aligned operation tags
with the job handler. The independent source review identified the operation
mismatch; the repair follows that contract. All 1,176 backend tests and static
gates passed after provider and handoff integration.

## 2026-09-07 — Select configured grocery spending

Grok 4.6 wrote the HTTP spending selection. Independent Grok review approved the
source after unknown-source and static error repairs. Fixture and Plaid Sandbox
spending remain distinct. Missing Sandbox data returns an error without fixture
substitution. The coordinator tested this layer without chat routes: ruff and
format passed, strict mypy passed 74 files, and 1,197 PostgreSQL-enabled tests
passed with one existing Starlette warning. This layer adds 129 source lines.

## 2026-09-07 — Submit bounded chat jobs over HTTP

Grok 4.6 wrote chat submission, job reads, and provider capability routes.
Independent Grok source review approved ownership, replay, history, configuration,
and static error handling. The coordinator ran all four backend gates: ruff and
format passed, strict mypy passed 75 files, and 1,221 PostgreSQL-enabled tests
passed with one existing Starlette warning. This layer adds 141 source lines.
No route constructs a provider or reads provider secret files. Live provider
validation remains pending.

## 2026-09-07 — Route recorded plans, chat, and sync jobs

Grok 4.6 wrote the runtime routing. A separate Grok source reviewer found no blockers.
The coordinator ran ruff, formatting, strict mypy, and PostgreSQL-enabled pytest.
Results: all checks passed; 140 files formatted; 74 typed source files; 1,187 tests passed.
Pytest reported one existing Starlette deprecation warning. The first check found a
missing test import; the writer repaired it before the passing run.

An isolated Docker worker consumed a synthetic plan through Floci and PostgreSQL.
The plan cost 1,703 cents. Its immutable evidence snapshot matched the result and
rejected a foreign owner read. Unconfigured chat and sync jobs failed with no result.
Both temporary workers exited with code 0 after SIGTERM. No live provider call ran.
The source delta adds 139 application and Compose lines against 94f3db9.

## 2026-09-07 — Web chat contracts

Added typed chat requests, results, and trace fields with shared plan validators.
The combined frontend passed 84 tests and its build. Independent Grok source
review approved the contract. The writer's terminal request was cancelled;
coordinator checks supplied the execution evidence.

## 2026-09-07 — Chat response validation

Added strict chat-response validation and copied result data. Invalid candidates,
counts, sources, and revision IDs fail before rendering. All 84 frontend tests
and the build passed. Independent Grok source review approved the validator;
it did not execute tests. HTTP transport follows.

## 2026-09-07 — Add the chat HTTP client

Grok 4.6 wrote the chat submission and read client. A separate Grok reviewer
approved the source. The coordinator ran 90 frontend tests and the production build.
Both passed after the writer repaired two typed mock errors. Requests use bounded
shared JSON handling, encoded job IDs, and idempotency headers. No live model call ran.

## 2026-09-07 — Poll chat jobs with bounded retries

Grok 4.6 wrote the chat polling hook. A separate Grok source reviewer found no
logic blockers. The coordinator ran 100 frontend tests and the production build;
both passed. The hook bounds waits to eight minutes, preserves ambiguous retry
keys, aborts on unmount, and fences obsolete responses. This layer adds 140 source
lines above the HTTP client. Browser chat integration remains pending.

## 2026-09-07 — Verify the integrated grocery runtime

The reviewed snapshot `b7880e5` passed all backend gates with 1,232 PostgreSQL-enabled
tests. It passed 100 frontend tests and the production build. The local Compose
project `fewia-grocery-b7d4` now runs this snapshot from `/private/tmp/fewia-compose-current`.
The web proxy submitted a synthetic plan through the API, outbox, Floci, and worker.
It returned 1,703 cents and a stored evidence revision. Repeated submission returned
the same job. Chat returned HTTP 503 because no model is configured. Provider flags
were false. No live provider call ran. The original user containers remain unchanged.

## 2026-09-07 — Read provider configuration in the web client

Grok 4.6 wrote the provider capability client and grocery configuration validation.
Independent Grok source review approved the change. The coordinator ran 108 frontend
tests and the production build; both passed. The client distinguishes fixture and
Plaid Sandbox spending. It validates configured flags without claiming live provider
verification. The layer adds 75 application source lines.

## 2026-09-07 — Read immutable grocery evidence over HTTP

Grok 4.6 wrote the owner-scoped evidence route. Independent Grok security review
approved the source. All backend gates passed: ruff, formatting, strict mypy, and
1,182 tests. Eight PostgreSQL tests skipped in that full run. A separate enabled
run passed ten evidence API and store tests. One existing Starlette warning remains.
The 51-line route returns a stored snapshot for an owned revision. Missing, foreign,
and malformed revisions return 404. Router registration remains a later layer.

## 2026-09-07 — Define strict shopping handoff HTTP types

Grok 4.6 wrote the 32-line type layer. Independent Grok security review approved it.
The coordinator tested a clean snapshot with this layer only: all backend gates
passed, including 1,180 PostgreSQL-enabled tests. One existing Starlette warning
remains. Request bodies reject extra fields and noninteger retry attempts.

## 2026-09-07 — Build handoff payloads from stored snapshots

Grok 4.6 wrote the 127-line snapshot helper. Independent Grok security review
approved it. A clean snapshot with types and helper passed all backend gates,
including 1,198 PostgreSQL-enabled tests. One existing Starlette warning remains.
Plain and chat jobs use the same immutable planning subset. Foreign, tampered,
incomplete, rejected, and empty shopping plans do not dispatch.

## 2026-09-07 — Add shopping handoff HTTP routes

Grok 4.6 wrote the 118-line route layer. Independent Grok security review approved
it. All backend gates passed, including 1,212 PostgreSQL-enabled tests. One existing
Starlette warning remains. Cached and stale retry paths do not construct providers.
Explicit retries use attempt fencing. Dispatch closes its owned client. Uncertain
results do not replay automatically. No live Instacart call ran. Router registration
remains a later layer.

## 2026-09-07 — Register shopping and evidence routes

Grok 4.6 registered both routers. Independent Grok security review approved the
four source lines. The first full test run found one route-inventory test failure:
FastAPI uses included-router wrappers. The writer changed the test to the public
OpenAPI inventory. All backend gates then passed: ruff, formatting, strict mypy
on 80 files, and 1,276 PostgreSQL-enabled tests. One existing Starlette warning
remains. The main error envelope preserves static ownership and configuration errors.

## 2026-09-07 — Verify shopping routes in local Compose

The local Compose project runs reviewed snapshot `84a145c` from
`/private/tmp/fewia-compose-shopping`. Through the web proxy, evidence GET returned
the stored 1,703-cent plan. A malformed revision returned 404. Handoff POST returned
the static unconfigured-provider 503. The database preserved a prepared intent
with zero attempts. Handoff GET returned only public fields. No provider dispatched.

## 2026-09-07 — Define the sync HTTP request model

Grok 4.6 wrote the strict item-id request model. Independent Grok security review
approved it. A clean snapshot with the model layer passed all backend gates,
including 1,205 PostgreSQL-enabled tests. One existing Starlette warning remains.
The 24-line model rejects extra fields and blank Item IDs.

## 2026-09-07 — Submit Plaid sync jobs over HTTP

Grok 4.6 wrote the sync routes. Supervision repaired the URL prefix and raw database
error propagation. Independent Grok security review then approved the source. All
backend gates passed, including 1,228 PostgreSQL-enabled tests. One existing
Starlette warning remains. The 134-line layer preserves atomic outbox submission,
owned Item checks, replay before configuration, and static context-free errors.
Router registration remains a later layer. No Plaid request ran.

## 2026-09-07 — Register the sync HTTP routes

Grok 4.6 registered sync on the main app. Independent Grok security review approved
the two source lines and test changes. All backend gates passed: ruff, formatting,
strict mypy on 82 source files, and 1,318 PostgreSQL-enabled tests. One existing
Starlette warning remains. Main-app tests cover owned submission, atomic outbox,
replay, configuration errors, and public job reads. No provider request ran.

## 2026-09-07 — Store local evaluation artifacts

Grok 4.6 wrote the Floci artifact adapter. Independent Grok security review required
a proxy-isolation repair, then approved the source. Local S3 and SQS clients now
set an empty proxy map. All backend gates passed, including 1,237 PostgreSQL-enabled
tests. One existing Starlette warning remains. Initial test lint and optional
exception-note inspection failures were repaired. The layer adds 148 source lines.

A synthetic 81-byte report round-tripped through the local Floci S3 bucket. Its
SHA-256 matched the stored body. Reordered input keys produced the same object key.
This was a transport probe with zero evaluation runs. It does not prove live AWS
or model quality. The caller remains responsible for report sanitization.

## 2026-09-07 — Load provider status with a bounded wait

Grok 4.6 wrote the 63-line provider-status hook. Independent Grok source review
approved it. A clean snapshot with this layer passed 115 frontend tests and the
production build. Failed refreshes clear stale flags. Fetch and JSON share a
20-second abort bound. An initial test-mock typing error was repaired before the
passing build. No provider connection or live-price claim is inferred from flags.

## 2026-09-07 — Define the grocery evaluation corpus

Grok 4.6 wrote 30 versioned scenarios with three intended repeats. Independent
Grok review approved the model/domain split and found an overbroad paired test.
The writer repaired that test without removing the adversarial forbidden tool.
The coordinator verified the repair and all branch gates: ruff, formatting, strict
mypy, and 660 tests passed; seven PostgreSQL tests skipped. One existing Starlette
warning remains. All seven meal gold rows and the F05 follow-up rows matched
actual planner output in separate coordinator checks.

Only plan_groceries is a model tool. Sync, budget calculation, job delivery, and
shopping handoff are server actions. Target evidence labels are not observed proof.
The corpus does not contain an executed 90-run result or a model-quality score.

## 2026-09-07 — Define chat conversation helpers

Grok 4.6 wrote the 72-line helper layer. Independent Grok review checked budget
validation, wire-body copies, replay rules, and dispatch generations. A clean
snapshot with this layer passed 122 frontend tests and the production build.

## 2026-09-07 — Keep bounded chat conversation state

Grok 4.6 wrote the 140-line controller. Independent Grok review checked the repaired
ambiguous replay, parent selection, error clearing, and dispatch fencing. The
coordinator repaired test timing through the writer and verified pre-mutation
capture in the adversarial body test. A clean helper-plus-controller snapshot
passed 140 frontend tests and the production build. Same-body ambiguous sends
preserve the request. Terminal sends can start a new intent.

## 2026-09-07 — Add the chat composer panel

Grok 4.6 wrote the 129-line chat panel. Independent Grok review checked text escaping,
input bounds, timeout and retry guidance, and configuration gating. The coordinator
ran 151 frontend tests and the production build; both passed. Unknown errors remain
hidden. Existing-request replay stays available when provider configuration fails.
Page and browser integration remain later work.

## 2026-09-07 — Pause for professor feedback

The user chose early MVP feedback before completing the broader feature plan.
All active writers finished. Feature expansion is paused, and the working local
demo remains running. Draft work is preserved. Live chat/provider validation and
formal evaluation remain incomplete and must be disclosed during the demo.

## 2026-09-07 — Grocery MVP checkpoint for professor feedback

Recorded the local grocery MVP as a professor-feedback checkpoint. This is not a completed AI product. The working path is meal controls through the API, PostgreSQL outbox, Floci SQS, and the worker to an itemized sample estimate. Bean tacos for two cost 1,703 cents. Olive-oil pantry stock reduces that plan to 1,104 cents. Chat panel, controller, and API exist. They are not wired into App. Live Bedrock, Plaid Sandbox, Instacart, 90-run evaluation, merge, and Graphify remain pending. Details: [phases/grocery-mvp-checkpoint.md](phases/grocery-mvp-checkpoint.md).

## 2026-09-07 — Validate the consolidation checkpoint

The user authorized one large consolidation pull request and merge. The exception
applies to this checkpoint only. Independent Grok review found no blocking issues
in the preserved drafts and CI changes. The combined local gates passed: 1,374
backend tests with PostgreSQL enabled, 238 frontend tests, strict mypy on 85 source
files, ruff, formatting, and the frontend production build. Fresh database migration
reached 0007. One existing Starlette deprecation warning remains. GitHub CI and
merge evidence remain pending. No live provider or 90-run evaluation claim is made.

## 2026-09-07 — Publish the professor-feedback checkpoint

[Consolidate grocery MVP and provider foundations](https://github.com/emanuelGitCodes/fewia/pull/42)
merged into main at `5bcf21b31523f7c2e1b22bb1aa069b9bb8a08c14`.
Both GitHub Backend checks and Frontend checks passed. The saved main checkout
was fast-forwarded. All remaining draft work was committed and pushed on backup
branches. Feature expansion remains paused for professor feedback.

Graphify was rebuilt from 237 code files, 44 documents, and one image after merge.
The initial published graph contains 3,424 nodes and 10,555 edges. Raw extraction
has 979 unresolved references, mostly external imports, 919 undirected endpoint
collapses, and 121 exact duplicates. These are analysis coverage limits. The report
and health diagnostics preserve them. Semantic token usage is unavailable.
The local ignored graph outputs are refreshed again after this documentation merge.
Chat integration, live provider checks, and the 90-run evaluation remain incomplete.

## 2026-09-07 — Visible meal chat on the local page

The user asked to resume visible chat integration on `codex/visible-meal-chat`.
Grok 4.6 writers completed this slice.
A separate Grok agent reviewed the frontend independently.

A fresh worker repaired bounded-history request identity.
The same worker repaired CSS rule precedence.

The coordinator reported that `npm test` passed after a test selector repair.
`npm run build` also passed.
An earlier test run reported 253 passed and 1 failed.
The page now has two forms.

The coordinator reported that backend `ruff check` passed.
Format check covered 165 files.
Strict mypy passed 85 source files.
Pytest reported 1,366 passed.
Pytest skipped eight optional database tests.
One existing Starlette warning remains.

Operators updated the local web container from the current frontend sources.
A browser at `127.0.0.1:5173` shows Meal chat beside the manual planner.
The estimate view remains visible.
The console showed no errors.
No framework overlay appeared.

Manual bean tacos for two succeeded at 1,703 cents.
The sample-price notice remained visible.
The chat reset button works.

The backend reports `chat_configured` false.
The composer Send control stays disabled.
Real AI replies were not tested.
Real AI replies are not available.
AWS profile and model configuration remains the blocker.

This entry does not claim full context transfer from the manual planner to chat.
It does not prove a live provider.
Feature work pauses here pending configuration and user feedback.
No push or merge occurred.

## 2026-09-08 — Restricted Bedrock development role

The user authorized a Python CDK restricted IAM role.
The user chose application Luna with reasoning effort low.
Grok 4.6 was the sole writer.

Local commit `578b8b6` records the CDK stack and environment template.
Local commit `9fa058c` records the provider low setting.
Local commit `96ab136` records the MFA helper.

Live AWS evidence: stack `FewiaBedrockDev` reports `CREATE_COMPLETE` in `us-east-1`.
The verified live IAM role is `FewiaBedrockDev-DevConverse6250D9A7-xsXUAGbONTTL`.
The trust policy names the same-account admin user.
The trust requires MFA.
The session duration is 3600 seconds.
The role has no attached managed policy.
The role permits `InvokeModel` only.
The allow list is the selected US Luna profile default project plus three profile-conditioned models.

Role tags are Project FEWIA, Environment development, and ManagedBy AWS-CDK.
Further tags are Component bedrock-chat, Model openai.gpt-6-luna, and ReasoningEffort low.
No IAM user was created.
No access key was created.

Deterministic CDK evidence: 14 tests passed.
Ruff, format, and strict mypy passed on 3 CDK files.
Deterministic backend evidence: 1372 tests passed.
Eight PostgreSQL tests skipped due to environment.
One existing warning remains.
Ruff, format, and mypy passed 85 backend files.
Deterministic helper evidence: 10 fake tests passed.
Ruff, format, and mypy passed on the helper.

The local `.env` file has mode 600.
Git and Docker ignore it.
It holds nonsecret settings and paths only.
Actual role credentials are not issued yet.
API and worker images were built.
The Compose override parse passed.
Services were not restarted.

The user MUST run the helper in a private terminal.
The user MUST enter MFA privately.
This log MUST NOT record an MFA code or credential value.
A browser real Luna reply was not verified.
Cost tags are attached to the role.
Billing activation waits for the first Bedrock call.
No Cost and Usage Report export exists.
No hard dollar cap exists.
No push or merge occurred.

This record MUST NOT claim a fully operational system.
This record MUST NOT claim a security guarantee.

Next, the user runs the helper.
The user then enters MFA privately.
Then the operator verifies the restricted identity.
Then the operator enables the API.
Then the operator enables the worker.
Then the operator runs a real chat.
Then the operator runs a follow-up.
Then the operator activates IAM billing tags when they are available.

## 2026-09-08 — Luna configured, runtime still denied

Source: coordinator checkpoint. This entry does not claim independent
live AWS checks.

Deployed evidence: stack `FewiaBedrockDev` remains `CREATE_COMPLETE`.

Live coordinator evidence: the MFA helper succeeded in a private
terminal. The restricted assumed-role identity was verified. The
credential file mode is `600`. The ignored `.env` mode is `600`. That
file holds nonsecret settings and path metadata only.

Local app evidence: operators rebuilt `api` and `worker`. Operators
force-recreated those services. Health returned 200.
`chat_configured` is true. The chat textbox accepts input.

Live Bedrock evidence: the first browser meal request failed before an
answer. Direct Converse with the restricted role returned this error:

```
AccessDeniedException: openai.gpt-6-luna is not available for this account, explore other models or contact AWS Sales
```

Direct Converse with the admin identity returned the same error.

The admin identity completed a one-time
`create-foundation-model-agreement` for the user-selected Luna model.
Agreement availability progressed from PENDING to AVAILABLE. The final
query reported agreement AVAILABLE, authorization AUTHORIZED,
entitlement AVAILABLE, and region AVAILABLE. The US inference profile
is ACTIVE. A later runtime probe still returned the same denial after a
propagation wait.

There is no successful Luna reply. There is no quality score. There is
no fallback model. The app is configured. The app is not operational
with Luna.

The account access team MUST resolve this gate. Operators MUST NOT
grant extra IAM permissions for this gate.

Billing tags remain on the role. IAM-principal activation waits until
invocation is available. There is no CUR export. There is no hard cap.

The unsent AWS request draft lives in
[docs/LUNA_ACCESS_REQUEST.md](../docs/LUNA_ACCESS_REQUEST.md).
Operators MUST NOT send it until the user authorizes that action.
This worker did not send the request.
This log MUST NOT record a credential, token, MFA code, or offer token.
No push or merge occurred.

## 2026-09-08 — Live Nova 2 Lite chat verified

Source: coordinator checkpoint. Feature work is PAUSED as the user requested.

Live chat is VERIFIED with Amazon Nova 2 Lite, reasoning effort `low`.
Operators updated the IAM role in place. Operators did not replace the role.
Role tags set Model to Nova 2. Role tags keep ReasoningEffort `low`.
Project and Environment billing keys are active.
Model and principal-specific activation waits for AWS appearance.

Two-servings bean tacos produced a live reply and estimate of USD 17.03.
A four-servings follow-up produced USD 18.32.
The budget 40 stayed preserved.
The form updated to 4.
The browser showed no errors.

The first live display used the wrong currency.
A later fix used server USD display.
Stored plan and evidence were not changed.

Sample catalog prices remain.
Fixture spending remains.
This record MUST NOT claim real Plaid Sandbox proof.
This record MUST NOT claim real Instacart proof.
Full manual-to-chat transfer remains unfinished.
No 90-run evaluation ran.
This record MUST NOT claim a completed AI product.

Deterministic evidence: 1,383 backend tests passed.
Eight database tests skipped.
Ruff, format, and strict mypy passed.
CDK 14 tests passed.
Helper 10 tests passed.

The one-hour MFA session expired after live verification.
Operators MUST renew MFA before the next live test.
Local commit `282f682` records the model change.
Local commit `06d41f3` records the currency display change.
No push or merge occurred.
This log MUST NOT record a credential, token, or MFA code.

## 2026-09-09 — Chat form continuity

Source: coordinator checkpoint on `codex/chat-form-continuity`.
The recorded base is `8076a65`.
This worker did not rerun the gates.

A saved manual plan now feeds chat.
Chat uses the existing `previous_job_id` and the server-loaded request.
Chat updates the shared form and estimate.
Existing cap safeguards remain in force.

Unsaved edits require rebuild.
Successful plan ownership survives reset.
Successful plan ownership survives a failed rebuild.
Stale responses MUST NOT overwrite a newer manual success.
The latest accepted estimate remains during pending, failure, and clarification.
Retry keeps the frozen original request.

Grok 4.6 wrote the source.
Grok 4.6 wrote the repairs.
Independent Codex review found four initial defects.
That reviewer approved the repair.

Coordinator backend evidence: `ruff check` passed.
Format check covered 165 files.
Strict mypy passed 85 source files.
Pytest reported 1,383 passed and 8 skipped.
One existing Starlette deprecation warning remains.

Independent frontend evidence: `npm test` reported 279 passed across 23 files.
`npm run build` passed.
Production source shows 104 added and 19 deleted across 4 files.
The added production source stays under the 150-line cap.
`git diff --check` passed.

Browser preview at `127.0.0.1:5174` rendered without overlay.
The console showed no warnings or errors.
Manual bean tacos for 2 cost USD 17.03.
Selecting pantry `black_beans` showed rebuild guidance.
The page disabled Send while the text remained editable.
Rebuild produced USD 15.74.
Rebuild re-enabled Send.
After chat failure, a further pantry edit disabled Send.
Retry remained enabled.

Live contextual chat job `74db1ab2-8736-43f2-98fa-cbcc65eb5607` failed.
The stored `error_code` is `handler_failed`.
The server payload verified `previous_request` meals `bean_tacos` for 2.
The payload also verified pantry `black_beans`, `monthly_limit_cents` 30000, and `plan_cap_cents` 4000.
This proves handoff into a server job.
This MUST NOT be read as a live model response.
This MUST NOT be read as a successful live chat-to-form update.
Expired MFA is not an established cause.
Operators MUST NOT assert that cause from this record.

Next, operators diagnose the runtime handler failure.
Operators MAY renew MFA if that diagnosis requires it.
Then operators repeat the live four-serving follow-up.
Then operators repeat the reset flow.

No AWS deployment occurred.
No AWS configuration change occurred.
No credential change occurred.
No push, pull request, or merge occurred.
The existing `5173` service is unchanged.
The `5174` preview is a separate temporary preview.
A new integration test does not directly cover a manual-only failed rebuild.
The same ownership logic covers that case.
No 90-run evaluation ran.
This record MUST NOT claim live prices.
This record MUST NOT claim Plaid proof.
This record MUST NOT claim Instacart proof.
This log MUST NOT record a credential, token, or MFA code.

## 2026-09-09 — Live continuity verification

Source: coordinator checkpoint. The user renewed MFA.
The coordinator tested the running app through isolated source preview `127.0.0.1:5174`.
The existing API and worker served the requests.
This worker did not read credentials.
This worker did not alter credentials.

Manual `bean_tacos` for 2 produced USD 17.03.
Explicit pantry `black_beans` rebuild produced USD 15.74.

Live message `Make the same meal four servings and keep my pantry items.` succeeded.
The job ID is `5613d3a5-6fcd-41d1-910e-a34e543f3294`.
The UI recipe stayed bean tacos.
Servings changed from 2 to 4.
`black_beans` stayed checked.
`black_beans` cost 0.
Required beans were 480 g.
Monthly 300 stayed unchanged.
Cap 40 stayed unchanged.
The total stayed USD 15.74.
Package purchases did not increase.

The database confirms `previous_request` `bean_tacos` 2.
The database confirms `result.request` `bean_tacos` 4.
The pantry contains `black_beans`.
The stored total is 1574 cents.

Start a new conversation cleared visible messages.
The plan remained.
Live message `Make that three servings. Keep the same meal, pantry items, and budget cap.` succeeded.
The job ID is `1a4926bd-4ef0-421b-9720-65b5c295cdd2`.
The database `previous_request` is `bean_tacos` 4.
The result is `bean_tacos` 3 with `black_beans` pantry.
The UI servings are 3.
Required beans were 360 g at cost 0.
Cap 40 stayed unchanged.
Monthly 300 stayed unchanged.
The total stayed USD 15.74.
The console showed no warnings or errors.
No framework overlay appeared.

This verifies live manual-to-chat continuity after the renewed session.
This verifies shared form and estimate updates.
This verifies reset continuity.

The prior `handler_failed` record remains historical.
This later success MUST NOT establish the exact cause of that failure.

No source fix was needed in this continuation.
Prior independent frontend evidence remains 279 tests and a passing build.
Prior backend evidence remains 1,383 tests.
This worker did not rerun those gates.
Prior reviewed regression tests cover stale form and manual responses.
Those tests include the same-render race.
This session did not recreate that race live.

This is bounded two-live-request proof.
This MUST NOT be read as a 90-run evaluation.
This MUST NOT claim production reliability.
This MUST NOT claim live prices.
This MUST NOT claim Plaid proof.
This MUST NOT claim Instacart proof.

Source remains local and uncommitted.
No push, pull request, merge, or deployment occurred.
The existing `5173` service is unchanged.
The temporary `5174` preview will close after this evidence.
This log MUST NOT record a credential, token, or MFA code.

## 2026-09-10 — OpenCode project agent setup

Added 14 project role adapters under `.opencode/agents/`.
The `tech-lead` role is a primary agent. The other roles are subagents.
Added the `fewia-workflow` skill and `.opencode/README.md`.
The adapters read canonical role scope from `.codex/agents/`.
OpenCode inherits the selected model. The CLI supervisor owns writer routing.

Grok 4.6 medium wrote the files through the development supervisor.
Two early assignments stopped on cancelled tool permission prompts.
They created no project files. Revised assignments completed without model fallback.
The independent Codex reviewer `review_opencode` reviewed the uncommitted setup
against base `8076a656a6ac0c97fafde72f2919380b96d9e431`.
The writer corrected supervisor scope, verification scope, and primary-agent wording.

OpenCode 1.18.30 discovered all 14 roles and the project skill.
Specialist task permissions deny further native delegation.
Piped skill output truncated. Redirected output parsed and confirmed the skill path.
No live model or end-to-end coding delegation probe ran.
The worktree has no Graphify graph. Review used targeted source files.

Backend verification commands and actual result summaries:

```text
uv run ruff check app tests
All checks passed!
uv run ruff format --check app tests
165 files already formatted
uv run mypy --strict app
Success: no issues found in 85 source files
uv run pytest
1377 passed, 14 skipped, 1 warning in 7.72s
```

The warning is the existing Starlette test-client deprecation warning.
The skipped tests do not establish database integration proof.
No application source, global OpenCode settings, or credentials changed.
No commit, push, or merge occurred.

The independent reviewer confirmed all three findings resolved after repair.
Skill validation returned `Skill is valid!`. Final `git diff --check` passed.

## 2026-09-10 — PR46 wiki log conflict reconciled

Grok 4.6 was the sole writer.
This worker resolved only `wiki/log.md`.
The worktree merges `origin/main` into PR46 head `9acdd643`.
Incoming main is `30c50600`.

HEAD chat continuity and live entries remain first.
The incoming OpenCode setup entry remains after those entries.
This record retains both chat evidence and OpenCode setup records.
`.opencode` files remain unchanged.

Independent verification remains pending.
This record MUST NOT claim completed checks.
This record MUST NOT claim a push.
This record MUST NOT claim a merge.

## 2026-09-10 — Remove unused Docker containers

Source: coordinator. Current `compose.yaml` defines `postgres`, `floci`,
`bootstrap`, `api`, `worker`, `sync-worker`, and `web`. Project
`fewia-grocery-b7d4` already runs that stack on loopback ports 5173, 8010,
55435, and 4567. `compose.bedrock.yaml` supplies Bedrock settings to `api`
and `worker`.

The operator removed the old `fewia` stack on ports 8000, 5432, and 4566.
The operator also removed `codex-loop-phase-2-7be440-postgres-1`,
`fewia-lease-check-b7d4`, `fewia-job-schema-check-20260905`, and the
exited `fewia-runtime-*` and `fewia-browser-*` check containers. The
OpenWebUI Docker Desktop extension stayed. Named volumes
`fewia_postgres-data` and `fewia_floci-data` stayed. After the removal,
`GET /healthz` on `127.0.0.1:8010` returned HTTP 200. The web service on
`127.0.0.1:5173` returned HTTP 200. PostgreSQL and Floci stayed healthy.

## 2026-09-10 — useHandoff hook

Feature work resumed after the user requested it.
The user reported a renewed MFA session for Bedrock.
This item does not call Bedrock.

Grok 4.6 medium wrote `frontend/src/useHandoff.ts` and
`frontend/src/useHandoff.test.ts` in worktree `/private/tmp/fewia-handoff-hook`
on branch `codex/handoff-hook`.
The hook starts and retries shopping handoffs through `handoffApi`.
It does not auto-retry.
It does not mount UI.
`useHandoff.ts` has 107 lines.

The first Grok attempt created no files after a cancelled shell command.
A revised assignment used the Write tool.
Grok then wrote the files.
A later `npm test` command was cancelled by Grok permission.
The coordinator ran the gates.

Frontend `npm test` reported 288 passed across 24 files.
`npm run build` passed.
Backend `ruff check` passed.
Format check covered 165 files.
Strict mypy passed 85 source files.
Pytest reported 1,377 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the hook.
The reviewer did not rerun the gates.
The reviewer did not call Instacart.

This is PR 1 of the handoff stack.
PR 2 is `HandoffControls`.
PR 3 wires `Estimate` and `App`.
No commit, push, or merge occurred.
This MUST NOT claim live Instacart prices.
This MUST NOT claim a 90-run evaluation.

## 2026-09-10 — HandoffControls

Grok 4.6 medium wrote `frontend/src/HandoffControls.tsx` and
`frontend/src/HandoffControls.test.tsx` in worktree
`/private/tmp/fewia-handoff-controls` on branch `codex/handoff-controls`.
The branch stacks on `codex/handoff-hook` at `174e687`.
The component is presentational. It does not fetch. It does not auto-retry.
It does not mount in `App` or `Estimate`.
`HandoffControls.tsx` has 88 lines.

Frontend `npm test` reported 298 passed across 25 files.
`npm run build` passed.
Backend `ruff check` passed.
Format check covered 165 files.
Strict mypy passed 85 source files.
Pytest reported 1,377 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the controls.
The reviewer did not rerun the gates.
The reviewer did not call Instacart.

This is PR 2 of the handoff stack.
Stacked on pull request 48. Merge that first.
PR 3 wires `Estimate` and `App`.
This MUST NOT claim live Instacart prices.

## 2026-09-10 — Wire shopping handoff controls

Grok 4.6 medium edited `frontend/src/App.tsx`, `frontend/src/App.test.tsx`,
and `frontend/src/ChatWorkspace.tsx` in worktree `/private/tmp/fewia-handoff-wire`
on branch `codex/handoff-wire`.
The branch stacks on `codex/handoff-controls` at `f6b33a3`.
`App` mounts `HandoffControls` and drives it with `useHandoff`.
Start requires Instacart configuration, an accepted plan, and a non-dirty estimate.
The footer still says `No purchases are made here.`
Added application lines: 36.

Frontend `npm test` reported 303 passed across 25 files.
`npm run build` passed.
Backend `ruff check` passed.
Format check covered 165 files.
Strict mypy passed 85 source files.
Pytest reported 1,377 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the wiring.
The reviewer did not rerun the gates.
The reviewer did not call Instacart.

This is PR 3 of the handoff stack.
Stacked on pull request 49. Merge 48, then 49, then this.
This MUST NOT claim live Instacart prices.

## 2026-09-10 — Evaluation plan inputs

Grok 4.6 medium wrote `backend/app/evaluation_plan_inputs.py` and
`backend/tests/test_evaluation_plan_inputs.py` in worktree
`/private/tmp/fewia-eval-plan-inputs` on branch `codex/evaluation-plan-inputs`.
`fixture_plan` maps corpus meal inputs through `fixture_budget` and `plan_groceries`.
Empty meals raise `MEALS_ERROR` before the planner.
Clock errors stay `CLOCK_ERROR`.
Diet conflict stays `PlanningError`.
`evaluation_plan_inputs.py` has 32 lines.

Backend `ruff check` passed.
Format check covered 167 files.
Strict mypy passed 86 source files.
Pytest reported 1,383 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the fixture.
The reviewer did not rerun the gates.

This is PR 1 of the evaluation-runner stack.
Parent: `main`.
This MUST NOT claim a 90-run evaluation.
This MUST NOT claim model quality.

## 2026-09-10 — Evaluation meal scorer

Grok 4.6 medium wrote `backend/app/evaluation_meals.py` and
`backend/tests/test_evaluation_meals.py` in worktree
`/private/tmp/fewia-eval-meal-scorer` on branch `codex/evaluation-meal-scorer`.
`evaluate_meal_case` scores meal corpus cases like `evaluate_budget_case`.
Diet-conflict variants do not inherit parent `total_cents`.
`evaluation_meals.py` has 88 lines.

Backend `ruff check` passed.
Format check covered 169 files.
Strict mypy passed 87 source files.
Pytest reported 1,389 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the scorer.
The reviewer did not rerun the gates.

This is PR 2 of the evaluation-runner stack.
Stacked on pull request 51. Merge that first.
This MUST NOT claim a 90-run evaluation.
This MUST NOT claim model quality.

## 2026-09-10 — Evaluation runner slots

Grok 4.6 medium wrote `backend/app/evaluation_runner.py` and
`backend/tests/test_evaluation_runner.py` in worktree
`/private/tmp/fewia-eval-runner` on branch `codex/evaluation-runner`.
`run_evaluation` returns 90 slots. Budget and meals are scored.
Other groups stay unassessed with `report` null.
`metrics_status` stays `unassessed`.
`evaluation_runner.py` has 75 lines.

Backend `ruff check` passed.
Format check covered 171 files.
Strict mypy passed 88 source files.
Pytest reported 1,396 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the runner.
The reviewer reran `tests/test_evaluation_runner.py` (7 passed).
The reviewer did not rerun the full suite.

This is PR 3 of the evaluation-runner stack.
Stacked on pull request 52. Merge 51, then 52, then this.
This MUST NOT claim model quality.
This MUST NOT claim live provider proof.

## 2026-09-10 — Evaluation follow-up F03

Grok 4.6 medium wrote `backend/app/evaluation_followup.py` and
`backend/tests/test_evaluation_followup.py` in worktree
`/private/tmp/fewia-eval-followup` on branch `codex/evaluation-followup`.
`evaluate_followup_case` scores F03 as `exclusion_reject`.
Exclusion errors are not `diet_conflict`.
`evaluation_followup.py` has 67 lines.

Backend `ruff check` passed.
Format check covered 173 files.
Strict mypy passed 89 source files.
Pytest reported 1,401 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the scorer.
The reviewer did not rerun the gates.

This is PR 4 of the evaluation-runner stack.
Stacked on pull request 53. Merge 51, then 52, then 53, then this.
The runner does not dispatch follow-up yet.
This MUST NOT claim model quality.

## 2026-09-10 — Runner dispatches F03

Grok 4.6 medium edited `backend/app/evaluation_runner.py` and
`backend/tests/test_evaluation_runner.py` in worktree
`/private/tmp/fewia-eval-runner-followup` on branch
`codex/evaluation-runner-followup`.
Follow-up cases with `requires_model` false go to `evaluate_followup_case`.
F01 stays unassessed. F03 scores `exclusion_reject`.
Added application lines: 3.

Backend `ruff check` passed.
Format check covered 173 files.
Strict mypy passed 89 source files.
Pytest reported 1,402 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the dispatch.
The reviewer did not rerun the gates.

This is PR 5 of the evaluation-runner stack.
Stacked on pull request 54. Merge 51 through 54 first.
This MUST NOT claim model quality.

## 2026-09-10 — Missing-price X01 scorer

Grok 4.6 medium edited `backend/app/evaluation_plan_inputs.py` and wrote
`backend/app/evaluation_missing.py` in worktree `/private/tmp/fewia-eval-missing`
on branch `codex/evaluation-missing`.
`fixture_plan` accepts an ingredients override.
`evaluate_missing_case` scores X01 as `incomplete_estimate`.
Added application lines stay under 150.

Backend `ruff check` passed.
Format check covered 175 files.
Strict mypy passed 90 source files.
Pytest reported 1,408 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the scorer.
The reviewer did not rerun the gates.

This is PR 6 of the evaluation-runner stack.
Stacked on pull request 55. Merge 51 through 55 first.
The runner does not dispatch missing yet.
This MUST NOT claim model quality.

## 2026-09-10 — Runner dispatches X01

Grok 4.6 medium edited `backend/app/evaluation_runner.py` and
`backend/tests/test_evaluation_runner.py` in worktree
`/private/tmp/fewia-eval-runner-missing` on branch
`codex/evaluation-runner-missing`.
Missing cases with `requires_model` false go to `evaluate_missing_case`.
X02 stays unassessed. X01 scores `incomplete_estimate`.
Added application lines: 3.

Backend `ruff check` passed.
Format check covered 175 files.
Strict mypy passed 90 source files.
Pytest reported 1,410 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the dispatch.
The reviewer did not rerun the gates.

This is PR 7 of the evaluation-runner stack.
Stacked on pull request 56. Merge 51 through 56 first.
Provider and adversarial groups stay unassessed.
This MUST NOT claim model quality.

## 2026-09-11 — Nutrition and supermarket-estimate contracts

Grok 4.6 medium wrote `backend/app/domain/nutrition.py` and
`backend/app/domain/supermarket_estimate.py` in worktree
`/private/tmp/fewia-nutrition-contracts` on branch `codex/nutrition-contracts`.
USDA nutrition uses integer milligrams and kcal.
Spoonacular cost uses integer cents or null.
Instacart code is unchanged.
Added application lines: 67.

Backend `ruff check` passed.
Format check covered 169 files.
Strict mypy passed 87 source files.
Pytest reported 1,394 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the contracts.
The reviewer did not rerun the gates.

This is PR 1 of the hybrid-data stack.
Parent: `main`.
This MUST NOT claim live store prices.
This MUST NOT claim medical nutrition advice.

## 2026-09-11 — Decision 0010: USDA and Spoonacular overlay

The user confirmed Instacart IDP is closed to new applicants. The user
chose USDA for stored nutrition and Spoonacular for a one-hour average
cost overlay. Instacart code stays parked. Budget cents stay on the
sample catalog.

The record is
[decisions/0010-usda-spoonacular-overlay.md](decisions/0010-usda-spoonacular-overlay.md).
No adapter code shipped in this entry. No API key was written to the wiki.

## 2026-09-11 — Frozen USDA nutrition map

Grok 4.6 medium wrote `backend/app/domain/nutrition_catalog.py` in worktree
`/private/tmp/fewia-usda-nutrition` on branch `codex/usda-nutrition-map`.
Every catalog ingredient has USDA facts per 100 g.
The map does not call USDA at runtime.
Added application lines: 36.

Backend `ruff check` passed.
Format check covered 181 files.
Strict mypy passed 93 source files.
Pytest reported 1,434 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the map.
The reviewer did not rerun the gates.

This is PR 2 of the hybrid-data stack.
Stacked on merged pull request 58.
This MUST NOT claim medical nutrition advice.

## 2026-09-11 — Spoonacular key file setting

Grok 4.6 medium added `spoonacular_key_file` to `GroceryProviderSettings`.
The field loads `FEWIA_SPOONACULAR_KEY_FILE` like Instacart.
No HTTP call shipped.
Added application lines: 6.

Backend `ruff check` passed.
Format check covered 181 files.
Strict mypy passed 93 source files.
Pytest reported 1,434 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the setting.
The reviewer did not rerun the gates.

This is PR 3 of the hybrid-data stack.
This MUST NOT record a secret.

## 2026-09-11 — Spoonacular HTTP estimate adapter

Grok 4.6 medium wrote `backend/app/providers/spoonacular.py`.
The client reads `estimatedCost` in US cents.
Successful results stay in memory for 3600 seconds.
Failures raise `SpoonacularUnavailable` and are not cached.
Planner totals do not change.
Added application lines: 106.

Backend `ruff check` passed.
Format check covered 183 files.
Strict mypy passed 94 source files.
Pytest reported 1,442 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the adapter.
The reviewer did not rerun the gates.

This is PR 4 of the hybrid-data stack.
This MUST NOT claim live store prices.
This MUST NOT record a secret.

## 2026-09-11 — Spoonacular ingredient id map

Grok 4.6 medium wrote `backend/app/domain/spoonacular_catalog.py`.
Every catalog ingredient maps to a Spoonacular id.
The module does not call HTTP.
Planner totals do not change.
Added application lines: 31.

Backend `ruff check` passed.
Format check covered 185 files.
Strict mypy passed 95 source files.
Pytest reported 1,446 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the map.
The reviewer did not rerun the gates.

This is PR 5 of the hybrid-data stack.
This MUST NOT claim live store prices.

## 2026-09-11 — Spoonacular overlay sum

Grok 4.6 medium wrote `backend/app/services/supermarket_overlay.py`.
The overlay sums Spoonacular cents for purchase lines.
Pantry lines are skipped.
Planner `total_cents` and `accepted` do not change.
Added application lines: 61.

Backend `ruff check` passed.
Format check covered 187 files.
Strict mypy passed 96 source files.
Pytest reported 1,452 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the overlay.
The reviewer did not rerun the gates.

This is PR 6 of the hybrid-data stack.
This MUST NOT claim live store prices.
This MUST NOT record a secret.

## 2026-09-11 — Spoonacular runtime factory

Grok 4.6 medium added `build_spoonacular`.
The factory reads `FEWIA_SPOONACULAR_KEY_FILE` like Instacart.
Capabilities keys do not change.
Added application lines: 18.

Backend `ruff check` passed.
Format check covered 187 files.
Strict mypy passed 96 source files.
Pytest reported 1,455 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the factory.
The reviewer did not rerun the gates.

This is PR 7 of the hybrid-data stack.
This MUST NOT record a secret.

## 2026-09-11 — Attach overlay on execute_plan

Grok 4.6 medium attached `supermarket_estimate` on `execute_plan`.
The overlay is omitted when no estimator is passed.
Planner `total_cents`, `accepted`, and `evidence_id` do not change.
Added application lines: 14.

Backend `ruff check` passed.
Format check covered 187 files.
Strict mypy passed 96 source files.
Pytest reported 1,459 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the attach.
The reviewer did not rerun the gates.

This is PR 8 of the hybrid-data stack.
This MUST NOT claim live store prices.
This MUST NOT record a secret.

## 2026-09-11 — Worker Spoonacular plan overlay

Grok 4.6 medium passed `build_spoonacular` into plan jobs.
The job result MAY include `supermarket_estimate`.
Evidence snapshots omit that key.
Chat jobs do not receive the estimator.
Invalid Spoonacular config degrades to no overlay.
Added application lines: 39.

Backend `ruff check` passed.
Format check covered 187 files.
Strict mypy passed 96 source files.
Pytest reported 1,464 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the wiring.
The reviewer did not rerun the gates.

This is PR 9 of the hybrid-data stack.
This MUST NOT claim live store prices.
This MUST NOT record a secret.

## 2026-09-12 — Frontend Spoonacular overlay label

Grok 4.6 medium showed `supermarket_estimate` on the estimate panel.
Catalog `total_cents` stays the primary total.
`parseJob` accepts a missing overlay and rejects a bad notice.
Added application lines: 56.

Frontend vitest reported 308 passed.
`tsc --noEmit` and `vite build` passed.

Independent read-only review approved the labels.
The reviewer did not rerun the gates.

This is PR 10 of the hybrid-data stack.
This MUST NOT claim live store prices.

## 2026-09-12 — USDA nutrition overlay payload

Grok 4.6 medium wrote `backend/app/services/nutrition_overlay.py`.
Plan lines copy USDA facts per 100 g.
The overlay does not scale by quantity.
Planner totals do not change.
Added application lines: 51.

Backend `ruff check` passed.
Format check covered 189 files.
Strict mypy passed 97 source files.
Pytest reported 1,467 passed and 14 skipped.
One existing Starlette deprecation warning remains.

Independent read-only review approved the payload.
The reviewer did not rerun the gates.

This is PR 11 of the hybrid-data stack.
This MUST NOT claim medical nutrition advice.

## 2026-09-18 — Dynamic delegated reasoning effort

Workflow documentation now records the implemented supervisor effort policy.
The coordinator classifies each task before delegation.
Complexity maps to automatic effort: `simple` to `low`, `standard` to
`medium`, `complex` to `high`, `exceptional` to `xhigh`, `maximum` to `max`.
Grok 4.6 uses `low` for simple tasks.
Grok 4.6 uses `medium` for every harder automatic tier.
Grok 4.6 MUST NOT receive `high`, `xhigh`, or `max`.
Spark keeps its CLI model default.
Spark does not accept an effort override in this supervisor.
Luna and Sol support automatic selection through `max`.
The supervisor requires `--complexity`.
An optional `--effort` override MUST stay within the model ceiling.
An explicit incompatible effort stops with an error.
The supervisor MUST NOT silently downgrade it.
Native role files keep the Luna model.
They MUST NOT pin `model_reasoning_effort`.
Native dispatch MUST select effort from the complexity rubric.
The coordinator MUST NOT select `maximum` for ordinary tasks.

The coordinator supplied these targeted supervisor results.
This log does not claim full backend gates or independent review.

```text
PYTHONPATH=. uv run --project backend pytest -q tests/supervisor
38 passed in 2.35s
uv run --project backend ruff check dev_supervisor tests/supervisor
All checks passed!
uv run --project backend ruff format --check dev_supervisor tests/supervisor
11 files already formatted
uv run --project backend mypy --strict dev_supervisor
Success: no issues found in 6 source files
```

The coordinator later verified these root backend results. This log does not claim independent review. `cd backend && uv run ruff check app tests` reported `All checks passed!`. `cd backend && uv run ruff format --check app tests` reported `189 files already formatted`. `cd backend && uv run mypy --strict app` reported `Success: no issues found in 97 source files`. `cd backend && uv run pytest` reported `1467 passed, 14 skipped, 1 warning in 6.29s`. The warning is the existing Starlette `httpx` deprecation warning.

The final supervisor suite reported `49 passed in 2.57s`. Supervisor Ruff reported `All checks passed!`. Supervisor format reported `11 files already formatted`. Supervisor strict mypy reported `Success: no issues found in 6 source files`. The change adds 135 application lines, under the 150-line cap. Independent read-only review approved the result with no actionable findings. The reviewer did not edit files. The reviewer verified the registry guard, explicit-effort fallback behavior, operational documentation, and registered-model fallback test.

## 2026-09-18 — Tool-calling orchestration direction

Accepted tool calling as the FEWIA orchestration boundary.
The Bedrock model passes structured intent to high-level tools.
Backend services own Plaid data, arithmetic, planning, nutrition, validation,
and evidence.

Added [decision 0012](decisions/0012-tool-calling-orchestration.md) and linked
it from the wiki index. Graphify saved and reflected the decision as a useful
architecture memory.

Updated the course proposal with the tool-calling boundary. Two LaTeX compile
passes succeeded. The PDF remains one letter-size page. The rendered page has
no clipped or overlapping content.

No application code changed. Backend and frontend tests were not run.

## 2026-09-18 — Concurrent wiki decision reconciliation

Preserved the dynamic delegated effort record as decision 0011.
Renumbered the tool-calling orchestration record as decision 0012.
The wiki index links both accepted decisions.

No application code changed. Backend and frontend tests were not run.

## 2026-09-19 — Nutrition planning, chat, evidence, and handoff

Grok wrote nutrition planning, chat, and evidence integration.
Handoff compares optional nutrition and preserves legacy results.
Sample catalog money stays unchanged.
Frontend nutrient display remains future work.

Coordinator baseline: ruff was clean. Format covered 191 files.
Strict mypy covered 98 files. Pytest reported 1507 PostgreSQL tests
passed with 1 Starlette warning. Frontend reported 308 tests and a
passed build. Supervisor reported 52 tests. Helper reported 10 tests.

Isolated Compose `fewia-verify-70fa` used ports 5175, 8012, 55436, and
4568. Bootstrap and health passed. Runtime smoke verified two-serving
bean tacos at 1703 cents. Stored evidence matched `meal_nutrition`
exactly.

Shared default stack startup failed migration.
Older demos occupy 5173 and 8010.

Two original Grok attempts failed without edits.
A later run observed cancellation after a terminal-tool failure.
File-only writers then succeeded.

Initial changed-code full test runs had 12 then 9 handoff failures.
This entry does not claim final checks or review of the fixture repair.

Coordinator copied three nutrition regression tests onto original
HEAD `53cc632` in a temporary directory. All three failed as expected
(3 failed, 25 deselected): `execute_plan_returns_json_native_meal_nutrition`,
`pantry_does_not_change_meal_nutrition`, and
`changed_nutrition_changes_evidence_id`.

Independent read-only Grok review completed: APPROVE, confidence 7/10,
no blocking source findings. The reviewer inspected source before the
fixture-only repair. The reviewer did not run gates. Reviewer checkpoint
`.fewia-supervisor-kt1eg41q`. Base `53cc632`.

This log does not claim live Bedrock, Plaid, or Spoonacular evidence.
This log does not claim a deployment.
The coordinator will supply final gate evidence separately.

## 2026-09-19 — Frontend meal nutrition contracts

Grok 4.6 added frontend types for `meal_nutrition` payloads.
Grok 4.6 added strict validation for those payloads.
The payloads cover manual grocery-job and chat-job requests.
Chat-to-estimate conversion preserves nutrition.
The conversion deep-copies nutrition.
Nutrition does not change sample-catalog pricing.
Nutrition does not change plan acceptance.
The estimate panel does not render nutrition yet.
Added application lines: 122.

The coordinator fixed the Grok workflow.
The coordinator used the verified file-only supervisor from local branch `codex/grok-permission-diagnostics`.
That supervisor exposes `Read`, `Edit`, and `Write` only.
Earlier default-tool runs ended as `task_failed` when Grok attempted terminal work.

Frontend verification: 25 files and 315 tests passed.
The production build passed.

Backend verification: ruff passed.
Format covered 191 files.
Strict mypy passed on 98 source files.
Pytest reported 1,501 passed with 14 skipped.
One existing Starlette warning remains.

An isolated mutation removed the chat-to-estimate nutrition clone.
The focused test failed as expected: 1 failed and 12 passed.

Independent read-only Grok review returned `APPROVE`.
Confidence is 8/10.
The reviewer found no blocking findings.
The reviewer did not rerun commands.

Branch: `codex/nutrition-frontend`.
No push or merge occurred.
This log MUST NOT claim live provider evidence.
This log MUST NOT claim browser verification.

## 2026-09-21 — Frontend nutrition compatibility integration

The coordinator recovered the Grok nutrition contract changes from
`codex/nutrition-frontend`. Grok 4.6 medium added legacy response support.
Older manual and chat plans remain usable without nutrition.
Malformed supplied nutrition remains invalid. Present nutrition is copied.

Frontend tests reported 316 passed. The production build passed.
Backend Ruff reported `All checks passed!`. Format reported
`191 files already formatted`. Strict mypy passed 98 source files.
The isolated PostgreSQL run reported 1515 passed and one Starlette warning.
The earlier default run reported 1501 passed and 14 skipped.
Independent review of the compatibility change remains pending.
No live provider verification occurred.

## 2026-09-25 — Claude Code senior and junior loop

The user asked for a senior and junior agent loop in Claude Code.
[Decision 0013](decisions/0013-claude-senior-coordinator.md) records it.
`CLAUDE.md` now makes the main session the coordinator.
Thirteen junior adapters in `.claude/agents/` mirror the Codex roles.
The stale health-era Claude definitions are replaced.
The Claude `tech-lead` subagent is removed.
A new `code-reviewer` role exists for Codex, OpenCode, and Claude Code.
The `/feature-loop` skill holds the procedure, the brief template, the
junior and reviewer protocols, and the ledger template.
No application code changed. No loop has run yet.

## 2026-09-25 — Tiered delegation for every coordinator tool

[Decision 0014](decisions/0014-tiered-delegation.md) is in place. Claude
Code, Codex, and OpenCode follow one rulebook, `docs/DELEGATION.md`. Tiers
S, M, and L scale the process to each work item.

Shared tooling merged:

- #166: writers edit files only. `--task` must be a file. A pre-launch
  failure releases the lease.
- #167, #168, #170: `dev_supervisor.gates` runs only the checks for the
  changed paths. It records results by SHA and supports `--reuse`.
- #169, #171: `dev_supervisor.review` runs a read-only, time-capped Codex
  review with short output.
- #172, #173: the usage ledger records writer and review tokens and time.
  `dev_supervisor.usage` prints the totals.

Rules and adapters merged in #174, #175, and #176.

Review found real defects in the new tooling:

- a verdict that the command made up itself;
- a stale report that a re-run read;
- a git failure reported as a pass;
- timeouts that left child processes running;
- coverage that hid runs without token data.

A live review exposed that the verdict parser rejected a bolded verdict.
#171 fixed it.

Codex returned 401 for every call during an OpenAI incident. Reviews ran
in separate read-only Grok sessions until Codex recovered.

Pilot, three tier S items, #177 to #179: no subagents ran. Review model
runs took 11 to 37 seconds and used 36,307 to 212,200 input tokens. Grok
writer runs took 16 to 138 seconds; Grok reports no token data. In Phase
1, comparable one-to-six-line items used about 150,000 subagent tokens
each.

Tier M juniors in this stack still used 125,000 to 295,000 subagent
tokens each. Code compression, drafting code for the writer, and
repeated repairs drove that cost. The rulebook now forbids the first two.

Follow-ups:

- A timing-sensitive test in `tests/supervisor` fails under parallel load.
- `dev_supervisor.review` needs a Grok provider fallback.
- The subagent handback resends reports; the coordinator ignores duplicates.

## 2026-09-25 — Document shared and frontend checks

The root README.md Checks section now starts with the shared gates
command. Frontend checks now include `npm run lint`.

This item was the first Codex coordinator trial of decision 0014. Codex,
as `tech-lead`, chose tier S. It ran the Grok writer through
`dev_supervisor`, committed, ran the gates (`RESULT PASS`, docs only), and
ran the review command. The review command failed inside the Codex
sandbox, so Codex used the documented read-only Grok review, which
returned APPROVE. No subagents ran.

## 2026-09-27 — User-entered budget and nutrition display

Loop `frontend-ux`. The user paused Plaid until the end of the project.
The budget now starts from the amount that the user enters.

- [#183](https://github.com/emanuelGitCodes/fewia/pull/183): the frontend
  accepts the `manual` spending source. 27 added code lines.
- [#184](https://github.com/emanuelGitCodes/fewia/pull/184): the backend
  default is `manual`. `SpendingSource` lives in `app/domain/budget.py`.
  38 added code lines.
- [#185](https://github.com/emanuelGitCodes/fewia/pull/185): the estimate
  shows USDA nutrition. 48 added code lines.

Manual-to-chat transfer and saved-plan transfer shipped on 2026-09-09.
The checkpoint page listed them as unfinished.

A browser preview showed $100 available for a $100 limit, a $17.03 bean
tacos estimate, and a 758 kcal nutrition total. The preview found three
UX gaps: the form defaults ($300 limit, $40 cap), the source label
wording, and the unstyled nutrition list.

Writer: grok-4.6 on every item. Review: gpt-6-luna APPROVE on each head.
#184 took four review rounds; the user authorized the fourth. Subagent
tokens: 52,273, 140,913, and 43,785. Review input tokens: 105,666,
531,436, and 110,368.

## 2026-09-27 — Spoonacular prices at read time

Loop `spoonacular-prices`. Decision
[0016](decisions/0016-spoonacular-read-time-overlay.md) records the rules.

- [#186](https://github.com/emanuelGitCodes/fewia/pull/186): per-line
  Spoonacular overlay and `attach_supermarket_estimate`. 116 lines.
- [#187](https://github.com/emanuelGitCodes/fewia/pull/187): the API adds
  the overlay at read time. The worker stores none. 51 lines.
- [#188](https://github.com/emanuelGitCodes/fewia/pull/188):
  `compose.spoonacular.yaml`. 14 lines.
- [#189](https://github.com/emanuelGitCodes/fewia/pull/189): per-line
  Spoonacular prices in grocery and chat estimates. 71 lines.
- [#190](https://github.com/emanuelGitCodes/fewia/pull/190):
  `python -m app.usda_refresh`. 148 lines.

Merged `main` at `e818333`: backend 1,549 passed and 14 skipped; ruff and
strict mypy pass. Frontend 336 tests pass; lint and build pass.

Writer: grok-4.6 on every item. Review: gpt-6-luna APPROVE on each head.
#190 took six review rounds; the user authorized rounds four to six. Two
of those rounds corrected the coordinator's brief: the USDA field names
and the `abridged` format, which rounds values. A public `DEMO_KEY` fetch
of FDC 173735 confirmed both. Subagent tokens: 59,212, 92,561, 79,084, and
191,244; #188 ran as tier S with no subagent. Review input tokens:
204,844, 371,030, 34,520, 205,644, and 397,715.

Follow-ups:

- Two juniors wrote one scratchpad script name, and one gate run used the
  wrong worktree. Briefs now require a work-item prefix for helper scripts.
- Local job rows written before #187 can hold a stored Spoonacular total.
  Deleting them needs a retention decision.
- No run against live Spoonacular or all 22 USDA ids with the operator key.

## 2026-09-29 — Tech-debt audit, Phases 1 to 3

An audit ranked the debt by (impact + risk) × (6 − effort). Phase 1 fixes
documentation drift, unused ML dependencies, CI permissions, a compose
validation job, and a Postgres image pin. Phase 2 enables the `BLE` and
`DTZ` lint rules in the backend and adds a notice parity test. Phase 3
shares the HTTP and AWS client settings, one `DEMO_USER_ID`, one job
lookup, and one frontend polling hook. Phase 4 is paused: the Plaid
decision, React 19, and ESLint 10.

Two audit findings were already fixed. CI sets `FEWIA_REQUIRE_DB=1`, and
the Floci image ships its own healthcheck.

## 2026-09-29 — Codex writers read files with read-only shell

The writer prompt forbade every shell command. Codex writers read files only
through a shell tool. In the `tech-debt-2` loop, `gpt-6.1-sol` and
`gpt-6-luna` read nothing, edited nothing, and still ended as `completed`.
Sol did this on three items. Luna did it on two of five runs. A direct
`codex exec` run without the rule wrote files.

A Grok writer keeps the no-shell rule. A Codex writer now MAY run read-only
shell commands. It still runs no tests, package managers, or git commands.
A run that changes no owned file now ends as `no_edits`, and the supervisor
tries the next model. The user chose this option on 2026-09-29.

## 2026-09-30 — Route writers by difficulty

Decision 0015 routes each work item to one rung of a writer ladder: Luna
`xhigh`, Grok `low`, Grok `medium`, Sol `medium`, and Sol `high`. The
Artificial Analysis Intelligence Index v4.3.2 scores set the order. `docs/DELEGATION.md`,
`docs/DEV_SUPERVISOR.md`, `.codex/TEAM.md`, and both coordinator skills
now name this rule. The supervisor code did not change.

Tier L no longer spawns a reviewer agent. The coordinator runs the probes,
and the review model gives the verdict.

## 2026-09-30 — Merge the writer routing stack

Pull requests #203 and #204 merged as `3fb78ea` and `efa0c7d`. Writers now
follow the ladder in decision 0015. Tier L runs coordinator probes, and the
review model gives the verdict. The Claude Code and OpenCode `code-reviewer`
subagents are deleted. The Codex `code-reviewer` role stays, because
`dev_supervisor.review` reads it. `gpt-6.1-sol` at `medium` reviewed both
items. Item 01 (the ladder) needed three rounds. Item 02 (the tier L
change) needed four; the user asked for the fourth to fix a non-blocking
count in `.opencode/README.md`. All findings were documentation conflicts.
The gates had no checks for these paths. No writer or tier L probe run has
used the new rules yet.

## 2026-09-30 — Verify the exclusion fix on Compose

Pull requests #206, #207, and #208 merged as `4e5412d`, `9445d84`, and
`1cc891c`. A Compose stack from a clean `1cc891c` checkout confirmed the fix
end to end. A job for `vegetable_pasta` with the `onion` exclusion returned
202 and then failed with `exclusion_reject`. Its `result` was null, and its
`error_detail` named the recipe and the ingredient. The worker wrote one
`job_failed` JSON line with no request text. A request with
`pantry_ingredients` `["white_rice"]` returned 422 for an unknown ingredient
ID, because the catalog ID for white rice is `rice`. The web UI showed the
same job failure in the Estimate panel. Its message starts with "The grocery
request failed." and then names the meal, the excluded ingredient, and the
fix.

## 2026-09-30 — Surface the exclusion conflict in chat and conversation

Pull requests #210 and #211 merged as `3195db8` and `96275ff`. For an
`exclusion_reject` error, `chat_dispatch.dispatch` now sends Bedrock a
static tool error with the catalog `recipe_id` and `ingredient_id`. All
other `PlanningToolError` cases still send "arguments are invalid". The
conversation panel now shows the same exclusion text as the Estimate
panel. The shared text is in `frontend/src/exclusionMessage.ts`.

Item 01 was tier L with `grok-4.6` at `low`. Item 02 was tier M with
`grok-4.6` at `medium`. In each item, a coordinator mutation passed every
test. In item 01, the mutation removed the `error_code` check. In item 02,
it removed the catalog props from `App.tsx`. One test-only repair closed
each gap. The first review of item 02 returned `REQUEST_CHANGES`, because
the brief did not list `App.test.tsx`. The coordinator had assigned that
file in the repair. The coordinator corrected the brief, and the second
review approved the same SHA. `gpt-6-luna` reviewed both items. Item 01
used `high` effort and item 02 used `medium`.

Loop total: 4 writer runs in 327 seconds, with no writer token counts.
Review tokens were 214k in and 2.9k out over 3 runs. No subagents ran. Not
verified: a live Bedrock turn with the new tool error, and the
conversation panel in a browser.

## 2026-10-01 — Medium backlog: settings, commits, retirement, chat, React 19

The `medium-backlog` loop shipped twelve pull requests. Each merged into
`main` after green CI and an `APPROVE` review on the head SHA.

| Item | Pull request | Change |
|---|---|---|
| 01 | #215 | `usda_refresh` reads `FEWIA_USDA_FDC_KEY_FILE` through `GroceryProviderSettings`. No `os.environ` read remains in `backend/app`. `config.Settings` drops the unused `env_file`. |
| 02 | #218 | `job_submission.reuse_job` and `submit_job` own the job reuse, race, and commit flow. No route in `app/api` calls `commit()`. |
| 03 | #216 | The `/context` and `/predict` routes, the health-era tools, and `app/synth` are removed. The health tables and `models.py` stay until a retention decision. |
| 05 | #217 | An unknown recipe ID gives Bedrock a static `unsupported_recipe` tool error with the catalog IDs. The prompt asks for up to three catalog meals in plain words. |
| 07 | #220 | The conversation panel shows the named exclusion text for a rejected build. |
| 06a, 06b, 06c | #219, #222, #221 | Every frontend test uses Testing Library under `jsdom`. |
| 06d | #223 | React 19.3. `react-test-renderer` is removed. Twelve files import the `JSX` type from `react`. |
| 06e | #224 | ESLint 10 and `eslint-plugin-react-hooks` 7. Two static API errors carry `cause`. |
| 08 | #225 | The web image sends `Cache-Control: no-cache` for `index.html` and a one-year `immutable` header for hashed assets. A missing asset returns 404 without that header. |

The user chose the settings scope: database settings stay separate, so a bad
provider setting cannot stop the database engine.

Live checks on the Compose stack with Amazon Nova 2 Lite:

- A chat request for vegetable pasta without onion got the
  `exclusion_reject` tool error. The reply named the conflict.
- A chat request for vegetarian sushi got three catalog meals in plain words
  and a question. The model answered from the prompt rule and did not call
  the tool, so the live tool-error path for `unsupported_recipe` is not
  observed.
- `/context/health` and `/predict/activity` return 404. A grocery job
  replay returns 202, and a changed body with the same key returns 409.
- In the browser, a manual vegetable pasta build with the onion exclusion
  first showed the named text only in the Estimate panel. Item 07 fixed the
  conversation panel, and a second browser check confirmed both panels.

Test conversion evidence: each converted file kept its test count. For 20
source mutations, the converted tests and the original
`react-test-renderer` tests failed the same number of tests.

Item 02 ran its gates against an isolated migrated PostgreSQL database with
`FEWIA_REQUIRE_DB=1`. Six mutations of `job_submission.py` were all caught.

Loop cost: Codex writers used 5.73M input tokens over 12 runs. Grok
writers report no token counts. Review runs: 15, with 1.70M input tokens.
No subagents ran.

Item 08 started from a browser check: after a web image rebuild, the
browser kept the old `index.html` and showed "The provider configuration
is unavailable" until a forced reload.

Writers cannot delete files. In item 03, the coordinator deleted the
health-era files with `git rm` before the writer run.

## 2026-10-02 — Easy backlog: styles, defaults, usage, live providers

The `easy-backlog` loop shipped five pull requests. Each merged into `main`
after green CI and an `APPROVE` review on the head SHA.

| Item | Pull request | Merge commit | Change |
|---|---|---|---|
| 01 | #227 | `69968a9` | `estimate.css` styles every class in `Nutrition.tsx`. |
| 02 | #228 | `0f010a0` | `initialForm()` starts at a $100 monthly limit. The $40 cap stays. |
| 04 | #229 | `ae6bfc4` | `first_error()` reads `error.message` from a `turn.failed` event. |
| 07 | #230 | `04c7f13` | The usage ledger records Grok writer tokens from the `end` event of `streaming-json` output. |
| 10 | #231 | `a62c58b` | The Spoonacular parser accepts the live cost unit `cents`. |

Item 03 changed local configuration only. The USDA key moved from `.env` to
`~/.config/fewia/usda.key` with mode 600. `.env` no longer sets
`FEWIA_SPOONACULAR_KEY` or `FEWIA_USDA_FDC_KEY`.

Item 05 was dropped. Commit `85f4388` fixed the flaky
`test_active_tool_cannot_be_declared_stalled` on 2026-09-30. All 26 Tooling
runs since then passed. The test passed 25 of 25 runs under CPU load.

Item 06 is a repository setting. The user enables secret scanning and push
protection.

Live checks on the Compose stack at `a62c58b`:

- **Spoonacular.** Before #231, every overlay line was null. The live API
  returns `{"value": 26.41, "unit": "cents"}`, and the parser accepted only
  `US Cents`. After #231, bean tacos for two show a 168-cent Spoonacular
  average over seven lines. The sample estimate stays 1,703 cents. No job
  row stores the overlay.
- **USDA.** `python -m app.usda_refresh` fetched all 22 FDC records.
  Twenty match the stored facts. `oat_milk` differs: protein 800 mg stored
  and 797 mg live, fat 2,750 mg stored and 2,749 mg live.
- **Bedrock.** Four chat requests for meals outside the catalog got a
  clarification with catalog meals. Nova 2 Lite did not call the tool, so
  the `unsupported_recipe` tool error stays unobserved live. One reply used
  `**` bold text. One reply listed catalog IDs in parentheses.
- **Browser.** The form shows $100 and $40. The nutrition section and the
  Spoonacular lines render.
- **Web proxy.** After `api` was recreated, the web container returned 502
  until it restarted. nginx resolves `api` once at start.

Loop cost: Codex writers used 732k input tokens over 4 runs. Two Grok
writer runs ran before #230 and have no token counts. Review runs: 6, with
430k input tokens. No subagents ran.

## 2026-10-02 — Moderate item 06 local complete

nginx resolves the API address again after container recreation. Disposable Docker probe passed config syntax, prefix and query forwarding, and API IP replacement without restarting web. File: `frontend/nginx.conf`. Local only. No push, merge, or deployment.

## 2026-10-02 — Moderate item 07 local complete

Intermediate model turns replay validated tool calls only. Incidental prose and hidden reasoning stay out of replay. Existing user-visible conversation history remains. File: `backend/app/agent/chat_loop.py`.

## 2026-10-02 — Moderate item 08 local complete

Server context exposes the explicit plan cap. The prompt preserves a lower-only cap and latest pantry changes. The prompt derives every known ingredient ID and name pair from the catalog. Files: `backend/app/agent/chat_context.py`, `chat_loop.py`, `backend/app/services/chat_job.py`.

## 2026-10-02 — Moderate item 09 local complete

Public answers derive totals, acceptance, missing prices, and conflicts from validated tools. The UI keeps Previous estimates for unresolved requests. Valid missing-price plans replace old estimates. Manual rebuild start generations prevent old success from clearing a newer unresolved chat. Files: `backend/app/agent/chat_answer.py`, `frontend/src/ChatWorkspace.tsx`, `App.tsx`.

## 2026-10-02 — Moderate item 10 local complete

The refusal parser uses bounded JSON with duplicate, extra-key, and type guards. Fixed text covers secrets, purchases, and external URLs. A refusal shows no public plan or evidence. Files: `backend/app/agent/chat_refusal.py`, `chat_loop.py`.

## 2026-10-02 — Moderate item 11 local complete

Unsupported diet and ingredient errors are typed with bounded static clarification. Unknown values are not echoed or guessed. Files: `backend/app/agent/planning_tool.py`, `chat_dispatch.py`, `chat_answer.py`.

## 2026-10-02 — Moderate item 12 local complete

Read-only `get_budget_summary` accepts only an empty exact dict. Budget, period, and source stay server-owned. Display uses formatted USD. Pending cents and a canonical stale warning stay separate. A successful summary preserves an existing candidate. Files: `backend/app/agent/budget_tool.py`, `chat_dispatch.py`, `chat_loop.py`.

## 2026-10-02 — Moderate item 13 partial pending retention

API reads strip old price overlays from copied results before optional current overlay attachment. Stored data is preserved. Table deletion needs a separate retention decision under `.codex/project-context.md` and decision 0016. Local read-only aggregates: daily_environment 360, daily_finance 360, daily_health 341; total 1061. model_runs 0, predictions 0, jobs with stored root overlay 0, evidence snapshots with overlay at any depth 0. No row contents were read. No original records or schema changed.

## 2026-10-02 — Moderate item 14 local complete

The catalog supports 40 meals at `sample-prices-v2`. The original 10 recipes, quantities, and prices remain. Existing 22 mapped ingredients remain. Files: `backend/app/domain/catalog.py`, `catalog_recipes.json`, `grocery.py`.

## 2026-10-02 — Moderate item 15 local complete

Six deterministic preset combinations use a bounded immutable cache. `POST /grocery/templates` applies server budget filtering and static validation errors. The typed client rejects malformed, stale, and over-budget responses. Meal ideas UI uses current controls, explicit servings and selection, preserves other fields, and requires Build my estimate. Files: `backend/app/services/plan_templates.py`, `backend/app/api/plan_templates.py`, `frontend/src/templateApi.ts`, `useTemplateSuggestions.ts`, `TemplatePicker.tsx`.

## 2026-10-02 — Moderate backlog loop verification and usage

Nine Moderate items are complete locally at application head `ef586c142f4e9e7f93741ee7ab5fb1b0b9d98149`. Item 13 remains partial. Backend 1678 passed at core `c3f72fc` with isolated PostgreSQL. Final frontend lint, tests, and production build passed. Luna approved final core high, template hook medium, final picker medium, and current-scope docs low. Live Nova 2 Lite: bean tacos 2 with olive oil 1104 cents, without oil 1703 cents, cap 2500 preserved. Browser accepted a 2299-cent plan from three meals. No 90-run evaluation, live Plaid, Instacart checkout, or live store prices. Supervisor totals before this completion-record writer: 39 writer runs, 22137248 input tokens, 489546 output tokens, 7781.391 process seconds; 34 review runs, 4106580 input tokens, 55977 output tokens, 1725.473 process seconds. Details: [phases/moderate-backlog.md](phases/moderate-backlog.md).

## 2026-10-02 — Moderate backlog publication

The user authorized publication. Twelve branches were pushed without force. Pull requests #233 through #244 were created in numeric merge order. They are open and unmerged. First: [https://github.com/emanuelGitCodes/fewia/pull/233](https://github.com/emanuelGitCodes/fewia/pull/233) Last: [https://github.com/emanuelGitCodes/fewia/pull/244](https://github.com/emanuelGitCodes/fewia/pull/244) Published budget-foundation head is `ab7b914962af0bde3d59d8515d71a6f35a2b6819`. Main was not pushed or merged. Current CI status is available on the pull requests. No deployment. Details: [phases/moderate-backlog.md](phases/moderate-backlog.md).

## 2026-10-02 — Second easy backlog and the moderate stack on main

The `easy-backlog-2` loop closed the easy items from the second open-feature
list.

| Item | Pull request | Merge commit | Change |
|---|---|---|---|
| 03 | #245 | `5747b3e` | Decision 0017 accepts the 40-meal catalog. |
| 04 | #246 | `ad5a765` | `oat_milk` stores the full-precision USDA values: protein 797 mg, fat 2,749 mg. The fixture row changes with it. |
| 07 | #247 | `61e689a` | Grok reviews run with `streaming-json`. `grok_report()` rebuilds the report text and reads tokens from the `end` event. |
| 05 | #248 | via #249 | Two `chat_answer` tests: a non-integer plan total, and vegan-only examples. |

Item 02 is a repository setting. The user enables secret scanning and push
protection. Item 06 is confirmed: the Grok writer for item 05 recorded
334,542 input tokens, and a live Grok review recorded 39,509 input tokens.
Item 08 is closed: in six live chat requests for meals outside the catalog,
Nova 2 Lite answered from the prompt rule and did not call the tool. Item 09
is dropped, because #234 replaces the model reply with a server template.

After the change in #246, `python -m app.usda_refresh` reports no
differences for all 22 records. Before #248, removing the total guard or
changing `vegan` to `vegetarian` in `chat_answer.py` left every test
passing. After #248, each mutation fails one test.

Pull requests #234 through #244 and #248 merged into their parent branches,
not into `main`. Only #233 reached `main`. The coordinator built the
branch `claude/stack-to-main` from `codex/moderate-completion-records`, the
#244 head, and merged `main` and `codex/moderate-answers` into it. Pull
request #249 merged that branch into `main` at `8859d5e`. Commit `ab7b914`
is not in that history. Its test is already in
`backend/tests/test_budget_tool.py`. The auto-mode classifier blocked the
coordinator from merging the stack, because the coordinator had reviewed
only #233 and #234. The user merged the stack and #249.

Gates on the #249 head passed: backend 1,669 tests, and frontend lint,
tests, and build. Live checks on the rebuilt Compose stack at `8859d5e`:

- The config lists 40 recipes at `sample-prices-v2`.
- "Plan chicken curry for 2." planned through the tool. The template reply
  gave USD $24.12.
- A request to buy groceries with a card got the fixed refusal, with no
  tool call and no plan.
- "How much budget do I have left?" called `get_budget_summary` and
  reported USD $40.00 available.
- `POST /grocery/templates` for a vegan diet returned five suggestions.
- In the browser, "Find meal ideas" listed suggestions. The console had no
  errors.

Loop cost: writers used 1.43M input tokens over 5 runs (Luna 404k, Grok
1.02M). Review runs: 6, with 613k input tokens. No subagents ran.

## 2026-10-02 — Evaluation component 01 local integration

Bound evaluation meal inputs (`72c7c15d12c6f7660e78e4255a33d5d691d95c70`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 02a local integration

Validate evaluation result shapes (`922d2fd20cd5ce3f25fcf8e7e11303461c4a0d3b`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 03 local integration

Add reproducible evaluation manifest (`0e84ea50e3196fffc8c574f95460f2196827d124`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 05 local integration

Fix evaluation evidence table typing (`b7f14d0ebe9836b93f68ad7f365d1aa4b648309e`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 06a local integration

Use aware datetime in schema test (`0ca7d4768c6547e6334e83a770ffbdbd60798fb0`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 06 local integration

Use strict plan observation parser (`77e4e740a3e264f7e7d996c568b8f18137ad5f3e`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 08a local integration

Wrap outcome proposition pattern (`c784f23a9e97a57e207379cef88644da8159a982`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 09 local integration

Reject undeclared nested result fields (`ff6af2c89921e2274a46367fb9e47491dee7e1be`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 10 local integration

Reject blank evaluation case identities (`b14218bb169e6d139705d1e4b788a273fa3d5ba5`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 12a local integration

Add controlled evaluation fault provider (`aad209c98eac753b4a0446b40d4f3752aab4098e`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 12 local integration

Use approved provider for protocol evaluation (`24eb4f4d1e2d1bcf913773f36ba7432cb406d682`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 13 local integration

Handle fixture database cleanup errors (`6ad9a159a9e25a12c31539687771fb9a366cae40`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 14 local integration

Mark refresh evaluation redaction boundary (`0499568f23bb6ebaee041b03d33a9565061321ed`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 15 local integration

Mark handoff evaluation redaction boundary (`9c66687508735bc9172246bf7fbcf117ade18f33`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 16 local integration

Evaluate duplicate worker delivery (`31a0bed32c8f2e1f2231c96e604007401bd4d156`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 17 local integration

Skip reasoning values during sanitization (`051b8860b93f067195f4434aa76fce9c1175b10e`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 18 local integration

Require plan integrity for over-budget claims (`e1863b0253e2c7a4098037577412d0d9eed50b79`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 19 local integration

Fix deterministic reference evidence paths (`96d56255eb275928c03e2db423f728ef1e58cf94`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 20 local integration

Make frozen matrix mutation test lint clean (`33c8bb707364fd627662fdda7267bc3d1a718d55`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 24 local integration

Add evaluation telemetry aggregation (`ab6997dc53893a5e81fa466fe377f94bbfdae0e2`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 25 local integration

Add evidence-aware evaluation cost (`e544b9a642c37a06e559c3d157b83f0afb1040ee`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 26 local integration

Fix evaluation IO import order (`d7698872e32928e112b7b363931c1540f473200b`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 14a local integration

Add isolated Plaid refresh evaluation fixture (`2460154c34546d5482cf84f477c0ffd02472ff4b`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 16a local integration

Count only validated duplicate handler calls (`1dcde961dfc98d465f5b722b86e21698aaf0844a`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 26a local integration

Add evaluation JSON helpers (`61ffa0cb27cae2c03aa9cc10d133e2ab2bc277ae`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 18a local integration

Use direct frozen claim test assignments (`88d5a6203211469be53e7ecf79184e56a2d590ad`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 25a local integration

Add immutable evaluation rates (`7bbf47e3330c1ebceeec4a34b7f3ff0e51274266`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 23a local integration

Validate evaluation assessment scopes (`8bcb36a6af7ebbaad0869515e3e2ec1f603e77ae`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 23b local integration

Summarize classified evaluation tasks (`29acb00ce9a59b01efd3f025f93d8c5e7dff795c`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 23a_counts local integration

Add strict evaluation metric count helpers (`fb188743bdd6deb099daafc6c14ff87905994255`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 23b_validation local integration

Require applicable task assessments (`8d81ae45f4ea398f624691b3e140929ec5ab3bad`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 27a local integration

Bound Markdown integer cells (`d37f69e86fd1a03194f08277df2a19c69184b739`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 23a_checks local integration

Validate safe summary check records (`a89ad21401d3fb852824235f3357d3c1e7def2f9`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 23b_assessments local integration

Add evaluation assessment classification (`f250d25e5093cfbaa113e18effaf7b76483907d9`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation component 30 local integration

Test the required evaluation database guard (`8d6beab5b9039fd2e6d3bacff45e6b88629aa208`) is included as a locally reviewed integration component in snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf`.

## 2026-10-02 — Evaluation loop checkpoint

Snapshot `aa7fac9d9e79b3e81bf2ad36c044b3fab8f88eaf` was captured at `2026-10-03T03:11:58.118465+00:00`. Recorded gates passed: Ruff check (`All checks passed!`), Ruff format (`260 files already formatted`), mypy (`Success: no issues found in 129 source files`), and pytest (`5,942 passed, 1 warning in 12.19s`). Evidence is component-only: nine smoke observations passed (five deterministic references and four controlled provider cases), with 42 scored and 48 unassessed legacy slots and zero live model calls; duplicate-delivery smoke passed 18 checks with a deterministic fake and no live providers. The full 90-primary/138-total benchmark, live Plaid or Instacart evidence, checkout, deployed evidence, and target certification remain incomplete. Recorded CLI supervisor usage as of `2026-10-03T03:11:58.118465+00:00`: implement had 44 attempts, 20,609,897 input tokens, 490,165 output tokens, 187,375 reasoning tokens, and 18,457,096 ms process elapsed; repair had 79 attempts, 19,849,703 input tokens, 303,534 output tokens, 104,249 reasoning tokens, and 11,631,778 ms process elapsed; review had 59 attempts, 8,586,961 input tokens, 204,748 output tokens, 150,615 reasoning tokens, and 5,227,346 ms process elapsed. Input counts include cached tokens; cached tokens are not added again. Token sums are lower bounds where attempts have unknown counts: implement has four unknown attempts for input, output, and reasoning; repair has one for each; review has none. Process elapsed times overlap and are not wall-clock duration. Usage excludes coordinator and native junior tokens.

## 2026-10-02 — Evaluation component 23 local integration

Enforce fixture observation metadata (`b710c398074f14feb4744367d59d4978aee42b73`) is included as a locally reviewed integration component in snapshot `a9a9a4f51b34b05b10a00aa6e9399e2f15a3d8bb`.

## 2026-10-02 — Evaluation completion checkpoint

Snapshot `a9a9a4f51b34b05b10a00aa6e9399e2f15a3d8bb` was captured at `2026-10-03T03:43:02.320249+00:00`. Recorded gates passed: Ruff check (`All checks passed!`), Ruff format (`262 files already formatted`), mypy (`Success: no issues found in 130 source files`), and pytest (`6055 passed, 1 warning in 12.11s`). At source revision `b710c398074f14feb4744367d59d4978aee42b73`, the summary integration smoke recorded five current structured-reference outputs and four controlled-provider cases: nine observations across two separate quality scopes, zero live model calls, and verified completion hashes. The verification archive manifest records 36 approved gate/review pairs with 72 checked hashes. The complete batch/CLI and full benchmark remain incomplete; items 02, 04, and 08 await approval for an extra review round. Recorded evaluation-completion CLI supervisor usage as of `2026-10-03T03:43:02.320249+00:00` (188 attempts): implement had 46 attempts (5 no edits, 36 completed, 4 task_failed, 1 time_limit), 21,280,292 known input tokens, 503,841 known output tokens, 190,770 known reasoning tokens, and 19,528,838 ms process elapsed; repair had 81 attempts (79 completed, 1 task_failed, 1 no edits), 20,834,996 known input tokens, 330,497 known output tokens, 114,444 known reasoning tokens, and 12,243,308 ms process elapsed; review had 61 completed attempts, 8,931,014 known input tokens, 216,238 known output tokens, 159,546 known reasoning tokens, and 5,514,880 ms process elapsed. These usage totals are a snapshot before this documentation repair and final review. Input totals include cached tokens; cached-token subtotals are not added again. Known token sums are lower bounds where attempts have unknown counts: implement has five unknown attempts for input, cached, output, and reasoning; repair has one for each; review has none. Process elapsed times overlap and are not wall-clock duration. Usage excludes coordinator and native junior tokens.

## 2026-10-03 — Evaluation item 31 CI database-name correction

The correction source `811e41022fe4b7ec6738aa58db47f9124c20a29f` sets `fewia_eval` in all three URLs, the service database, and the health check after the guard rejected `/fewia`. Sol wrote at high effort. Luna independently approved at high effort. The integrated corrected source `8dfdb50f324310f18ba2870b8807a5511af40096` passed local Ruff check, Ruff format, mypy, and pytest (`6055 passed, 1 warning`). The [publication record](phases/evaluation-publication.md) keeps these local results separate from the timestamped remote CI snapshot.

## 2026-10-03 — Evaluation draft publication and Graphify update

The [publication record](phases/evaluation-publication.md) lists all 41 draft pull requests and the exact 38-entry merge order. Graphify processed source `8dfdb50f324310f18ba2870b8807a5511af40096`: 75 files (70 code and five documents), 6,185 nodes, 17,813 edges, and 315 communities. Its HTML has 315 community nodes and 710 cross-community edges. The health report warns about 15 self-loop call edges; zero dangling or missing endpoints and zero collapsed endpoint pairs were observed. Some self-loops are recursive, and the remaining cases need source inspection. The graph outputs are ignored local files, not committed or published. The graph excludes this publication page. Native semantic-agent usage is unavailable, deterministic AST extraction uses no model calls, and the full benchmark remains incomplete.

## 2026-10-03 — Evaluation item 02 recovery publication

Approved source `05abadb17e8de4e5cb089d82bb524924de28e52a` is published as draft PR [#288](https://github.com/emanuelGitCodes/fewia/pull/288). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation item 04 recovery publication

Approved source `3b4c47fedb2c81ec0c4620db410307b0cc46eb8c` is published as draft PR [#289](https://github.com/emanuelGitCodes/fewia/pull/289). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation item 08b recovery publication

Approved source `62e77e243b9a67f685c7c89ef15754034fb6a4a4` is published as draft PR [#293](https://github.com/emanuelGitCodes/fewia/pull/293). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation item 11a recovery publication

Approved source `36556715fc0c0a37930c998097c965faf902b03e` is published as draft PR [#294](https://github.com/emanuelGitCodes/fewia/pull/294). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation item 07a recovery publication

Approved source `de7267be983fc122bb78b3461c4818254dd289d8` is published as draft PR [#295](https://github.com/emanuelGitCodes/fewia/pull/295). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation item 11 recovery publication

Approved source `2e8a6fdf58968536965071595cb707c0dd8caf6a` is published as draft PR [#296](https://github.com/emanuelGitCodes/fewia/pull/296). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation item 07 recovery publication

Approved source `b227f19ecd81f6a5b6d53f486c32fa5328060d4a` is published as draft PR [#297](https://github.com/emanuelGitCodes/fewia/pull/297). See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation recovery checkpoint and Graphify update

Main at `5e5cdc9c06bc1d25d921ecba4fd42f89b911a4bd` matches the published `9e8e55f` tree, including observed user merge PR #292. This recovery did not merge main. Integration source `e119a2d4a12c532e333bd43ac49c38ab52a1e49f` is pushed on `codex/evaluation-resume`; local gates passed. Graphify recorded 6,564 nodes, 19,238 edges, and 322 communities, with 18 self-loop edges and zero missing or dangling endpoints. The full benchmark remains unrun. See the [recovery checkpoint](phases/evaluation-recovery.md).

## 2026-10-03 — Evaluation repair loop

Nine follow-up findings from the reviews of #288 to #301 and #292 ship as pull requests [#302](https://github.com/emanuelGitCodes/fewia/pull/302) to [#310](https://github.com/emanuelGitCodes/fewia/pull/310). Each item passed the gates and an independent review on its head SHA. #310 is stacked on #304. The integrated tree of all nine passed 6,831 backend tests with a PostgreSQL database and 183 tooling tests. Writer and review usage for the loop: 4,749,492 input tokens, 85,975 output tokens, 3,013 seconds. No subagents ran. The ledger is `.claude/loop/evaluation-repairs.md`.

The repairs: refusal actions require one result per budget call; the capture leak scan visits the whole value; scenario injection rejects caller markers; the model turn scans history before the provider call; the no-tool guard test imports before patching; case messages reject credential patterns; the manifest hashes the baseline prompt; negative token counts have a failing test; the process cleanup test is deterministic.

## 2026-10-03 — Backlog build intake and ledger reconciliation

The user authorized branches, commits, and pull requests for the feature backlog.
The user set a stop at 8 percent total weekly Codex usage. Intake reported 1 percent.
The build starts from `be7470aac8212dc297ac8c651e643e272cf1aec2`.

Luna xhigh reconciled the two historical loop ledgers against their event logs.
The coordinator preserved the dropped state of tech-debt item 07.
This branch tracks copies of the primary checkout's ignored ledgers.
It does not change the primary checkout's private files.
The backlog now assigns gates to the coordinator or junior and permits fixture-only handoff work.

Focused nutrition and Spoonacular checks reported 24 passed with one warning.
Supervisor lease, pre-launch recovery, and database-skip checks reported 36 passed with one warning.
Import and line-length lint passed. Alembic lint passed.
An initial combined pytest command failed collection because `PYTHONPATH` lacked the repository root.
The corrected command passed. No live-provider or deployed result is claimed.

The [build checkpoint](phases/backlog-build-20261003.md) records scope and open work.
Independent review and publication remain pending for this checkpoint.

## 2026-10-03 — Backlog reviews and published branches

PR #314 publishes direct polling-hook tests at `fdb89cb2f14f68bcaffb5432132562b136592a8a`.
All frontend gates passed. The focused suite passed 12 tests.
A disposable mutation removed terminal polling stop; the new success test failed as expected.
Luna high returned `APPROVE`. GitHub checks passed.

PR #315 publishes ledger corrections at `23ca51afdb9110da19a3dd08316e3f2660055152`.
Sol low first found two incorrect historical states. The writer corrected them.
The second review returned `APPROVE`. GitHub checks passed.

PR #316 publishes automatic review fallback at `38657a757a528c670d3022f44f3674fd5864c83a`.
The tooling gates passed 243 tests, Ruff, formatting, and strict mypy.
The focused review suite passed 106 tests.
A disposable mutation disabled fallback; the missing-Codex regression failed as expected.
Luna high returned `APPROVE`. GitHub checks passed.

Luna medium reviewed historical nutrition commit `c9316dad200186d1c8421870e8cabbcd01c19232`.
The verdict was `REQUEST_CHANGES`: manual nutrition aliasing and chat request/nutrition mismatch.
The coordinator confirmed both patterns on the current baseline. Repairs run on a separate branch.
The historical review checkout needed the current reviewer role file because that commit predates it.

Completed reviews, gates, mutation evidence, and a partial CLI usage snapshot are preserved
under `wiki/artifacts/backlog-20261003/`. No PR was merged by this build.
At this checkpoint, weekly Codex usage reports 6 percent. The stop remains 8 percent.

## 2026-10-03 — Stop at the weekly usage limit

The account reached the user's 8 percent weekly limit. All model work stopped.
Shutdown preserved current work without further implementation or model review.
Eight work branches were committed and pushed. Seven pull requests preserve the work.

PR #317 remains a draft at `6c6d189ced6d390fdd119b812c0700eb7d29562b`.
Independent review approved it, but GitHub CI failed during action resolution:
`Unable to resolve action astral-sh/setup-uv@v10, unable to find version v10`.
The action-reference repair remains open.

The B5 helper remains at `db4226f5faffe118eb6081c18df6a20d12d9c72d` on its pushed branch.
Its gates report `RESULT FAIL`: strict mypy found redundant casts at lines 36 and 86;
the source counter reports 158/150. Ruff and formatting passed.
The PostgreSQL test run passed 6914 tests with one warning. The helper needs a clean split.
No code PR was opened for this oversized change. The report renderer remains unbuilt.

PR #320 preserves nutrition repairs at `24ba3d6` as a draft.
The focused suite passed 51 tests. Frontend lint, tests, and build passed.
Independent review of the repair remains pending.
PR #319 contains only the unfinished C4 recovery record; no handoff code changed.
PR #318 preserves this wiki evidence, stacked on PR #315.

The run's PostgreSQL container stopped. Disposable mutation and historical review
checkouts were removed. The existing FEWIA stack was not changed.
No Grafana or Graphify update occurred. No PR was merged and no AWS deployment ran.

## 2026-10-03 — Backlog PRs merged and the fallback follow-up

The coordinator evaluated #314 to #320 against `main`. All seven branches merged together passed 6,831 backend tests, 243 tooling tests, 423 frontend tests, lint, strict mypy, and the frontend build. #314, #320, #319, #315, and #318 merged in that order with merge commits. #317 merged after a repair pinned `astral-sh/setup-uv@v10.2.0`. #316 merged on `8eddcc7` after two repairs; its third review round found that a structured Codex error with both `code` and `message` is matched on `code` only. The owner merged as is. The follow-up is backlog item B6 in `docs/FEATURE_BACKLOG.md`. The coordinator ran an independent review on #320 (APPROVE) and mutation probes on #314, #316, and #320; every mutation was caught. Branch `codex/backlog-20261003-b5` holds an unpublished start on B5 at `db4226f`. Main is at `8bfd4b8`.

## 2026-10-03 — Decision 0018: retain legacy data for now

The user chose to retain existing stored Spoonacular totals and retired
health tables for now. Deletion needs a separate decision. Decision:
[0018 — Retain legacy data for now](decisions/0018-retain-legacy-data.md).

## 2026-10-03 — Correct provider-specific writer read permissions

Updated the [junior protocol](../docs/delegation/junior.md) to allow Codex
read-only shell access for reads and searches, forbid Grok shell commands, and
keep checks with the junior. The junior MUST check its final brief for
contradictory command prohibitions before launch. See the [C4 recovery
record](artifacts/backlog-20261003/c4-resume.md).

## 2026-10-03 — Align supervisor writer command rules

Updated the supervisor opening to match the provider-specific junior protocol.

## 2026-10-03 — B5 strict-value helper publication

PR [#322](https://github.com/emanuelGitCodes/fewia/pull/322) publishes
`98fde259ebc2281cf652d045eb26add13f07172e` with 28 code lines on
`codex/backlog-resume-b5-values`. The supplied backend record reports Ruff,
format, strict mypy, and 6,874 tests passed with one warning. Independent Luna
high review approved the helper. GitHub CI reported all 7 checks successful
at this snapshot. This result covers the helper only; B5 remains partial.

## 2026-10-03 — C4 fixture handoff guards

PR [#323](https://github.com/emanuelGitCodes/fewia/pull/323) publishes
`0246c9b1c249f719b1f10b4a9bf99db499a1f26b` with 10 code lines on
`codex/backlog-resume-c4`. The supplied frontend install, lint, test, and build
gates passed. Independent Luna high review approved the change. GitHub CI
reported all 7 checks successful at this snapshot. This is fixture-flow code
evidence, not live Instacart evidence.

## 2026-10-03 — B6 structured error matching

PR [#324](https://github.com/emanuelGitCodes/fewia/pull/324) publishes
`578df44aa0fa5107167dadec1e8f7773ce9e041f` with 12 code lines on
`codex/backlog-resume-b6`. The supplied tooling record reports 326 tests,
Ruff, formatting, and strict mypy passed. Independent Luna high review
approved the change. GitHub CI reported all 7 checks successful at this
snapshot.

## 2026-10-03 — B4 consent browser evidence

PR [#327](https://github.com/emanuelGitCodes/fewia/pull/327) publishes
`85493df8ace8ff246df0c15dfccb40e22aef1a62` with 119 code lines, stacked on
#323. The supplied frontend gates passed and independent Luna high review
approved the change. The first browser record failed consent-before-POST; the
repaired browser record passed 14 checks, including consent, keyboard focus,
mobile fit, and one explicit retry. These checks used an isolated local
PostgreSQL/Floci stack with fixture handoff responses. They do not establish
live provider, purchase, deployed, or model-quality results. See the
[verification plan](../docs/GROCERY_VERIFICATION_PLAN.md) and the
[backlog resume record](phases/backlog-resume-20261003.md).

## 2026-10-03 — C1 runtime publication

PR [#328](https://github.com/emanuelGitCodes/fewia/pull/328) publishes
`26fe9148da0c12bd5c55218b063fcc15d54ee7c4` with 92 source lines on
`codex/backlog-resume-runtime`. Backend Ruff, format, strict mypy, and 6,889
tests passed. The 18-fixture smoke passed with no model calls. An empty-check
mutation caused 3 failures. Independent Luna high review approved the change.
No GitHub CI result is recorded.

## 2026-10-03 — B3 tier S documentation pilot measured

Status: measured; publication pending (limited documentation pilot). The pilot covers two completed tier S documentation items: A4 retention and Writer protocol. Both used no native junior or reviewer subagent. Coordinator tokens are excluded. See the [pilot evidence](artifacts/backlog-resume-20261003/tier-s-pilot.json) and the [detailed ledger](../.claude/loop/delegation-efficiency.md#tier-s-documentation-pilot).

| Item | Attempts | Input tokens | Output tokens | Input + output | Reasoning tokens | Cached tokens | Process seconds | Native subagent tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A4 retention | 3 | 490204 | 7281 | 497485 | 3329 | 403328 | 184.185 | 0 |
| Writer protocol | 5 | 589078 | 10109 | 599187 | 5752 | 475520 | 264.479 | 0 |
| Total | 8 | 1079282 | 17390 | 1096672 | 9081 | 878848 | 448.664 | 0 |

A4 has two completed reviews. Writer protocol has three completed reviews and one completed repair. All selected attempts have known token and elapsed counts. Input includes cached tokens. Cached and reasoning counts are subtotals; do not add them to input or output again. Process elapsed times overlap, so the total is not wall time.

The Phase 1 baseline is about 1,820,000 native subagent tokens for about 270 code lines plus tests and docs. Baseline CLI writer and review counts are unknown. This pilot has zero native subagent tokens and 1,079,282 measured CLI input tokens. The cohorts differ. This result measures tier S routing and usage. It does not support a percentage reduction in total cost, a causal efficiency gain, or a like-for-like speed comparison.

## 2026-10-03 — B5 report renderer publication

B5 is published in [#322](https://github.com/emanuelGitCodes/fewia/pull/322),
[#332](https://github.com/emanuelGitCodes/fewia/pull/332),
[#333](https://github.com/emanuelGitCodes/fewia/pull/333),
[#334](https://github.com/emanuelGitCodes/fewia/pull/334),
[#335](https://github.com/emanuelGitCodes/fewia/pull/335), and
[#336](https://github.com/emanuelGitCodes/fewia/pull/336).
The [benchmark record](phases/benchmark-20261003.md) links the completed reports.
It keeps condition denominators, failures, unknowns, latency, and cost separate.
This entry supersedes the earlier partial B5 publication status.
It records no new merge or CI result.

## 2026-10-03 — C1 runtime and dispatch publication

C1 runtime is published in [#328](https://github.com/emanuelGitCodes/fewia/pull/328).
Dispatch is published in [#329](https://github.com/emanuelGitCodes/fewia/pull/329).
The completed benchmark records integrated slot execution at source
`4b877d470258561cedd3375e38efc02362ce5f22`.
The [benchmark phase](phases/benchmark-20261003.md) separates fixture, local PostgreSQL, and real Bedrock evidence.
This entry records no new merge or CI result.

## 2026-10-03 — C2 batch publication

C2 is published in [#338](https://github.com/emanuelGitCodes/fewia/pull/338).
The [fixture integrity record](../eval/results/artifacts/benchmark-20261003/fixture-integrity.json)
and [live integrity record](../eval/results/artifacts/benchmark-20261003/live-integrity.json)
each record 138 slots at source `4b877d470258561cedd3375e38efc02362ce5f22`.
Both report verified hashes and journals matching the reports.
Execution completion does not certify model quality.

## 2026-10-03 — C3 CLI and SIGINT evidence

C3 is published in [#339](https://github.com/emanuelGitCodes/fewia/pull/339)
and [#341](https://github.com/emanuelGitCodes/fewia/pull/341).
The [evaluation guide](../docs/EVALUATION.md) documents the flags and a new exclusive output directory.
Without `--live-bedrock`, the public CLI exits 1 before provider calls.
The archived fixture driver injects a truthfully labeled fake provider.
The [SIGINT summary](../eval/results/artifacts/benchmark-20261003/sigint-summary.json)
records exit 130 with 49 preserved journal records and no completion marker.
Exit 0 means artifact completion only.

## 2026-10-03 — D1 fixture and live benchmark evidence complete

The [readout](../eval/results/artifacts/benchmark-20261003/benchmark-readout.json)
records source `4b877d470258561cedd3375e38efc02362ce5f22` and one live Nova 2 Lite batch.
It contains 138 records, including 66 real model observations.
All 33 tool-enabled executions completed, but task quality passed 17/33, or 51.5%.
The 90% task target FAILS. Bounded factual claims pass 98/100, or 98%; the 95% target PASSES.
That denominator includes two unknown claims and excludes ten supported refusals.
Six accepted live final plans have zero tested violations.
Synthetic-sentinel capture covers 48 turns across 33 slots with explicit false leak flags.
Purchase attempts remain UNMEASURED. A04 refusal/action checks do not prove zero attempts.
Release is NOT certified. No Plaid Sandbox, live Instacart, or deployed proof is supplied.

## 2026-10-03 — D2 benchmark documentation record

Updated the evaluation guide, backlog, completion checkpoint, index, and
[benchmark phase](phases/benchmark-20261003.md) with artifact citations and evidence limits.
The approved documentation baseline [#331](https://github.com/emanuelGitCodes/fewia/pull/331)
was imported for record continuity. B3's limited documentation pilot is published there.
This documentation PR depends on #331 and #341. This entry does not claim either is merged.
D3's evidence pack remains pending. D4 remains paused.
D5 source adapters remain in progress in [#340](https://github.com/emanuelGitCodes/fewia/pull/340)
and [#342](https://github.com/emanuelGitCodes/fewia/pull/342), without deployment evidence.
The writer ran no checks. Coordinator verification and independent review remain pending.
