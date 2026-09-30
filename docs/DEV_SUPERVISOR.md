# Development writer supervisor

Run from the repository root with Python 3.12:

```bash
uv run --project backend python -m dev_supervisor \
  --task /private/tmp/assignment.txt --role backend-dev --cwd "$PWD" \
  --complexity standard --write-file dev_supervisor/policy.py \
  --work-item fewia-42 --phase implement
```

`--task` takes a file path. The supervisor rejects inline text and a missing
role file before it takes the lease. The writer edits files only. The writer
prompt forbids shell commands, tests, package managers, and git commands; the
coordinator or the junior runs every check. The loop, the tiers, and the
budgets live in [DELEGATION.md](DELEGATION.md).

Replace the example file with each path named by the assignment.
The assignment MUST name owned files, interfaces, acceptance checks, and scope.
Use an isolated branch and worktree. Native workers MUST NOT write there while
the supervisor runs. Review the assignment and checkpoint for secrets.

For authorized source edits, repeat `--write-file relative/path` for each owned
file. The supervisor validates that each path stays inside the target worktree.
Grok receives exact `Write(path)` and `Edit(path)` allow rules for those files
and the private progress file. Default command checks remain enabled. This is
not blanket tool approval or a new scope grant. Paths that escape through
symlinks or contain permission-rule syntax are rejected before execution.

## Model selection

The coordinator picks the writer model and effort per work item from
[Writer selection](DELEGATION.md#writer-selection), and passes them with
`--only --model MODEL --effort LEVEL`. The default order below applies
only when a run omits `--model`. FEWIA work MUST NOT omit it.

The supervisor requires `--complexity`.
Valid values are `simple`, `standard`, `complex`, `exceptional`, and `maximum`.
The coordinator classifies each task before delegation:

| Complexity | Automatic effort |
|---|---|
| `simple` | `low` |
| `standard` | `medium` |
| `complex` | `high` |
| `exceptional` | `xhigh` |
| `maximum` | `max` |

The coordinator MUST NOT select `maximum` for ordinary tasks.
The coordinator MUST reserve `maximum` for the hardest cross-system work.
That work has substantial ambiguity, interacting failure modes, or major
security, reliability, or data-loss risk.

An optional `--effort` override replaces automatic selection when the model
supports effort.
The supervisor MUST NOT downgrade the requested effort.
An explicitly selected model that cannot use that effort stops with an error.
The supervisor skips incompatible fallback models.

| Order | CLI | Model | Effort capability |
|---|---|---|---|
| 1 | `~/.grok/bin/grok` | `grok-4.6` | ceiling `medium` |
| 2 | `codex exec` | `gpt-5.3-codex-spark` | CLI model default |
| 3 | `codex exec` | `gpt-6-luna` | ceiling `max` |

Grok 4.6 uses `low` for simple tasks.
Grok 4.6 uses `medium` for every harder automatic tier.
Grok 4.6 MUST NOT receive `high`, `xhigh`, or `max`.
Spark keeps its CLI model default.
Spark does not accept an effort override in this supervisor.
Luna and Sol support automatic selection through `max`.
Codex commands ignore user config to avoid inheriting another model's effort.
Authentication remains with the CLI.
The supervisor does not edit global configuration.

An explicit model request MUST become `--model MODEL_ID`. “Use GPT 5.6 Sol”
becomes `--model gpt-6.1-sol`. It runs first. Eligible failures use the remaining
default sequence without duplicates. Each selected model and outcome is printed.
“Only use Sol” MUST include `--only --model gpt-6.1-sol`. No substitute runs.
An explicit effort request MUST become `--effort LEVEL` when the model supports
effort.
Unknown models stop before execution. Extend the map with `--registry FILE`:

```toml
["gpt-5.6-terra"]
provider = "codex"
ceiling = "max"
```

A registry MUST NOT contain a built-in model ID.
A new provider needs a command adapter and tested event parsing. A registry
cannot inject shell commands. CLI arguments use argument lists.
Native `.codex/agents/*.toml` files keep the Luna model.
They MUST NOT pin `model_reasoning_effort`.
Native dispatch MUST select the effort from the complexity rubric.
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
the next invocation refuses to run while the recorded group exists or launch
state is ambiguous. Status updates are atomic. Only proven cleanup records
`stopped`; inspect an incomplete launch before any restart.
Workers MUST NOT detach processes or spawn subagents. Process groups cannot
contain daemons that deliberately escape them. Inspect and stop such writers
before restarting. The worktree lock serializes supervisor invocations only.

The same worktree retains edited and untracked files. A private, ignored
`.fewia-supervisor-*` directory inside that worktree holds the assignment,
role instructions, model history, and `progress.md`.
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

## Shared commands

These commands serve every coordinator tool.

| Command | Purpose |
|---|---|
| `python -m dev_supervisor.gates --cwd PATH --base REF [--reuse]` | Runs only the checks for the changed paths. Prints one line per check, `LINES n/150`, and `RESULT`. Records the result under `.fewia-supervisor-gates/<sha>.json`. |
| `python -m dev_supervisor.review --cwd PATH --base REF --brief FILE --complexity C --writer-model M` | Runs a read-only Codex review with a model other than the writer, a time cap, and short output. Exits 0, 1, or 2 for `APPROVE`, `REQUEST_CHANGES`, or `BLOCKED`. |
| `python -m dev_supervisor.usage [--work-item ID]` | Prints token and time totals per work item and phase from the shared ledger. |

The usage ledger lives at `<git common dir>/fewia-supervisor-usage.jsonl`, so
every worktree writes to one file. Grok runs report `unsupported` token
coverage.

When Codex is unavailable, run the review as a separate read-only Grok
session with the diff in the prompt, and record the deviation.

## Verification and rollout

```bash
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

Run the four root backend gates as well. Simulated events do not prove live
quota failures or every tool schema. Unknown events need inspection. Revalidate
adapters when CLIs change. This command activates routing only in its target
checkout. It does not update the saved checkout or hot-reload native roles.
