#!/usr/bin/env bash
# PreToolUse hook for Bash, filtered to `gh pr create`.
# Rule: a pull request MUST NOT add more than 150 lines of code.
# Tests, documentation, lockfiles, and generated files do not count.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // empty')"
grep -Eq 'gh\s+pr\s+create\b' <<<"$cmd" || exit 0
cap=150
base="$(git merge-base origin/main HEAD 2>/dev/null || git merge-base main HEAD)"
lines="$(git diff --numstat "$base" | awk -F'\t' '
  $1 != "-" \
  && $3 !~ /(^|\/)(test|tests|spec|__tests__|vendor|dist|build|node_modules)\// \
  && $3 !~ /(^|\/)test_[^\/]*\.py$/ \
  && $3 !~ /\.(test|spec)\.[tj]sx?$/ \
  && $3 !~ /\.(md|txt|lock|snap)$/ \
  && $3 !~ /-lock\.json$/ \
  {s+=$1} END {print s+0}')"

if [ "$lines" -gt "$cap" ]; then
  jq -n --arg n "$lines" --arg c "$cap" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:("This branch adds " + $n + " code lines. The cap is " + $c + ". Split it into a stack (stacked-prs skill).")}}'
  exit 0
fi
jq -n --arg n "$lines" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:("PR size check: " + $n + " added code lines (cap 150).")}}'
