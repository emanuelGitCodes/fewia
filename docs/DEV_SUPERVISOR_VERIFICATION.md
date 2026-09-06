# Development supervisor verification

Local implementation date: 2026-09-06. Base: `1dec7d4`.
This record covers the isolated worktree, not activation in the saved checkout.

## Local stack

Merge in this order after independent review and user approval:

| Branch | Parent | Added source lines |
|---|---|---:|
| `codex/dev-supervisor-core` | `1dec7d4` | 109 |
| `codex/dev-supervisor-events` | `codex/dev-supervisor-core` | 94 |
| `codex/dev-supervisor-process` | `codex/dev-supervisor-events` | 117 |
| `codex/dev-supervisor-workflow` | `codex/dev-supervisor-process` | 146 |

Tests and Markdown do not count. No PRs were published. Each slice includes
its relevant tests. The final branch contains the integrated command.
Independent temporary archives of the four branch tips passed 4, 14, 20, and
24 supervisor tests, respectively. Each archive used only its committed files.

## Commands and observed output

The local sandbox denied access to the default uv cache. Checks used
`UV_CACHE_DIR=/tmp/fewia-supervisor-uv`; this does not change global config.
From `backend/`:

```text
uv run ruff check app tests
All checks passed!

uv run ruff format --check app tests
53 files already formatted

uv run mypy --strict app
Success: no issues found in 30 source files

uv run pytest
247 passed, 3 skipped, 1 warning
```

The skipped tests require PostgreSQL integration configuration. The warning is
Starlette's deprecation notice for using httpx with TestClient.

From the repository root:

```text
PYTHONPATH=. uv run --project backend pytest -q tests/supervisor
24 passed

uv run --project backend ruff check dev_supervisor tests/supervisor
All checks passed!

uv run --project backend ruff format --check dev_supervisor tests/supervisor
11 files already formatted

uv run --project backend mypy --strict dev_supervisor
Success: no issues found in 6 source files
```

The first supervisor pytest invocation failed to import `dev_supervisor`.
Adding the repository root through `PYTHONPATH=.` fixed collection. An early
ruff check found two import-order defects; they were repaired and rechecked.

Tests cover model overrides, model-only exhaustion, finite fallback, checkpoint
continuity, unknown errors, tool activity, permission stops, silence, confirmed
stalls, worktree locking, orphan detection, and child cleanup. A real subprocess
fixture exits with a structured quota error; its successor preserves its edit.

## Live compatibility

- Grok accepted `grok-4.6` and `medium`, and returned `COMPATIBLE` without tools.
  The CLI reported about USD 0.0059 for that call.
- Grok read an innocuous fixture in `/tmp/fewia-grok-compat` and returned `READ`.
  Native `tool_call` and `tool_call_update` events informed the parser and tests.
  The CLI reported about USD 0.0044 for that call.
- Spark returned `COMPATIBLE` with the supervisor's model/default-effort flags,
  user config disabled, and a read-only sandbox. No tools were requested.
- Luna's CLI model invocation is simulated here; no live Luna call was made.
- Initial Grok and Codex calls hit sandbox session-storage restrictions. The
  authorized compatibility checks then ran with normal CLI permissions.
  No bypass flags were used. SQLite and plugin/state warnings were not repaired.

Automatic approval review rejected a proposed Grok read of private `AGENTS.md`.
That probe did not run. The later synthetic fixture sent no project file.
Live quota exhaustion, every permission-event schema, deliberate daemon escape,
and production task completion were not established by these calls.

## Independent review and remaining limits

The read-only Claude review command failed before review:

```text
Failed to authenticate. API Error: 401 OAuth access token has expired.
Re-authenticate to continue.
```

This is the earlier review attempt. The user subsequently removed Claude Code
from the active workflow. Authentication remains unchanged. The current review
uses a separate Codex agent; see the follow-up evidence below.

No graph exists in this isolated worktree. Worker instructions provide targeted
context and on-demand graph access; they do not claim automatic graph knowledge.
Native role pins remain unchanged. No application worker, new product feature,
Bedrock change, global configuration edit, push, or merge was performed.
Process-group cleanup covers normal descendants; detached daemons violate the
worker contract and require coordinator inspection. Unknown provider formats
stop instead of guessing a retry class. CLI-owned sessions follow CLI storage
policy; the supervisor itself discards raw streams.

