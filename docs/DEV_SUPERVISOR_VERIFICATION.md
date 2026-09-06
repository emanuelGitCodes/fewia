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

Claude verification remains pending. Authentication was not modified.
The coordinator can rerun review after authentication is restored.

No graph exists in this isolated worktree. Worker instructions provide targeted
context and on-demand graph access; they do not claim automatic graph knowledge.
Native role pins remain unchanged. No application worker, new product feature,
Bedrock change, global configuration edit, push, or merge was performed.
Process-group cleanup covers normal descendants; detached daemons violate the
worker contract and require coordinator inspection. Unknown provider formats
stop instead of guessing a retry class. CLI-owned sessions follow CLI storage
policy; the supervisor itself discards raw streams.
