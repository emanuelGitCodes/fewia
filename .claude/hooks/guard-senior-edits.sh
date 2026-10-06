#!/usr/bin/env bash
# PreToolUse hook for Edit, Write, MultiEdit, and NotebookEdit.
# Rule: the senior session MUST NOT write application, test, or
# infrastructure code. It MAY edit prose, the wiki, and agent configuration.
# Every path inside the repository is denied unless it is on the allow list.
# A path outside the repository, such as the scratchpad, is allowed.
# A writer that dev_supervisor starts has FEWIA_WRITER=1 and is allowed.
set -euo pipefail

input="$(cat)"
[ "${FEWIA_WRITER:-}" = 1 ] && exit 0
path="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")"
[ -z "$path" ] && exit 0

root="$(cd "${CLAUDE_PROJECT_DIR:-$PWD}" && pwd -P)"
# A relative path is relative to the project root. Collapse `..` and `.`
# so a path cannot step back into the repository.
case "$path" in /*) ;; *) path="$root/$path" ;; esac
path="$(python3 -c 'import os, sys; print(os.path.normpath(sys.argv[1]))' "$path")"
case "$path" in
  "$root"/*) rel="${path#"$root"/}" ;;
  *) exit 0 ;;
esac

# A worktree under .claude/worktrees/ holds a full checkout. Judge a path
# in a worktree by its path relative to that worktree.
check="$rel"
while [[ "$check" == .claude/worktrees/*/* ]]; do
  check="${check#.claude/worktrees/*/}"
done

case "$check" in
  *.md|*.txt|.claude/*|.codex/*|.opencode/*|.agents/*|wiki/*|docs/*|plans/*|runbooks/*)
    exit 0 ;;
esac

jq -n --arg p "$rel" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("Senior edit blocked for " + $p + ". Only prose, wiki/, docs/, and agent configuration are open. Delegate code to a writer through dev_supervisor (CLAUDE.md). Set disableAllHooks in .claude/settings.local.json to override for one session.")
  }
}'
