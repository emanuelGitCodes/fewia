#!/usr/bin/env bash
# PreToolUse hook for Bash.
# Deny: skipping gitleaks, deleting supervisor checkpoint dirs, force pushes,
# and pushes to main. Ask: every other external write (push, PR, merge).
# Under Codex (FEWIA_HOOK_HOST=codex), deny instead of ask.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // empty')"
[ -z "$cmd" ] && exit 0

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}
# Codex hooks cannot ask, so under Codex an external write is denied and
# the user runs it.
ask() {
  [ "${FEWIA_HOOK_HOST:-}" = codex ] && deny "$1 Codex hooks cannot ask: give the command to the user to run."
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
  exit 0
}

grep -Eq 'git\s+(commit|push)\b[^|;&]*--no-verify|SKIP=gitleaks[^|;&]*\bgit\b' <<<"$cmd" \
  && deny "AGENTS.md: agents MUST NOT skip the gitleaks hook."
grep -Eq 'rm\s+(-[a-zA-Z]+\s+)*[^ ]*\.fewia-supervisor' <<<"$cmd" \
  && deny "Never delete .fewia-supervisor-* dirs. A stale lease blocks the next writer run; clear it through dev_supervisor."
grep -Eq 'git\s+push\b.*(\s--force\b|\s-f\b|\s--force-with-lease\b)' <<<"$cmd" \
  && deny "Force push is blocked. Open a new branch or ask the user."
grep -Eq 'git\s+push\b.*(^|[[:space:]:/])main([[:space:]]|$)' <<<"$cmd" \
  && deny "AGENTS.md: agents MUST NOT push to main."
grep -Eq 'git\s+push\b|gh\s+pr\s+(create|merge|edit|close|ready)\b|gh\s+api\b.*-X\s*(POST|PATCH|PUT|DELETE)|git\s+merge\b' <<<"$cmd" \
  && ask "External write. CLAUDE.md requires user confirmation for pushes, pull requests, and merges."

exit 0
