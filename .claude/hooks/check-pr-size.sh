#!/usr/bin/env bash
# PreToolUse hook for Bash, filtered to the pull request create command.
# Rule: a pull request MUST NOT add more than 1000 lines of code.
# Tests, documentation, lockfiles, and generated files do not count.
set -euo pipefail

input="$(cat)"
cmd="$(jq -r '.tool_input.command // empty' <<<"$input")"
grep -Eq 'gh\s+pr\s+create\b' <<<"$cmd" || exit 0
. "$(dirname "$0")/pr-checkout.sh"

cap=1000
merge="$(git -C "$dir" merge-base "$base" HEAD 2>/dev/null || true)"
if [ -z "$merge" ]; then
  jq -n --arg b "$base" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:("Cannot resolve the base ref " + $b + ", so the 1000-line cap cannot be checked. Fetch it or pass --base.")}}'
  exit 0
fi
# The pull request carries HEAD, so measure the committed diff.
lines="$(git -C "$dir" diff --numstat "$merge" HEAD | awk -F'\t' '
  $1 != "-" \
  && $3 !~ /(^|\/)(test|tests|spec|__tests__|vendor|dist|build|node_modules)\// \
  && $3 !~ /(^|\/)test_[^\/]*\.py$/ \
  && $3 !~ /\.(test|spec)\.[tj]sx?$/ \
  && $3 !~ /\.(md|mdx|rst|adoc|txt|lock|snap)$/ \
  && $3 !~ /-lock\.json$/ \
  {s+=$1} END {print s+0}')"

if [ "$lines" -gt "$cap" ]; then
  jq -n --arg n "$lines" --arg c "$cap" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:("This branch adds " + $n + " code lines. The cap is " + $c + ". Split it into a stack (stacked-prs skill).")}}'
  exit 0
fi
jq -n --arg n "$lines" --arg b "$base" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:("PR size check: " + $n + " added code lines against " + $b + " (cap 1000).")}}'
