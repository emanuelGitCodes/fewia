# 0020 — One hook set for every agent CLI

- Date: 2026-10-07 (America/New_York).
- Status: accepted; merged in #410, #411, #413, and #414.
- Relates to: [0013 — Claude senior coordinator](0013-claude-senior-coordinator.md),
  [0014 — Tiered delegation](0014-tiered-delegation.md), and
  [`.claude/README.md`](../../.claude/README.md).

## Decision

The scripts in `.claude/hooks/` are the only copy of the FEWIA hooks.
Claude Code, Grok, and Codex run the same scripts.

- Claude Code reads `.claude/settings.json`. Grok also reads that file.
- Codex reads `.codex/hooks.json`. Each command calls
  `.claude/hooks/codex-hook.sh <script>`. The wrapper sets
  `CLAUDE_PROJECT_DIR` to the git root and `FEWIA_HOOK_HOST=codex`.
- The edit hooks read their targets through `.claude/hooks/edit-targets.py`.
  It reads `tool_input.file_path` and the targets of a Codex `apply_patch`
  patch.
- `guard-senior-edits.sh` judges a path in every checkout of the
  repository: the project root, the main checkout, and each worktree that
  `git worktree list` reports.
- `dev_supervisor` starts every writer with `FEWIA_WRITER=1`. The edit
  guard allows a writer.
- Codex hooks cannot ask. Under Codex, `guard-bash.sh` denies an external
  write, and the user runs the command.

## Options considered

- Keep a separate copy of the hooks for each CLI. The Codex copy that
  appeared on 2026-10-06 showed the risk: it used absolute paths to one
  worktree, its scripts were stale within a day, and it read only
  `file_path`, so it enforced nothing.
- Delete the Codex hooks and rely on prose rules for Codex sessions. The
  rules in `AGENTS.md` then have no enforcement in an interactive Codex
  session.
- Exempt writers by model or provider name. The hook input does not carry
  the provider, and a writer can be Codex or Grok. An environment variable
  that `dev_supervisor` sets reaches the hook process in both CLIs.

## Reason

One script set cannot drift. Probes with Grok 1.0.41 and Codex 0.159
confirmed the inputs, the environment, and the outcomes before the merge.
End-to-end runs denied a senior code edit, passed a writer edit, denied a
`git push` under Codex, and denied a `wiki/log.md` replacement.

## Consequences

- A user MUST trust the Codex hooks once with `/hooks` in an interactive
  Codex session. A changed hook needs trust again.
- In a linked worktree, Codex 0.159 runs the main checkout's
  `.codex/hooks.json`, and only when the worktree also has one. The main
  checkout SHOULD stay on a branch that has the file.
- `dev_supervisor` runs Codex writers and reviews with
  `--ignore-user-config`, so project hooks do not load there.
- A new hook MUST be registered in both `.claude/settings.json` and
  `.codex/hooks.json`. `tests/supervisor/test_codex_hooks.py` checks that
  every Codex command names an existing script.
- Project hooks did not run in the Claude Code desktop session that built
  this change. The cause is not known. A session MUST NOT assume that a
  hook blocked an action without evidence.
