# Phase 2 — Synthetic data

- **Completed**: 2026-09-01
- **Plan**: [project-plan.md](../../project-plan.md), Phase 2
- **Source**: `docs/CAP6938_MVP_PROJECT_PLAN.md` §5
- **Writer**: Codex. **Verifier**: Claude. See
  [decisions/0006-codex-writes-claude-verifies.md](../decisions/0006-codex-writes-claude-verifies.md).

## What shipped

Three stacked branches, in merge order:

1. `feat/phase2-records` (`cbdbfd6`) — `backend/app/synth/records.py`
   with `DATA_VERSION`, `DEFAULT_END_DATE`, `Profile`, `PROFILES`, and
   the frozen row dataclasses `FinanceRow`, `EnvironmentRow`,
   `HealthRow`, and `Dataset`. 99 code lines.
2. `feat/phase2-generator` (`74a3163`) — `backend/app/synth/generator.py`
   with `generate(*, seed, days, end_date)`. The generator imports no
   SQLAlchemy. 129 code lines.
3. `feat/phase2-cli` (`17ea707`) — `backend/app/synth/loader.py` and
   `backend/app/synth/__main__.py`. 120 code lines.

Pull requests #10, #11, and #12 carried the three branches. `main`
holds all three at commit `4e47640`. The three branches are deleted on
the remote.

`PROFILES` holds the four profiles of §5. The four cross the two
levels, so the data does not encode the single rule "more money means
more steps". The generator adds weekday effects, per-profile
environments, noise, missing health rows, null values in the nullable
health columns, and controlled outliers. Every value passes through a
helper that holds it inside its column constraint.

`load(session, dataset)` writes the users and the three daily tables
and replaces rows by primary key, so a second run neither fails nor
duplicates. Every `source` column carries `synthetic-v1`.

## Verification

Run on 2026-09-01 against a clean PostgreSQL 16 container. Port 5432
held another worktree's database, so the run used port 5433.

- `uv run ruff check app tests`, `uv run ruff format --check app tests`,
  `uv run mypy --strict app`, and `uv run pytest` all passed. 24 tests
  pass.
- Two runs of `python -m app.synth --seed 42 --days 90` wrote the same
  rows. The `daily_health` checksum was
  `341|90d7c046d8506a63248cd9c510b916ec` both times.
- Row counts matched the specification: 4 users, 360 finance rows, 360
  environment rows, and 341 health rows. Health missingness is 5.3
  percent.
- `select count(distinct source) from daily_finance` returned 1, and
  the value was `synthetic-v1`.
- GitHub Actions passed on all three pull requests and again on `main`
  at `4e47640`.

The verifier mutated the generator and the loader and reran the tests.
Every mutation now fails in the matching test: an unseeded random
chain, a deleted weekday effect, a profile level that stops driving
steps or spending, removed step or spending outliers, no missing health
rows, non-null health columns, a missing user merge, a removed
`setval`, a wrong display name, and a moving default end date.

## Defects that the checks did not catch

Ruff, `mypy --strict`, and the author's own tests passed on every round.
Independent mutation testing found the defects.

- Round 1: the test suite missed five of seven injected regressions. A
  test named for the weekday effect passed when the effect was deleted,
  because it compared two float means for inequality and noise alone
  satisfied it.
- The loader wrote users 1 to 4 into an `Identity()` column and left
  the sequence behind. The next ordinary insert failed with `duplicate
  key value violates unique constraint "users_pkey"`. Phase 3 and Phase
  5 add users, so the failure would have appeared far from its cause.
  The loader now advances the sequence with `setval`.
- `--end-date` defaulted to `date.today()`, so the documented command
  was not reproducible across days. Two runs one day apart left 364
  rows, not 360. The default is now the fixed constant
  `DEFAULT_END_DATE`, and a test pins its value.

## The stack incident

Pull request #10 merged while `feat/phase2-records` still existed.
GitHub did not retarget #11, which still pointed at
`feat/phase2-records`. Merging #11 unchanged would have repeated the
Phase 1 failure. The verifier retargeted #11 to `main` by hand first.

Merging #11 with `gh pr merge --delete-branch` then deleted
`feat/phase2-generator`, which was the base of #12. GitHub closed #12,
and a closed pull request accepts neither a reopen nor a new base while
its base branch is missing. Recovery pushed `74a3163` back to
`feat/phase2-generator`, reopened #12, retargeted it to `main`, and
merged it.

Two rules follow:

- GitHub retargets a child pull request only when the parent's head
  branch is deleted. An executor MUST check the base of every child
  before it merges the child.
- An executor MUST NOT delete a branch that a later pull request still
  names as its base. Retarget the child first, then merge, then delete.

## Open items

- `wiki/log.md` carries a Phase 2 entry dated 2026-08-31 that pull
  request #12 added before the stack merged. The entry stays, because
  the log is append-only.
- The loader issues one PostgreSQL statement, `setval` on
  `pg_get_serial_sequence`. The loader is no longer portable to another
  database.
- `backend/tests/test_synth_loader.py` skips, and does not fail, when
  no database answers.
- Phase 2 did not run `docker compose up -d postgres`, because another
  worktree held port 5432. Compose itself is unchanged since Phase 1.
