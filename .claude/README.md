# The `.claude/` folder

This folder configures Claude Code for FEWIA. Each file type has one job.
This page says what each one does, when Claude Code loads it, and how to
test it.

## Map

| Path | Type | Loaded when | Committed |
|---|---|---|---|
| `../CLAUDE.md` | Memory | Every session start | yes |
| `settings.json` | Settings, hooks, permissions | Session start, and on change | yes |
| `settings.local.json` | Personal overrides | After `settings.json` | no |
| `hooks/*.sh` | Hook scripts | On the event named in `settings.json` | yes |
| `agents/*.md` | Subagent definitions | When the senior spawns one | yes |
| `skills/<name>/SKILL.md` | Skills, also slash commands | When invoked, or when the task matches | yes |
| `loop/<slug>.md` | Feature-loop ledgers | Read by the `feature-loop` skill | no |
| `worktrees/` | Git worktrees for work items | Created by the `feature-loop` skill | no |

Settings merge in this order. A later file overrides an earlier one:
`~/.claude/settings.json`, then `.claude/settings.json`, then
`.claude/settings.local.json`.

## Which file type for which need

- **A rule every session MUST know.** Put one sentence in `CLAUDE.md`.
  Keep it short. Long text goes in `docs/` and gets a link.
- **A rule that MUST run without the model's cooperation.** Write a hook.
  A hook is a shell script. Claude Code runs it on an event. The model
  cannot skip it.
- **A procedure the model follows on request.** Write a skill. A skill is
  a folder with `SKILL.md`. The user runs it with `/<name>`. The model
  loads it when the description matches the task.
- **A worker with its own tools and model.** Write an agent. An agent is
  one Markdown file with frontmatter. The senior spawns it with the Agent
  tool.
- **A rule for one path only.** Write `rules/<name>.md` with a `paths:`
  list in the frontmatter. Claude Code loads it when a matching file is
  touched. FEWIA has none today.
- **A personal preference.** Put it in `settings.local.json`. Git ignores
  that file.

## Hooks

A hook receives one JSON object on stdin. It answers on stdout.

- Exit 0 with no output: the call proceeds.
- JSON with `permissionDecision: "deny"`: the call is blocked. The reason
  goes back to the model.
- JSON with `permissionDecision: "ask"`: the user confirms the call.
- JSON with `additionalContext`: the text goes into the model's context.

| Script | Event | Matcher | Rule it enforces |
|---|---|---|---|
| `guard-senior-edits.sh` | `PreToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit` | The senior MUST NOT write code. Every repository path is denied except prose, `wiki/`, `docs/`, and agent config. |
| `guard-bash.sh` | `PreToolUse` | `Bash` | Deny a gitleaks skip, supervisor dir deletion, force push, push to main. Ask on push, PR, merge. |
| `check-pr-size.sh` | `PreToolUse` | `Bash`, only `gh pr create` | A PR MUST NOT add more than 150 code lines. |
| `check-pr-done.sh` | `PreToolUse` | `Bash`, only `gh pr create` | HEAD needs a clean gates record and an `APPROVE` review in `.fewia-supervisor-*`. |
| `check-agents-pr.sh` | `PreToolUse` | `Bash`, only `gh pr create` | A `.claude/agents/` change ships alone and links a wiki page. |
| `guard-wiki-log.sh` | `PreToolUse` | `Edit\|Write\|MultiEdit` on `wiki/log.md` | The log is append-only. |
| `session-context.sh` | `SessionStart` | all | Report the branch, the open loop ledgers, and the worktree count. |
| `stop-wiki-reminder.sh` | `Stop` | all | Remind when a branch is ahead of main with no log entry. Never blocks. |
| `lint-prose.sh` | `PostToolUse` | `Edit\|Write` on `.md` | Flag house-style violations. Never blocks. |

The three `gh pr create` hooks share `pr-checkout.sh`. It reads a leading
`cd <dir> &&` to find the checkout and the `--base` flag to find the
parent branch. Open a stacked pull request with both.

`guard-bash.sh` reads the whole command text. A heredoc that quotes a
blocked command trips it. Write such text with the Write tool instead.
`guard-senior-edits.sh` does not see file writes made with a shell
command. The rule in `CLAUDE.md` still binds the senior there.

### Test a hook

Pipe the JSON the event sends. Read the output and the exit code.

```bash
echo '{"tool_input":{"file_path":"'"$PWD"'/backend/app/main.py"}}' | .claude/hooks/guard-senior-edits.sh
```

```bash
echo '{"tool_input":{"command":"git push origin main"}}' | .claude/hooks/guard-bash.sh
```

```bash
echo '{}' | CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/session-context.sh
```

### Add a hook

1. Write the script in `hooks/`. Start it with `set -euo pipefail`. Read
   stdin with `jq`.
2. Pipe-test it as above.
3. Register it in `settings.json` under the event name. Use
   `"$CLAUDE_PROJECT_DIR"/.claude/hooks/<name>.sh` as the command.
4. Validate the file: `jq -e .hooks .claude/settings.json`.
5. Claude Code reloads `settings.json` on change. A hook on
   `SessionStart` fires at the next session.

### Turn hooks off for one session

Create `.claude/settings.local.json` with `{"disableAllHooks": true}`.
Delete the file afterwards.

## Agents

Each file in `agents/` is a thin adapter. The frontmatter sets the name,
the description, the tools, and the model. The body points to the
canonical role in `.codex/agents/<role>.toml` and to
`docs/delegation/junior.md`. Juniors have no Edit or Write tool. A change
to a file in `agents/` MUST ship as its own pull request with a wiki link.

## Skills

A skill is a folder with `SKILL.md`. `references/` holds templates the
skill copies. `scripts/` holds commands the skill runs. Global skills live
in `~/.claude/skills/` and apply to every repository.

| Skill | Use |
|---|---|
| `feature-loop` | Build a feature with the tiered delegation loop. |
| `gates` | Run the gates with the throwaway `fewia_eval` PostgreSQL. |
| `wiki-log` | Append a log entry or write a decision page. |
| `worktree-cleanup` | Remove worktrees whose branch is merged, after a yes. |

## Ledgers and worktrees

`loop/` holds one ledger per feature loop. `worktrees/` holds one checkout
per work item. Git ignores both. Delete a worktree with
`git worktree remove`, not `rm`.
