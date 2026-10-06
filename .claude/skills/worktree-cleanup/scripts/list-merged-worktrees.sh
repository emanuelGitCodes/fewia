#!/usr/bin/env bash
# Print every worktree whose branch is merged into main, one per line:
# <path>\t<branch>\t<state>. State is "clean" or "dirty".
# Skips the main checkout, the current directory, and a detached HEAD.
# Pass --include-dirty to list worktrees with uncommitted changes too.
set -euo pipefail

include_dirty=0
[ "${1:-}" = "--include-dirty" ] && include_dirty=1

main_path="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
here="$(pwd -P)"

# Porcelain output is one block per worktree, blank-line separated. A
# detached worktree has no `branch` line and prints nothing.
git worktree list --porcelain | awk '
  /^worktree / { path = substr($0, 10); branch = "" }
  /^branch /   { branch = substr($0, 19) }
  /^$/         { if (path != "" && branch != "") print path "\t" branch; path = ""; branch = "" }
  END          { if (path != "" && branch != "") print path "\t" branch }
' | while IFS=$'\t' read -r path branch; do
  [ -z "$path" ] && continue
  [ "$path" = "$main_path" ] && continue
  [ "$path" = "$here" ] && continue
  [ "$branch" = "main" ] && continue
  git merge-base --is-ancestor "$branch" main 2>/dev/null || continue
  state="clean"
  if [ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]; then
    state="dirty"
    [ "$include_dirty" -eq 1 ] || continue
  fi
  printf '%s\t%s\t%s\n' "$path" "$branch" "$state"
done
