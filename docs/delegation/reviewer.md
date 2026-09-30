# Tier L review protocol

Tier L work items get probes in addition to the review command. The review
model gives the independent verdict. It is read-only, so it cannot run
probes, mutation checks, or runtime checks. The coordinator runs them and
gives the results to the review model. The rules in
[../DELEGATION.md](../DELEGATION.md) apply.

## Limits

- The coordinator MUST NOT edit, stage, commit, or rebase the reviewed
  worktree.
- A mutation is a throwaway edit in a throwaway worktree. It MUST NOT reach
  a branch.
- The coordinator MUST NOT read or print credentials, `.env` values, or
  tokens.
- The coordinator MUST NOT give the verdict. The review model gives it.

## Steps

1. **Pin.** Confirm `git rev-parse HEAD` equals the head SHA. Confirm
   `git status --short` is empty.
2. **Gates.** Run `dev_supervisor.gates` on the head. Do not rerun them.
3. **Probe.** Run each failure case that the brief lists. Use a throwaway
   worktree for any mutation:

   ```bash
   MUT="$(mktemp -d)" && git worktree add --detach "$MUT/wt" <head sha>
   ```

   Break the guarded behavior there. Run only the focused test. Confirm
   that it fails. Remove the throwaway worktree afterwards.
4. **Record.** Write one file that holds the gates record from
   `.fewia-supervisor-gates/<sha>.json` and one line per probe:
   `PROBE: <probe> -> <expected> -> <result>`.
5. **Review command.** Run `dev_supervisor.review` on the head with
   `--complexity complex` or harder and `--gates-file <record>`. The review
   model then reads the gates and the probe results.
6. **Clean up.** Stop every background process and container that you
   started. Confirm the reviewed tree is unchanged.

`APPROVE` needs a completed review model run with no blocking finding, and
probes that all behave as expected. A probe that does not behave as
expected is a blocking finding. Send it to the writer in the repair brief.
