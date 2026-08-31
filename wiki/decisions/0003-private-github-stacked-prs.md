# 0003 — Private GitHub repo, stacked pull requests

- **Date**: 2026-08-31
- **Status**: accepted

## Decision

The project lives in the private repository
`emanuelGitCodes/fewia` on GitHub. Every work item ships as a pull
request that adds 150 code lines maximum. A larger change ships as a
stack with the merge order stated in each PR body.

## Options considered

1. Private GitHub repo — chosen.
2. Public GitHub repo.
3. Local git only.
4. No git.

## Reason

The project handles financial and health concepts, so private is the
safe default. The user's global standard caps PR size at 150 added code
lines; small PRs get deep reviews.

## Consequences

- Agents deliver branches and PRs. Agents MUST NOT merge or push to
  `main`; the user merges.
- Tests, docs, lockfiles, and generated files do not count toward the
  cap.

Related: [phase 0](../phases/phase-0.md).
