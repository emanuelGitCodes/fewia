# C4 fixture handoff recovery

- Date: 2026-10-03
- Base: `be7470aac8212dc297ac8c651e643e272cf1aec2`
- Branch: `codex/backlog-20261003-c4`
- State: incomplete; no application code or tests changed.

## Observed source

`handoffTypes.parseHandoffView` validates HTTPS URLs against exact Instacart hosts.
`handoffApi.retryHandoff` calls the retry route with `expected_attempt`.
`HandoffControls` already shows a retry button for uncertain requests.

`App` renders controls when the feature flag is true or a previous handoff exists.
A false flag can therefore leave a previous handoff visible.
`HandoffControls` renders a succeeded view's URL without a final validation check.

## Remaining acceptance

- A false Instacart configuration hides all handoff controls, including stale state.
- A valid fixture URL renders only after validation.
- A malformed direct component input never produces a navigation link.
- An uncertain fixture write exposes explicit retry, with one route call per click.
- The default feature flag remains false. Live Instacart stays parked.
- The coordinator runs frontend gates, a mutation probe, and independent review.
- Browser verification remains open.

## Failed writer attempts

Two Sol high runs returned `no_edits`. A third run was interrupted before edits.
The brief retained a blanket command prohibition from the junior template.
Codex needs read-only shell commands to inspect files. `AGENTS.md` permits them.
No further writer was launched when the account reached 7 percent weekly usage.

The next brief MUST permit targeted read-only shell commands for Codex.
It MUST forbid tests, package managers, git, and file-writing shell commands.
The writer MUST edit only assigned files with `apply_patch`.

This record preserves the branch. It does not complete C4.
