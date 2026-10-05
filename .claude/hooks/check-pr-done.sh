#!/usr/bin/env bash
# PreToolUse hook for Bash, filtered to `gh pr create`.
# Rule: a work item is done when the gates pass on the head SHA and the
# review command returns APPROVE on the same SHA. Both records live on
# disk, keyed by SHA. Deny the pull request when either one is missing.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // empty')"
grep -Eq 'gh\s+pr\s+create\b' <<<"$cmd" || exit 0

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

# A leading `cd <dir> &&` names the checkout the command runs in.
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
if [[ "$cmd" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:];&]+) ]]; then
  dir="${BASH_REMATCH[1]/#\~/$HOME}"
  [[ "$dir" = /* ]] || dir="${CLAUDE_PROJECT_DIR:-$PWD}/$dir"
fi
sha="$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)"
[ -z "$sha" ] && exit 0
root="${CLAUDE_PROJECT_DIR:-$PWD}"

gates=""
for cand in "$dir/.fewia-supervisor-gates/$sha.json" "$root/.fewia-supervisor-gates/$sha.json"; do
  [ -f "$cand" ] && { gates="$cand"; break; }
done
[ -z "$gates" ] && deny "No gates record for HEAD ${sha:0:7}. Run dev_supervisor.gates on this head first."
jq -e '.clean == true and ([.gates[]? | select(.status == "FAIL")] | length == 0)' "$gates" >/dev/null \
  || deny "The gates record for HEAD ${sha:0:7} is not clean or has a FAIL. Repair and run the gates again."

review=""
for d in "$dir/.fewia-supervisor-reviews" "$root/.fewia-supervisor-reviews"; do
  for f in "$d/$sha"-*.md; do
    [ -f "$f" ] && grep -q 'VERDICT: APPROVE' "$f" && { review="$f"; break 2; }
  done
done
[ -z "$review" ] && deny "No APPROVE review for HEAD ${sha:0:7}. Run dev_supervisor.review on this head first."

jq -n --arg s "${sha:0:7}" --arg r "$(basename "$review")" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:("Definition of done holds for " + $s + ": gates clean, review " + $r + ".")}}'
