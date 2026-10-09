#!/usr/bin/env bash
# Stop hooks record token counts without blocking the turn.
# Each event selects its transcript path and phase.
set -euo pipefail
trap 'exit 0' EXIT

input="$(cat 2>/dev/null)" || exit 0
event="$(jq -r 'if type == "object" and (.hook_event_name | type) == "string" then .hook_event_name else empty end' <<<"$input" 2>/dev/null)" || exit 0
case "$event" in
  Stop)
    path="$(jq -r 'if (.transcript_path | type) == "string" then .transcript_path else empty end' <<<"$input" 2>/dev/null)" || exit 0
    phase=coordinate
    ;;
  SubagentStop)
    path="$(jq -r 'if (.agent_transcript_path | type) == "string" then .agent_transcript_path else empty end' <<<"$input" 2>/dev/null)" || exit 0
    agent="$(jq -r 'if (.agent_type | type) == "string" and (.agent_type | length) > 0 then .agent_type else empty end' <<<"$input" 2>/dev/null)" || exit 0
    phase=junior
    ;;
  *)
    exit 0
    ;;
esac

[ -n "$path" ] && [ -f "$path" ] || exit 0
root="${CLAUDE_PROJECT_DIR:-$PWD}"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo"
args=(--cwd "$root" --claude-transcript "$path" --phase "$phase")
if [ -n "${agent:-}" ]; then
  args+=(--agent-type "$agent")
fi
PYTHONPATH="$repo" uv run --project backend python -m dev_supervisor.usage "${args[@]}" >/dev/null 2>&1 || true
