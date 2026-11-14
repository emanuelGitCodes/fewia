# The `.claude/` folder

This folder configures Claude Code for FEWIA. Each file type has one job.
This page says what each one does, when Claude Code loads it, and how to
test it.

## Map

| Path | Type | Loaded when | Committed |
|---|---|---|---|
| `../CLAUDE.md` | Memory | Every session start | yes |
| `settings.json` | Settings, model, advisor, hooks, permissions | Session start, and on change | yes |
| `settings.local.json` | Personal overrides | After `settings.json` | no |
| `hooks/*.sh`, `hooks/*.py` | Hook scripts, shared with Codex through `.codex/hooks.json` | On the event named in `settings.json` or `.codex/hooks.json` | yes |
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
| `guard-senior-edits.sh` | `PreToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit`; Codex `apply_patch` | The senior MUST NOT write code. Every path in a checkout of the repository is denied except prose, `wiki/`, `docs/`, and agent config. A writer with `FEWIA_WRITER=1` is allowed. |
| `guard-bash.sh` | `PreToolUse` | `Bash` | Deny a gitleaks skip, supervisor dir deletion, force push, push to main. Ask on external writes. Codex accepts one exact approved push or PR body edit. |
| `check-pr-size.sh` | `PreToolUse` | `Bash`, only `gh pr create` | A PR MUST NOT add more than 1000 code lines. |
| `check-pr-done.sh` | `PreToolUse` | `Bash`, only `gh pr create` | HEAD needs a clean gates record and an `APPROVE` review in `.fewia-supervisor-*`. |
| `check-agents-pr.sh` | `PreToolUse` | `Bash`, only `gh pr create` | A `.claude/agents/` change ships alone and links a wiki page. |
| `guard-wiki-log.sh` | `PreToolUse` | `Edit\|Write\|MultiEdit`; Codex `apply_patch`; on `wiki/log.md` | The log is append-only. |
| `session-context.sh` | `SessionStart` | all | Report the branch, the open loop ledgers, and the worktree count. |
| `stop-wiki-reminder.sh` | `Stop` | all | Remind when a branch is ahead of main with no log entry. Never blocks. |
| `record-usage.sh` | `Stop` | all | Append the session's new token counts to the usage ledger as `coordinate`. Never blocks. |
| `record-usage.sh` | `SubagentStop` | all | Append the subagent's token counts as `junior` with its agent type. Never blocks. |
| `lint-prose.sh` | `PostToolUse` | `Edit\|Write`; Codex `apply_patch`; on `.md` | Flag house-style violations. Never blocks. |

The three `gh pr create` hooks share `pr-checkout.sh`. It finds the
checkout from a leading `cd <dir> &&`, else from the `cwd` of the hook
input, else from the project root. It reads the `--base` flag to find the
parent branch. Open a stacked pull request with `--base`.

A desktop session in a worktree runs the hooks from the main checkout,
with `CLAUDE_PROJECT_DIR` set to the main checkout. Claude Code removes a
leading `cd` to the session cwd from the command before a hook reads it.
The input `cwd` still names the worktree, so the hooks check the worktree.

`guard-bash.sh` reads the whole command text. Its raw checkpoint deletion
and gitleaks checks can match text inside a heredoc. Write such text with the
Write tool instead.
`guard-senior-edits.sh` does not see file writes made with a shell
command. The rule in `CLAUDE.md` still binds the senior there. A Claude
writer runs `claude -p --safe-mode`, so no project hook runs inside it;
its file scope comes from the `Edit(//path)` rules that `dev_supervisor`
passes.

The edit hooks read their target files through `edit-targets.py`. It
reads `tool_input.file_path` from Claude Code and Grok. It reads the
`*** Add File:`, `*** Update File:`, `*** Delete File:`, and
`*** Move to:` lines of a Codex `apply_patch` patch, relative to the
session `cwd`.

### Codex

`.codex/hooks.json` runs the same scripts for an interactive Codex
session. Each command calls `codex-hook.sh <script>`. The wrapper sets
`CLAUDE_PROJECT_DIR` to the git root and `FEWIA_HOOK_HOST=codex`, then
runs `.claude/hooks/<script>`. Keep one copy of each script, in
`.claude/hooks/`.

- Codex runs a project hook only after the user trusts it. Run `/hooks`
  in an interactive Codex session in the main checkout. A changed hook
  needs trust again.
- In a linked worktree, Codex 0.159 runs the main checkout's
  `.codex/hooks.json`. Keep the main checkout on a branch that has it.
- Codex hooks cannot ask. `guard-bash.sh` denies an external write under
  Codex unless the command matches a single-use approval below.
- `dev_supervisor` starts Codex writers and reviews with
  `--ignore-user-config`. Project hooks do not load there.

### Record one approved Codex push

The coordinator MUST have explicit user approval for the intended branch
publication. Existing approval for the task remains valid. The coordinator
verifies and binds the checkout, remote, push URL, branch, and final SHA.
These bindings do not require the user to repeat approval after the final
commit. Keep source and reason free of secrets. This command creates a
local record; it does not push.

