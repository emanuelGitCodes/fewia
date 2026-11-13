#!/usr/bin/env bash
# PreToolUse hook for Bash.
# Deny: skipping gitleaks, deleting supervisor checkpoint dirs, force pushes,
# and pushes to main. Ask: every other external write (push, PR, merge).
# Codex accepts one exact push with a matching local approval record.
set -euo pipefail

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}
# Codex hooks cannot ask. The coordinator records a separately approved push.
ask() {
  [ "${FEWIA_HOOK_HOST:-}" = codex ] && deny "$1 Codex hooks cannot ask: give the command to the user to run."
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
  exit 0
}

input="$(python3 -c '
import sys
data = sys.stdin.buffer.read(1048577)
if len(data) > 1048576 or b"\0" in data:
    raise SystemExit(1)
sys.stdout.buffer.write(data)
')" || deny "Invalid hook input."
cmd="$(jq -ers '
  if length != 1 or (.[0] | type) != "object" then error("Invalid payload")
  else .[0].tool_input? as $tool |
    if $tool == null then ""
    elif ($tool | type) != "object" then error("Invalid tool input")
    else (if ($tool | has("command")) then $tool.command else "" end) end |
    if type != "string" or contains("\u0000") then error("Invalid command")
    else . end
  end
' <<<"$input")" || deny "Invalid hook input."
[ -z "$cmd" ] && exit 0

# Match simple Git global options. Shell expressions still need confirmation.
argument="([^[:space:]\"'\\\\;&|]+|\"[^\"\\\\]*\"|'[^'\\\\]*')"
git_prefix="git[[:space:]]+(((-C|-c|--git-dir|--work-tree)[[:space:]]+$argument|(-C|-c|--git-dir=|--work-tree=)$argument|--no-pager|--paginate|--bare)[[:space:]]+)*"
push="${git_prefix}push\\b"
grep -Eq "${git_prefix}(commit|push)\\b[^|;&]*--no-verify|SKIP=gitleaks[^|;&]*\\bgit\\b" <<<"$cmd" \
  && deny "AGENTS.md: agents MUST NOT skip the gitleaks hook."
grep -Eq 'rm\s+(-[a-zA-Z]+\s+)*[^ ]*\.fewia-supervisor' <<<"$cmd" \
  && deny "Never delete .fewia-supervisor-* dirs. A stale lease blocks the next writer run; clear it through dev_supervisor."
grep -Eq "${push}[^|;&]*[[:space:]](--f(o(r(c(e(-[a-z-]*)?)?)?)?)?([=[:space:]]|$)|-[[:alpha:]]*f[[:alpha:]]*([[:space:]]|$))" <<<"$cmd" \
  && deny "Force push is blocked. Open a new branch or ask the user."
grep -Eq "${push}[^|;&]*[[:space:]](--(tags|all|delete|mirror)([=[:space:]]|$)|-d([[:space:]]|$))" <<<"$cmd" \
  && deny "Broad and destructive pushes need a separate user action."
grep -Eq "${push}[^|;&]*[[:space:]:/]main([[:space:]]|$)" <<<"$cmd" \
  && deny "AGENTS.md: agents MUST NOT push to main."
if grep -Eq "${git_prefix}(push|merge)\\b|gh\\s+pr\\s+(create|merge|edit|close|ready)\\b|gh\\s+api\\b.*-X\\s*(POST|PATCH|PUT|DELETE)" <<<"$cmd"; then
  if [ "${FEWIA_HOOK_HOST:-}" = codex ] && \
    printf '%s' "$input" | python3 "$(dirname "${BASH_SOURCE[0]}")/publication-approval.py" consume 2>/dev/null; then
    exit 0
  fi
  ask "External write. CLAUDE.md requires user confirmation for pushes, pull requests, and merges."
fi

# Match simple words after an option without assuming its name or value count.
fallback_word="${argument}+"
fallback_git="(([^[:space:]\"'\\\\;&|()<>]+/)?git|\"([^\"\\\\]*/)?git\"|'([^'\\\\]*/)?git')"
fallback_prefix="(^|[[:space:];&|()<>])${fallback_git}[[:space:]]+(-${fallback_word}[[:space:]]+(${fallback_word}[[:space:]]+)*)?"
grep -Eq "${fallback_prefix}(push|merge|\"(push|merge)\"|'(push|merge)')([[:space:];&|()<>]|$)" <<<"$cmd" \
  && deny "Git push or merge with an unfamiliar prefix needs a separate user action."

exit 0
