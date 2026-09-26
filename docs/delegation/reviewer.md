# Reviewer agent protocol

Tier L work items get a reviewer agent in addition to the review command.
The review command gives the independent code verdict. You add what a
read-only model cannot do: probes, mutation checks, and runtime checks.
The rules in [../DELEGATION.md](../DELEGATION.md) apply.

## Limits

- You MUST NOT edit, stage, commit, or rebase the reviewed worktree.
- You MUST NOT review a change that you wrote.
- You MUST NOT push, merge, or open a pull request.
- You MUST NOT read or print credentials, `.env` values, or tokens.

## Steps

1. **Pin.** Confirm `git rev-parse HEAD` equals the head SHA in your
   assignment. Confirm `git status --short` is empty.
2. **Read the gates record.** Read `.fewia-supervisor-gates/<sha>.json` in
   the worktree root. Do not rerun the full gates.
3. **Probe.** Run the failure cases that the assignment lists. Use a
   throwaway worktree for any edit:

   ```bash
   MUT="$(mktemp -d)" && git worktree add --detach "$MUT/wt" <head sha>
   ```

   Break the guarded behavior there. Run only the focused test. Confirm
   that it fails. Remove the throwaway worktree afterwards.
4. **Review command.** When the coordinator has not run it, run
   `dev_supervisor.review` once and wait for its verdict.
5. **Clean up.** Stop every background process and container that you
   started. Confirm the reviewed tree is unchanged.
6. **Report.** Send the report below once.

## Report

Keep the report to 40 lines.

```text
VERDICT: APPROVE | REQUEST_CHANGES | BLOCKED
ITEM: <item>   REVIEWED SHA: <sha>   BASE: <base>
REVIEW MODEL: <model> effort=<effort> verdict=<verdict>
PROBES: <probe> -> <result>, one line each
BLOCKING: <file:line> — <defect> — <failure scenario>, one line each
NON-BLOCKING: <file:line> — <note>, one line each
NOT VERIFIED: <one line each>
```

`APPROVE` needs a completed review model run with no blocking finding, and
probes that all behave as expected.
