#!/usr/bin/env bash
# PreToolUse hook for Edit, Write, MultiEdit, and Codex apply_patch.
# Rule: `wiki/log.md` is append-only. Agents MUST NOT edit or delete an
# existing entry. An edit passes only when the new text starts with the
# old text, so every change lands after what exists.
set -euo pipefail

input="$(cat)"

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

# A Codex patch passes only when it adds lines to an existing log, or
# creates the log when no log exists.
if [ "$(jq -r '.tool_name // empty' <<<"$input")" = apply_patch ]; then
  while IFS=$'\t' read -r op removes target; do
    case "$op" in
      update) [ "$removes" = false ] && continue ;;
      add) [ -f "$target" ] || continue ;;
    esac
    deny "wiki/log.md is append-only. The patch removes, replaces, moves, or deletes log text ($op). Add lines only."
  done < <(python3 "$(dirname "$0")/edit-targets.py" <<<"$input" \
    | jq -r '.[] | select(.path | endswith("/wiki/log.md")) | [.op, .removes, .path] | @tsv')
  exit 0
fi

path="$(jq -r '.tool_input.file_path // empty' <<<"$input")"
root="${CLAUDE_PROJECT_DIR:-$PWD}"
case "$path" in /*) ;; "") exit 0 ;; *) path="$root/$path" ;; esac
case "$path" in */wiki/log.md) ;; *) exit 0 ;; esac
[ -f "$path" ] || exit 0

tool="$(jq -r '.tool_name' <<<"$input")"
case "$tool" in
  Write)
    current="$(cat "$path")"
    new="$(jq -r '.tool_input.content' <<<"$input")"
    [[ "$new" == "$current"* ]] || deny "wiki/log.md is append-only. Keep the existing text and add the new entry at the end."
    ;;
  Edit)
    old="$(jq -r '.tool_input.old_string' <<<"$input")"
    new="$(jq -r '.tool_input.new_string' <<<"$input")"
    [[ "$new" == "$old"* ]] || deny "wiki/log.md is append-only. The new text must start with the old text unchanged."
    ;;
  MultiEdit)
    n="$(jq '.tool_input.edits | length' <<<"$input")"
    for ((i = 0; i < n; i++)); do
      old="$(jq -r ".tool_input.edits[$i].old_string" <<<"$input")"
      new="$(jq -r ".tool_input.edits[$i].new_string" <<<"$input")"
      [[ "$new" == "$old"* ]] || deny "wiki/log.md is append-only. Edit $((i + 1)) changes existing text."
    done
    ;;
esac
exit 0
