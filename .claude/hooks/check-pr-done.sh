#!/usr/bin/env bash
# PreToolUse hook for Bash, filtered to the pull request create command.
# Rule: a work item is done when the gates pass on the head SHA and the
# review command returns APPROVE on the same SHA. Both records live on
# disk, keyed by SHA. Deny the pull request when either one is missing.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // empty')"
grep -Eq 'gh\s+pr\s+create\b' <<<"$cmd" || exit 0
. "$(dirname "$0")/pr-checkout.sh"

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

sha="$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)"
[ -z "$sha" ] && deny "Cannot read HEAD in $dir, so the gates and review records cannot be checked."
root="${CLAUDE_PROJECT_DIR:-$PWD}"

gates=""
for cand in "$dir/.fewia-supervisor-gates/$sha.json" "$root/.fewia-supervisor-gates/$sha.json"; do
  [ -f "$cand" ] && { gates="$cand"; break; }
done
[ -z "$gates" ] && deny "No gates record for HEAD ${sha:0:7}. Run dev_supervisor.gates on this head first."
jq -e '.clean == true and all(.gates[]?; .status == "PASS" or .status == "SKIP")' "$gates" >/dev/null \
  || deny "The gates record for HEAD ${sha:0:7} is not clean or has a row that is not PASS or SKIP. Repair and run the gates again."

review=""
for d in "$dir/.fewia-supervisor-reviews" "$root/.fewia-supervisor-reviews"; do
  for f in "$d/$sha"-*.md; do
    [ -f "$f" ] || continue
    # The verdict is the last non-empty line, with Markdown emphasis removed.
    last="$(grep -v '^[[:space:]]*$' "$f" | tail -1 | tr -d '*_' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ "$last" = "VERDICT: APPROVE" ] && { review="$f"; break 2; }
  done
done
[ -z "$review" ] && deny "No APPROVE review for HEAD ${sha:0:7}. Run dev_supervisor.review on this head first."

jq -n --arg s "${sha:0:7}" --arg r "$(basename "$review")" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:("Definition of done holds for " + $s + ": gates clean, review " + $r + ".")}}'
