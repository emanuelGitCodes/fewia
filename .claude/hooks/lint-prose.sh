#!/usr/bin/env bash
# PostToolUse hook for Edit and Write on Markdown files.
# Reports house-style violations back to the model. It never blocks.
set -euo pipefail

path="$(jq -r '.tool_input.file_path // empty')"
case "$path" in *.md) ;; *) exit 0 ;; esac
[ -f "$path" ] || exit 0

findings="$(grep -nE \
  -e '\b(utilize|utilise|leverage|prior to|in order to|initiate|facilitate)\b' \
  -e '\b(SHALL|REQUIRED|RECOMMENDED|OPTIONAL)\b' \
  -e '—' \
  "$path" | head -10 || true)"

[ -z "$findings" ] && exit 0
jq -n --arg f "$findings" --arg p "$path" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("house-style: review these lines in " + $p + ":\n" + $f)}}'
