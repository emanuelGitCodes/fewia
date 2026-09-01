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