## 2026-09-06 — Codex/Grok review and runtime repair

The user removed Claude Code from active development. Decision 0009 and the
current role policies require a separate Codex or Grok reviewer. Historical
records remain intact. No Claude authentication, installation, account, or
subscription change was made.

Two local slices follow `codex/dev-supervisor-workflow`:

| Branch | Parent | Added source lines |
|---|---|---:|
| `codex/dev-supervisor-review-policy` | `codex/dev-supervisor-workflow` | 52 |
| `codex/dev-supervisor-reviewed-runtime` | `codex/dev-supervisor-review-policy` | 106 |

The policy slice includes the permission library and its tests. Its committed
archive passed 26 supervisor tests. The runtime slice integrates the command
and lifecycle repairs. Its committed archive passed 35 supervisor tests.
The original four slices remain in the merge order
listed above. No branch was pushed or merged.

### Independent review

A separate Codex agent, `/root/supervisor_review`, received a bounded, read-only
assignment. It reproduced and returned these findings to the Grok writer:

- A selector setup exception left a live writer and permitted another lease.
- A completed question remained a permission wait.
- Final resolved paths could introduce permission-rule metacharacters.
- Signal or selector cleanup errors could prevent process termination.

The reviewer also found stale Luna-only routing, obsolete ownership examples,
and incorrect assumptions about persistent CLI context. These were corrected.

The final reviewer reported no remaining actionable findings in its assigned
scope. It independently passed 35 tests. Six temporary-copy mutations failed
the relevant regressions. The previous thread and selector-close reproductions
left no live writer after repair. Final exception-handler narrowing was reviewed
again; the reviewer passed 35 tests in 2.30 seconds. The reviewer made no edits.

### Real writer execution

Grok 4.6 medium remained the writer. Initial headless writes cancelled at the
permission boundary. `acceptEdits` alone did not authorize the checkpoint write,
even after the checkpoint moved into the worktree. No provider fallback occurred.

A minimal probe with `--allow 'Write(/tmp/fewia-grok-compat/probe.txt)'` wrote
`SAFE` and completed. The CLI reported USD 0.00412012. Lowercase `write` was
rejected before model execution. Exact Write/Edit rules then allowed the scoped
project repair. A subsequent command permission prompt stopped that run after
source edits; the coordinator ran its checks.

The permanent `--write-file` interface completed the final focused repair and
lint repair with Grok. It authorized only named files and private progress.
Command checks remained enabled. No blanket approval, global permission change,
model override, or fallback from a permission cancellation was used. Checkpoints
are private and ignored inside the worktree. Grok-owned session metadata provided
the cancellation diagnosis; raw session contents were not added to the repository.

The installed CLI can surface headless permission cancellation as `task_failed`.
That outcome stops the sequence; it never triggers provider fallback. Local
session metadata may be needed to distinguish its cancellation cause.

### Final coordinator checks

With `UV_CACHE_DIR=/tmp/fewia-supervisor-uv`:

```text
PYTHONPATH=. uv run --project backend ruff check dev_supervisor tests/supervisor
All checks passed!

uv run --project backend ruff format --check dev_supervisor tests/supervisor
11 files already formatted

uv run --project backend mypy --strict dev_supervisor
Success: no issues found in 6 source files

PYTHONPATH=. uv run --project backend pytest -q tests/supervisor
35 passed
```

Backend gates again reported `All checks passed!`, `53 files already formatted`,
`Success: no issues found in 30 source files`, and `247 passed, 3 skipped, 1 warning`.
The skips and warning are the same PostgreSQL configuration and Starlette limits
reported above. All 14 role TOML files parsed. Early repair checks found PIE810,
one formatting defect, and two BLE001 exceptions; all were fixed and rechecked.

### Activation boundary

The supervisor executed real scoped repairs from this local worktree. The saved
checkout still needs the six-branch stack integrated through the user's normal
review and merge process. Existing native task role lists do not hot-reload.
Use the supervisor command from an integrated checkout with a bounded assignment,
explicit owned files, and any user model constraints. No application worker or
new grocery feature was launched. Bedrock application routing remains unchanged.
