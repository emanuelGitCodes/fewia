#!/usr/bin/env bash
# PreToolUse hook for Bash, filtered to the pull request create command.
# Rule: a change to a file in `.claude/agents/` MUST ship as its own pull
# request. The body MUST link the wiki entry that records the reason.
set -euo pipefail

input="$(cat)"
cmd="$(jq -r '.tool_input.command // empty' <<<"$input")"
grep -Eq 'gh\s+pr\s+create\b' <<<"$cmd" || exit 0
. "$(dirname "$0")/pr-checkout.sh"

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

merge="$(git -C "$dir" merge-base "$base" HEAD 2>/dev/null || true)"
[ -z "$merge" ] && deny "Cannot resolve the base ref $base, so the agents rule cannot be checked. Fetch it or pass --base."
files="$(git -C "$dir" diff --name-only "$merge" HEAD)"
grep -q '^\.claude/agents/' <<<"$files" || exit 0

others="$(grep -v '^\.claude/agents/' <<<"$files" | grep -v '^wiki/' || true)"
[ -n "$others" ] && deny "This branch changes .claude/agents/ together with: $(tr '\n' ' ' <<<"$others"). An agent change ships alone (CLAUDE.md)."

# The body comes from --body-file, else from the quoted --body value.
# Any other form, such as --fill, has no body to check.
body=""
if [[ "$cmd" =~ --body-file[[:space:]=]+\"?([^[:space:]\"]+) ]]; then
  bf="${BASH_REMATCH[1]}"
  [ -r "$bf" ] || deny "The body file $bf is not readable, so the wiki link cannot be checked."
  body="$(cat "$bf")"
elif [[ "$cmd" =~ --body[[:space:]=]+\"([^\"]*)\" ]] || [[ "$cmd" =~ --body[[:space:]=]+\'([^\']*)\' ]] || [[ "$cmd" =~ --body[[:space:]=]+([^[:space:]]+) ]]; then
  body="${BASH_REMATCH[1]}"
fi
grep -q 'wiki/' <<<"$body" || deny "An agent change needs a wiki link in the PR body. Record the reason in wiki/ first (CLAUDE.md)."

exit 0
