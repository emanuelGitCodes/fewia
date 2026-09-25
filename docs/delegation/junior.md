# Junior protocol

You own one work item. The coordinator gives you a brief. A Grok or Codex
writer edits the files through `dev_supervisor`. You drive the writer,
check its work, and report. The rules in [../DELEGATION.md](../DELEGATION.md)
apply.

## Limits

- You MUST NOT edit application, test, infrastructure, or documentation
  files yourself. Only the writer edits them.
- You MAY write the assignment file outside the repository, run commands,
  and commit on your work branch.
- You MUST NOT draft code for the writer. Describe behavior, contracts, and
  failures in the assignment. Do not paste code for the writer to copy.
- You MUST NOT push, merge, or open a pull request.
- You MUST NOT perform an external mutation. Return a proposed action to
  the coordinator.
- You MUST NOT read or print credentials, `.env` values, or tokens.

## Steps

1. **Read.** Read your role file in `.codex/agents/`, this protocol, the
   brief, and the files the brief names. Read nothing else unless the
   brief is missing context. Report missing context.
2. **Branch.** Work in your own worktree. Create the work branch from the
   base branch that the brief names.
3. **Assignment.** Write the brief to a file outside the repository. Add
   these lines: "Do not run commands. Edit files only. The junior runs
   every command." and "Commit nothing."
4. **Write.** Start the writer in the background with a timeout. `--task`
   takes a file path.

   ```bash
   uv run --project backend python -m dev_supervisor \
     --task "$ASSIGNMENT" --role <role> --cwd "$PWD" \
     --complexity <class> --write-file <owned path> \
     --work-item <item> --phase implement
   ```

5. **Inspect.** Run `git status --short` and `git diff`. Every changed file
   MUST be an owned file. A `task_failed` outcome needs this inspection
   before you decide anything.
6. **Install and format.** When the writer declares a dependency, you run
   `npm install` or `uv lock`. Do not edit a manifest or a lockfile. You MAY
   run `ruff format` or the frontend formatter on owned files instead of a
   writer round for whitespace.
7. **Gates.** Run the gates once:

   ```bash
   uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base <base>
   ```

8. **Repair.** When a gate fails or the diff misses the brief, write a
   repair assignment with the failure lines. Run the writer again with
   `--phase repair`. You MAY do this twice. Then stop and report.
9. **Commit.** Commit the owned files on the work branch. Use a short
   imperative subject and the attribution line that the brief gives.
10. **Clean up.** Stop every background process and watch that you
    started.
11. **Report.** Send the report below once.

## Report

Keep the report to 40 lines. Name the SHA. Do not paste diffs or files.

```text
STATUS: done | blocked | failed
ITEM: <item>
BRANCH: <work branch> @ <short sha>   BASE: <base>
WORKTREE: <absolute path>
WRITER: <model> effort=<effort> outcome=<outcome> runs=<n>
FILES: <paths>
GATES: <the RESULT line and each FAIL line from dev_supervisor.gates>
LINES: <n>/150
TESTS ADDED: <names>
DEVIATIONS: none | <one line each>
QUESTIONS: none | <one line each>
NOT VERIFIED: <one line each>
```

## Repair messages

The coordinator sends findings as a repair message. Treat each blocking
finding as a new repair assignment. Run steps 3 to 11 again. When you think
a finding is wrong, say so in the report instead of in code.
