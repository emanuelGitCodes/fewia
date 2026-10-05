#!/usr/bin/env bash
# PreToolUse hook for Edit, Write, MultiEdit, and NotebookEdit.
# Rule: the senior session MUST NOT write application, test, or
# infrastructure code. It MAY edit prose, the wiki, and agent configuration.
# Exit 0 with no output allows the call. A JSON deny blocks it.
set -euo pipefail

input="$(cat)"
path="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")"
[ -z "$path" ] && exit 0

root="${CLAUDE_PROJECT_DIR:-$PWD}"
rel="${path#"$root"/}"

# Prose and agent configuration are always allowed.
case "$rel" in
  *.md|*.txt|.claude/*|.codex/*|.opencode/*|.agents/*|wiki/*|docs/*|plans/*|runbooks/*)
    exit 0 ;;
esac

# Code trees are closed to the senior.
case "$rel" in
  backend/*|frontend/*|infra/*|dev_supervisor/*|eval/*|tests/*|.github/*|compose*.yaml|ruff.toml)
    jq -n --arg p "$rel" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("Senior edit blocked for " + $p + ". Delegate the change to a writer through dev_supervisor (see CLAUDE.md). Set disableAllHooks in .claude/settings.local.json to override for one session.")
      }
    }'
    exit 0 ;;
esac

exit 0
