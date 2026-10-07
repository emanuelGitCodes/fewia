#!/usr/bin/env bash
# PostToolUse hook for Edit, Write, and Codex apply_patch on Markdown files.
# Reports house-style violations back to the model. It never blocks.
set -euo pipefail

input="$(cat)"
report=""
while IFS= read -r -d '' path; do
  case "$path" in *.md) ;; *) continue ;; esac
  [ -f "$path" ] || continue
  findings="$(grep -nE \
    -e '\b(utilize|utilise|leverage|prior to|in order to|initiate|facilitate)\b' \
    -e '\b(SHALL|REQUIRED|RECOMMENDED|OPTIONAL)\b' \
    -e '—' \
    "$path" | head -10 || true)"
  [ -n "$findings" ] && report="${report}house-style: review these lines in $path:
$findings
"
done < <(python3 "$(dirname "$0")/edit-targets.py" <<<"$input" | jq -j '.[].path + "\u0000"')

[ -z "$report" ] && exit 0
jq -n --arg r "$report" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$r}}'
