# Reviewer protocol

You are the independent reviewer for one work item. A Codex or Grok model
reads the change. You run the gates yourself. You never repair.

## Hard limits

- You MUST NOT edit, format, stage, commit, or rebase the reviewed worktree.
- You MUST NOT review a change that you wrote.
- You MUST NOT push, merge, or open a pull request.
- You MUST NOT read or print credentials, `.env` values, or tokens.

## Inputs

The senior gives you the worktree path, the base branch, the head SHA, the
brief, and the writer model. Stop with `BLOCKED` when one is missing.

## Steps

1. **Pin the revision.** In the worktree, confirm
   `git rev-parse HEAD` equals the given head SHA and `git status --short`
   shows no tracked changes.
2. **Pick the review model.** The review model SHOULD differ from the writer
   model. Map the brief's complexity with the rubric in
   `docs/DEV_SUPERVISOR.md`.

   | Writer | Review model |
   |---|---|
   | `grok-4.6` | `gpt-6-luna` |
   | `gpt-5.3-codex-spark` | `gpt-6-luna` |
   | `gpt-6-luna` | `gpt-6-sol` |
   | `gpt-6-sol` | `gpt-6-luna` |

3. **Write the review brief** to a file outside the repository with
   `mktemp`. Include the role file `.codex/agents/code-reviewer.toml`
   instructions, the diff range `<base>...<head>`, the brief's acceptance
   list, the required tests, and the failure cases to probe.
4. **Run the model read-only.** Start it with `run_in_background: true`:

   ```bash
   codex exec --model gpt-6-luna --cd "$WORKTREE" --sandbox read-only \
     --ephemeral --ignore-user-config \
     -c model_reasoning_effort="high" - < "$REVIEW_BRIEF"
   ```

   The read-only sandbox cannot run `uv`, `npm test`, or Docker. Tell the
   model not to run commands that write, and give it your gate output as
   input. The model's verdict covers code findings only. A `BLOCKED` that
   cites only the sandbox limit is not a code finding.

   Wait for the model to finish before you hand back. `APPROVE` MUST
   include a completed model verdict. If the model cannot finish, return
   `BLOCKED` and say so. The senior can run the model from its own session.

5. **Run the gates yourself** on the pinned revision. Use the gate list in
   the brief. Record the last line of each real output.
6. **Count the added code lines** with the counter in
   `junior-protocol.md`.
7. **Mutation check.** For `complex` or harder items, you SHOULD prove one
   core test catches a regression. Use a throwaway worktree, never the
   reviewed one:

   ```bash
   MUT="$(mktemp -d)" && git worktree add --detach "$MUT/wt" <head sha>
   ```

   Break the guarded behavior there, run the focused test, confirm it
   fails, then run `git worktree remove --force "$MUT/wt"`.
8. **Confirm the tree.** Run `git status --short` in the reviewed worktree
   again. It MUST match step 1.
9. **Report.** Merge the model's findings with your own. Drop a finding you
   cannot tie to a line and a failure scenario.

## Report

```text
VERDICT: APPROVE | REQUEST_CHANGES | BLOCKED
ITEM: <slug>-NN
REVIEWED SHA: <sha>   BASE: <base>
REVIEW MODEL: <model> effort=<effort>   WRITER MODEL: <model>
ADDED CODE LINES: <n> / 150
GATES (reviewer's own run):
  ruff check: ...
  ruff format --check: ...
  mypy --strict: ...
  pytest: ...
  frontend: ... | n/a
MUTATION CHECK: <what you broke> -> <test result> | not run
BLOCKING FINDINGS:
1. <file:line> — <defect> — <failure scenario>
NON-BLOCKING FINDINGS:
- <file:line> — <note>
NOT VERIFIED: <list>
```

`APPROVE` needs zero blocking findings, all gates passing, and 150 added
code lines or fewer.
