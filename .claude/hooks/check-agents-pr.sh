#!/usr/bin/env bash
# PreToolUse hook for Bash, filtered to `gh pr create`.
# Rule: a change to a file in `.claude/agents/` MUST ship as its own pull
# request. The body MUST link the wiki entry that records the reason.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // empty')"
grep -Eq 'gh\s+pr\s+create\b' <<<"$cmd" || exit 0

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

dir="${CLAUDE_PROJECT_DIR:-$PWD}"
if [[ "$cmd" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:];&]+) ]]; then
  dir="${BASH_REMATCH[1]/#\~/$HOME}"
  [[ "$dir" = /* ]] || dir="${CLAUDE_PROJECT_DIR:-$PWD}/$dir"
fi

base="$(git -C "$dir" merge-base origin/main HEAD 2>/dev/null || git -C "$dir" merge-base main HEAD 2>/dev/null || true)"
[ -z "$base" ] && exit 0
files="$(git -C "$dir" diff --name-only "$base" HEAD)"
grep -q '^\.claude/agents/' <<<"$files" || exit 0

others="$(grep -v '^\.claude/agents/' <<<"$files" | grep -v '^wiki/' || true)"
[ -n "$others" ] && deny "This branch changes .claude/agents/ together with: $(tr '\n' ' ' <<<"$others"). An agent change ships alone (CLAUDE.md)."

# The body is inline (--body) or in a file (--body-file).
body="$cmd"
if [[ "$cmd" =~ --body-file[[:space:]=]+([^[:space:]]+) ]]; then
  bf="${BASH_REMATCH[1]//\"/}"
  [ -f "$bf" ] && body="$(cat "$bf")"
fi
grep -q 'wiki/' <<<"$body" || deny "An agent change needs a wiki link in the PR body. Record the reason in wiki/ first (CLAUDE.md)."

exit 0
