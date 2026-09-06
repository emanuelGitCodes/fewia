# Development writer supervisor

Run from the repository root with Python 3.12:

```bash
uv run --project backend python -m dev_supervisor \
  --task /private/tmp/assignment.txt --role backend-dev --cwd "$PWD"
```

The assignment MUST name owned files, interfaces, acceptance checks, and scope.
Use an isolated branch and worktree. Native workers MUST NOT write there while
the supervisor runs. Review the assignment and checkpoint for secrets.

## Model selection

| Order | CLI | Model | Reasoning effort |
|---|---|---|---|
| 1 | `~/.grok/bin/grok` | `grok-4.6` | `medium` |
| 2 | `codex exec` | `gpt-5.3-codex-spark` | CLI model default |
| 3 | `codex exec` | `gpt-5.6-luna` | `xhigh` |

Spark omits reasoning effort. Codex commands ignore user config to avoid
inheriting another model's effort. Authentication remains with the CLI.
The supervisor does not edit global configuration.

An explicit model request MUST become `--model MODEL_ID`. “Use GPT 5.6 Sol”
becomes `--model gpt-5.6-sol`. It runs first. Eligible failures use the remaining
default sequence without duplicates. Each selected model and outcome is printed.
“Only use Sol” MUST include `--only --model gpt-5.6-sol`. No substitute runs.
Unknown models stop before execution. Extend the map with `--registry FILE`:

```toml
["gpt-5.6-sol"]
provider = "codex"
effort = "high"
```

A new provider needs a command adapter and tested event parsing. A registry
cannot inject shell commands. CLI arguments use argument lists.
Native `.codex/agents/*.toml` pins remain available for explicit native runs.
They do not implement fallback. The supervisor passes the selected role's
`developer_instructions` to the CLI. Bedrock application routing is separate.

## Stops and fallback

Each model receives at most one attempt. Defaults allow three attempts; an
additional starting model allows four. There are no same-provider retries.
Exhaustion returns `all_providers_exhausted`.

Missing executables and recognized structured provider error codes can trigger
fallback. Quota, rate limits, and unavailability have separate outcomes.
Unknown errors, failed tasks, permissions, cleanup failures, and time limits
stop. A failed test in tool output is not a provider error. Raw output text
never triggers fallback.

Silence changes private `status.json` to `needs_inspection` after 180 seconds.
The coordinator MUST inspect processes and tools, and rule out legitimate
execution, permissions, and user questions. After that inspection, write the
current `attempt` token into `confirm-stall` in the printed checkpoint directory.
It is accepted only during silence with no known active tool or permission wait.
A stale token cannot stop a later attempt. Never confirm from time alone.
The one-hour attempt limit stops without fallback. Configure these bounds with
`--idle-seconds` and `--limit-seconds`.

## Handoff and safety

The writer process group receives TERM, then KILL if needed. Handoff requires
proof that the group is gone. SIGINT and SIGTERM run cleanup. After a crash,
the next invocation refuses to run while the recorded group exists.
Workers MUST NOT detach processes or spawn subagents. Process groups cannot
contain daemons that deliberately escape them. Inspect and stop such writers
before restarting. The worktree lock serializes supervisor invocations only.

The same worktree retains edited and untracked files. A private checkpoint
holds the assignment, role instructions, model history, and `progress.md`.
Writers record completed checks and remaining work. Missing records remain
unknown; the next writer inspects and verifies them. Raw CLI streams, tool
output, and environment values are not saved. CLI session storage follows
each CLI's configuration. Keep checkpoints until independent review completes.

Workers MUST NOT perform external mutations, push, merge, or change global
settings. Return proposed external actions to the coordinator. These are
worker instructions, not an OS security boundary. CLI permission controls
remain active. Never replay uncertain external actions.

A separate Codex or Grok agent independently reviews the current diff and runs
the required tests. Assign read-only ownership, targeted context, acceptance
criteria, and concrete failure cases. Reviewers MUST NOT repair reviewed code.
Return findings to the owning writer, then rerun affected checks and review.
The coordinator records reviewer identity, tested revision, commands, outcomes,
and unverified scope. A writer cannot certify its own independent review.
Do not use `resume --last`; it can select another task. Preserve model constraints
on repair assignments. Claude Code and Claude authentication are not required.

## Context and graph

The coordinator retains broad project context. Workers receive bounded,
self-contained briefs rather than the full conversation or architecture.
For exploration, provide the goal, acceptance criteria, hard safety and product
constraints, assigned scope, and relevant data contracts. Permit alternative
designs. For implementation, add only the source, wiki, and graph context needed
for integration. The coordinator compares and validates proposals before use.
A proposal does not expand scope or permission.

Read the selected role TOML directly; graph output can omit role definitions.
Graph queries are available on demand or for a targeted integration question.
Do not require every worker to read the whole graph. If a needed graph is absent
or stale, report that fact and use targeted source reads. Compare manifest hashes
before relying on it. Different commit IDs alone do not imply different trees.
A coordinator MAY copy a validated graph from an identical tree. Refresh only
within the authorized scope. Ignored graph files may be absent from a worktree.
A branch or session does not confer automatic graph or project knowledge.

## Verification and rollout

```bash
PYTHONPATH=. uv run --project backend pytest -q tests/supervisor
uv run --project backend ruff check dev_supervisor tests/supervisor
uv run --project backend ruff format --check dev_supervisor tests/supervisor
uv run --project backend mypy --strict dev_supervisor
```

Run the four root backend gates as well. Simulated events do not prove live
quota failures or every tool schema. Unknown events need inspection. Revalidate
adapters when CLIs change. This command activates routing only in its target
checkout. It does not update the saved checkout or hot-reload native roles.
