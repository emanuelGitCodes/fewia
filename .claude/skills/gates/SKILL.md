---
name: gates
description: Run the FEWIA gates with the dedicated PostgreSQL the database tests need. Starts a throwaway postgres:16 named fewia_eval, migrates it, exports the three database variables, runs dev_supervisor.gates, and removes the container. Use when the user asks to run the gates, the checks, or the tests on a branch.
argument-hint: "[--base <ref>] [--reuse]"
---

# Gates

The runtime database tests assert that every database on the server
matches `fewia_eval`. The shared Compose server holds `fewia` and
`fewia_test` too, so it fails that guard. Without the variables about
220 tests skip and the gate record is incomplete. This skill gives the
gates their own server.

## Run

From the checkout under test, with Docker running:

```bash
.claude/skills/gates/scripts/gates-with-db.sh --base main
```

The script:

1. Starts `postgres:16` on a free local port with user `fewia`,
   password `fewia`, database `fewia_eval`.
2. Runs `uv run alembic upgrade head` in `backend/`.
3. Exports `DATABASE_URL`, `FEWIA_JOB_TEST_DATABASE_URL`, and
   `FEWIA_EVALUATION_DATABASE_URL`, one `export` per line.
4. Runs `dev_supervisor.gates` with the flags you pass through.
5. Removes the container, also on failure.

Run it with the Bash tool and `run_in_background: true`. Read the last
lines: `LINES n/1000` and `RESULT PASS` or `RESULT FAIL`.

## Rules

- The gates record is keyed by the head SHA. Commit before you run.
- Pass `--reuse` only when the tree is clean and the record matches HEAD.
- Expect one skip or none in the backend tests. A run with hundreds of
  skips means the variables did not reach the tests.