```bash
python3 .claude/hooks/publication-approval.py record \
  --checkout /absolute/path/to/fewia \
  --remote origin --branch codex/security-hardening \
  --push-url git@github.com:example/fewia.git \
  --head 0123456789abcdef0123456789abcdef01234567 \
  --source 'Current chat: user explicitly approved this branch push' \
  --reason 'Publish the reviewed security fixes'
```

Submit the printed command without edits:

```text
git push --no-follow-tags --recurse-submodules=no origin <full-sha>:refs/heads/codex/security-hardening
```

Extra whitespace, quotes, flags, expansions, and compound commands do not
match. The branch MUST be the current `codex/` branch. The helper accepts
one effective GitHub push URL in SCP, HTTPS, or `ssh://git@github.com/` form.
The explicit `--push-url` MUST match that URL. Credentials, ports, query
strings, and other hosts are rejected. Remote names and branch segments
use letters, digits, `_`, and `-`. Remote names start with a letter.
Branch segments start with a letter or digit.

The helper rejects Git environment overrides except `GIT_PAGER`. It rejects
remote mirror mode, push options, custom VCS or receive-pack commands, and
`core.sshCommand`. It checks these constraints at record time and use time.
The exact refspec limits the push to one SHA and branch. The printed flags
disable automatic tag and submodule pushes.

The checkout MUST be an absolute canonical worktree root. Every supplied
`cwd` and `tool_input.workdir` MUST match the wrapper's project root. When
both are absent, the actual hook cwd MUST match that root. The checker
compares the decoded command exactly, including trailing newlines.

The helper creates `fewia-publication-approval.json` exclusively in the
worktree's Git metadata directory. Linked worktrees have separate records.
The record binds the command, checkout, HEAD, branch, remote, URL, and Git
configuration digest. It expires after one hour. It MUST be a regular file
owned by the current user, with mode `0600` and one link.

The guard calls `consume` after its hard denies. An exclusive lock permits
one matching attempt and removes the record. Mismatches preserve it. A
failed push consumes it. Other PR actions, merges, forced or broad pushes,
pushes to main, and gitleaks skips remain blocked.

For recovery, inspect the record before removing it. Locate its directory
with `git rev-parse --absolute-git-dir` in the intended checkout. Remove
only `fewia-publication-approval.json`. The helper never overwrites it.
The coordinator MUST confirm approval covers the next exact push before
recording again. Do not retry an uncertain external action.

### Record one approved Codex PR body edit

The coordinator MUST have explicit user approval for the intended PR body
edit. A push grant cannot approve a body edit. A body grant cannot approve
a push. Only the coordinator performs publication.

Before preparing the replacement, review the current remote body. Compute
the SHA-256 digest of its exact decoded UTF-8 bytes, including an empty body.
Do not add a newline during decoding. Keep that reviewed digest for
`--remote-body-sha256`. The flag MUST contain exactly 64 lowercase hex digits.

Prepare the reviewed body as a UTF-8 file without NUL bytes. The file MUST
have mode `0600`, one link, and the current user's ownership. It MUST be a
regular file with at most 65,536 bytes. Its absolute canonical path MUST
contain only letters, digits, `_`, `-`, `.`, and `/`. No path component
can be `.` or `..`. Neither the file nor any parent can be a symlink.

Review the exact bytes before recording their SHA-256 digest. This example
assumes `/absolute/path/to/reviewed-body.md` already contains those bytes.
`REVIEWED_REMOTE_BODY_SHA256` holds the digest from the remote body review:

```bash
python3 .claude/hooks/publication-approval.py record-pr-body \
  --checkout /absolute/path/to/fewia \
  --remote origin --branch codex/security-hardening \
  --push-url git@github.com:example/fewia.git \
  --head 0123456789abcdef0123456789abcdef01234567 \
  --repo example/fewia --pr 494 \
  --body-file /absolute/path/to/reviewed-body.md \
  --body-sha256 "$(shasum -a 256 /absolute/path/to/reviewed-body.md | cut -d ' ' -f 1)" \
  --remote-body-sha256 "$REVIEWED_REMOTE_BODY_SHA256" \
  --source 'Current chat: user explicitly approved the PR description edit' \
  --reason 'Apply the reviewed PR description'
```

Submit the printed command without edits:

```text
gh pr edit 494 --repo github.com/example/fewia --body-file /absolute/path/to/reviewed-body.md
```

Both the read and the write name `github.com` explicitly. A hostless repo
can select a configured default host even when `GH_HOST` is empty.
The repo MUST match the effective push URL without case, after removal
of one trailing `.git`. Owner names use letters, digits, `_`, and `-`.
Repo names also permit dot-separated segments. The PR number MUST be a
positive canonical decimal number with at most ten digits.

At record time and consume time, the helper runs one read-only command:

```text
gh pr view 494 --repo github.com/example/fewia --json number,url,headRefOid,headRefName,isCrossRepository,state,isDraft,body
```

