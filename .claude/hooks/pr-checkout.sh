#!/usr/bin/env bash
# Shared by the pull request hooks. Source it after reading `$input` and
# `$cmd`. Sets `dir` to the checkout a leading `cd <dir> &&` names, else the
# `cwd` of the hook input, else the project root. Claude Code removes a
# leading `cd` to the session cwd from the command, so the input `cwd` names
# the worktree. Sets `base` to `origin/<--base>`, else `origin/main`.
# A base that is not on origin does not resolve, and the caller denies.
dir="$(jq -r '.cwd // empty' <<<"${input:-}" 2>/dev/null || true)"
[ -n "$dir" ] || dir="${CLAUDE_PROJECT_DIR:-$PWD}"
if [[ "$cmd" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:];&]+) ]]; then
  target="${BASH_REMATCH[1]/#\~/$HOME}"
  [[ "$target" = /* ]] || target="$dir/$target"
  dir="$target"
fi
base="origin/main"
if [[ "$cmd" =~ --base[[:space:]=]+\"?([^[:space:]\"]+) ]]; then
  base="origin/${BASH_REMATCH[1]#origin/}"
fi
