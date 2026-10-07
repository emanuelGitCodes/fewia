#!/usr/bin/env bash
# PreToolUse hook for Edit, Write, MultiEdit, NotebookEdit, and Codex
# apply_patch.
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

root="$(cd "${CLAUDE_PROJECT_DIR:-$PWD}" && pwd -P)"
# edit-targets.py lists every file the call writes, relative to the deepest
# checkout that holds it. A patch can write several files.
rels="$(python3 "$(dirname "$0")/edit-targets.py" --relative "$root" <<<"$input")"

denied=""
while IFS= read -r -d '' rel; do
  # A worktree under .claude/worktrees/ holds a full checkout. Judge a path
  # in a worktree by its path relative to that worktree.
  check="$rel"
  while [[ "$check" == .claude/worktrees/*/* ]]; do
    check="${check#.claude/worktrees/*/}"
  done
  case "$check" in
    *.md|*.txt|.claude/*|.codex/*|.opencode/*|.agents/*|wiki/*|docs/*|plans/*|runbooks/*) ;;
    *) denied="${denied:+$denied, }$rel" ;;
  esac
done < <(jq -j '.[] + "\u0000"' <<<"$rels")

[ -z "$denied" ] && exit 0

jq -n --arg p "$denied" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("Senior edit blocked for " + $p + ". Only prose, wiki/, docs/, and agent configuration are open. Delegate code to a writer through dev_supervisor (CLAUDE.md). Set disableAllHooks in .claude/settings.local.json to override for one session.")
  }
}'