The PR MUST be open and a draft. It MUST have a same-repo head whose SHA
and branch match the reviewed checkout. The response MUST name the same
PR URL and number. The helper binds the current remote body digest,
including an empty body. At record time, that digest MUST match the supplied
`--remote-body-sha256`. Consumption compares a second view to the same digest.
Any remote body, head, branch, or state change
rejects consumption. The remote response supplies state, never commands.

Body grants use version 2 records. Push grants retain the version 1 schema.
Both use the same exclusive metadata record, expiry, and nonblocking lock.
Body grants also bind the repo, PR number, file path, content digest, and
file identity. Replacing or changing the file after recording rejects
consumption. Each snapshot checks every component for symlinks. Its final
absolute path identity MUST match the open file, even after an ancestor rename.
The helper checks the file again before it removes the grant.

The GitHub read disables prompts, discards stderr, limits stdout to 262,144
bytes, and has a 1.2-second deadline. The helper limits its total work to
3.8 seconds plus bounded process cleanup. It rejects conflicting `GH_HOST`,
`GH_REPO`, `GH_CONFIG_DIR`, `GH_DEBUG`, and deprecated `DEBUG` settings.
It also rejects `GH_PATH`, which changes executable discovery.
`GH_HOST` can be empty or `github.com`. The other listed settings MUST be
empty or absent, except `GH_PATH`, which MUST be absent. Common harmless
settings and existing auth variables remain available. The probe overrides
`GH_PAGER` and `PAGER` with `cat`. The helper does not read credential files
or print body data.

A body grant approves only the printed body edit. It cannot approve title,
base, label, reviewer, attachment, state, ready, review, merge, or API changes.
An allowed attempt consumes the grant even if the subsequent edit fails.
The coordinator MUST verify the result after an attempt. The coordinator
MUST NOT blindly retry an uncertain edit.

### Publication check limits

This local check trusts the local user, hooks, Git, and GitHub CLI. It does
not authenticate chat approval. The operator MUST preserve Git state from
validation through publication. Local files and Git state can change after
hook validation, including between the helper's final file check and gh's
file read. Remote state can change after the snapshot. The body edit
has no server-side compare-and-swap. The hook cannot lock these gaps.
The guard uses `git-publication-command.py` to classify literal shell
words. The bounded lexer decodes adjacent quoted pieces and backslash
escapes without executing shell code. For example, `pu''sh` and `p\ush`
both name `push`. Quoted separators remain inside their words. Unquoted
separators split compound commands for inspection.
The guard also applies the legacy raw GitHub write regex after hard denials.
This fallback can match wrapped commands, quoted filters, and comments.

The classifier inspects bare, path, quoted, and concatenated Git and `gh` executable
names. It compares executable basenames without case for macOS paths.
It handles common `env`, `command`, `exec`, `time`, and `nohup`
wrappers. It checks global options before the Git subcommand. Unknown
global options receive a conservative scan for publication commands.
The scan keeps uncertainty through the remaining words. A possible write
causes a denial even if an earlier word names a read command.
For example, `git --namespace status push origin feature` is denied.
This can deny a read such as `git --namespace team log --grep push`.
An unfamiliar prefix without a possible write retains literal-read behavior.
Normalized force flags, broad pushes, gitleaks skips, and destinations of
`main` or `refs/heads/main` remain hard denials. A feature destination such
as `codex/main` does not name `main`.

The classifier routes direct `gh pr create`, `edit`, `merge`, `close`,
`ready`, `reopen`, `review`, `comment`, `lock`, and `unlock` to confirmation.
It detects API methods in short, long, equals, and attached forms. API
inputs and fields imply a write unless an explicit read method overrides
them. Explicit `GET`, `HEAD`, and `OPTIONS` requests remain usable.
Known PR reads, help, and local checkout remain usable with dynamic tail
arguments. Other literal top-level `gh` groups also accept dynamic tail
arguments. API reads accept preview flags and quoted scalar values for known
value options, such as `--jq`. These values cannot supply a method option.
Dynamic methods and unquoted API expansions fail closed. Ambiguous direct
`gh` publication forms fail closed.

The guard denies unsupported or ambiguous direct publication forms. Simple
literal writes use the host's confirmation policy. The lexer
does not grant approval: only the unchanged raw decoded command can match
the approval record. This match remains case-sensitive. Quoting, escapes,
wrappers, extra arguments, and compound commands cannot match it through
normalization.

This guard is not a shell sandbox. Shell aliases, Git or `gh` aliases, functions,
indirect programs, and dynamically constructed shell code fall outside
its supported classification. It does not resolve aliases, evaluate
expansions, or parse arbitrary shell grammar. ANSI-C fragments and dynamic
subcommands in direct Git and `gh` calls are denied without evaluation.
Direct publication commands with an ambiguous subcommand or dynamic write arguments
are denied. The coordinator MUST use direct literal commands for publication.

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
4. Register it in `.codex/hooks.json` with the command
   `"$(git rev-parse --show-toplevel)/.claude/hooks/codex-hook.sh" <name>.sh`.
   Codex reports a file edit as `apply_patch`.
5. Validate the files: `jq -e .hooks .claude/settings.json .codex/hooks.json`.
6. Claude Code reloads `settings.json` on change. A hook on
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
