#!/usr/bin/env bash
# SessionStart hook. Prints the branch, the open loop ledgers, and the
# worktree count as context for the session.
set -euo pipefail

cat >/dev/null
root="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$root"

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
worktrees="$(git worktree list 2>/dev/null | wc -l | tr -d ' ')"
ledgers=""
for f in .claude/loop/*.md; do
  [ -f "$f" ] || continue
  slug="$(basename "$f" .md)"
  open="$(grep -Ec '\| *(queued|released|in_progress|review|repair|blocked) *\|' "$f" || true)"
  [ "$open" -gt 0 ] && ledgers="$ledgers $slug($open open)"
done

msg="FEWIA session. Branch: $branch. Worktrees: $worktrees."
[ -n "$ledgers" ] && msg="$msg Loop ledgers with open items:$ledgers. Resume with /feature-loop resume <slug>."
msg="$msg Hooks are active: coordinator code edits are denied, external writes need the user, PR size is checked. See .claude/README.md."

jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$m}}'
