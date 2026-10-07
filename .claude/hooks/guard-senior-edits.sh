#!/usr/bin/env bash
# PreToolUse hook for Edit, Write, MultiEdit, and NotebookEdit.
# Rule: the senior session MUST NOT write application, test, or
# infrastructure code. It MAY edit prose, the wiki, and agent configuration.
# Every path in a checkout of the repository is denied unless it is on the
# allow list. The checkouts are the project root and every worktree that
# `git worktree list` reports, including the main checkout. A path in no
# checkout, such as the scratchpad, is allowed.
# A writer that dev_supervisor starts has FEWIA_WRITER=1 and is allowed.
set -euo pipefail

input="$(cat)"
[ "${FEWIA_WRITER:-}" = 1 ] && exit 0
path="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")"
[ -z "$path" ] && exit 0

root="$(cd "${CLAUDE_PROJECT_DIR:-$PWD}" && pwd -P)"
# A relative path is relative to the project root. Resolve `..`, `.`, and
# symbolic links so a path cannot step back into a checkout. The deepest
# checkout that holds the path sets the relative path.
case "$path" in /*) ;; *) path="$root/$path" ;; esac
rel="$(python3 -c '
import os, subprocess, sys
path = os.path.realpath(sys.argv[1])
root = sys.argv[2]
try:
    listing = subprocess.run(
        ["git", "-C", root, "worktree", "list", "--porcelain", "-z"],
        capture_output=True, text=True,
    ).stdout
except OSError:
    listing = ""
tops = [root] + [f[9:] for f in listing.split("\0") if f.startswith("worktree ")]
best = ""
for top in tops:
    top = os.path.realpath(top)
    if path.startswith(top + os.sep) and len(top) > len(best):
        best = top
print(os.path.relpath(path, best) if best else "")
' "$path" "$root")"
[ -z "$rel" ] && exit 0

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
