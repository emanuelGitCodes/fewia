#!/usr/bin/env bash
# Stop hook. Rule: after a work item is done, append one dated entry to
# `wiki/log.md`. This hook reminds. It never blocks.
set -euo pipefail

cat >/dev/null
root="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$root"

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
[ "$branch" = "main" ] && exit 0
base="$(git merge-base main HEAD 2>/dev/null || true)"
[ -z "$base" ] && exit 0
ahead="$(git rev-list --count "$base..HEAD")"
[ "$ahead" -eq 0 ] && exit 0

# `git diff <base>` with no second ref compares the base to the working
# tree, so a committed entry and an uncommitted one both count.
git diff --name-only "$base" -- wiki/log.md | grep -q . && exit 0

jq -n --arg b "$branch" --arg n "$ahead" \
  '{systemMessage: ("Branch " + $b + " has " + $n + " commit(s) ahead of main and no wiki/log.md entry. AGENTS.md asks for one dated entry per finished work item.")}'
