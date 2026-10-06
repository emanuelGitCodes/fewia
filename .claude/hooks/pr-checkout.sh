#!/usr/bin/env bash
# Shared by the pull request hooks. Source it after reading `$cmd`.
# Sets `dir` to the checkout a leading `cd <dir> &&` names, else the
# project root. Sets `base` to `origin/<--base>`, else `origin/main`.
# A base that is not on origin does not resolve, and the caller denies.
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
if [[ "$cmd" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:];&]+) ]]; then
  dir="${BASH_REMATCH[1]/#\~/$HOME}"
  [[ "$dir" = /* ]] || dir="${CLAUDE_PROJECT_DIR:-$PWD}/$dir"
fi
base="origin/main"
if [[ "$cmd" =~ --base[[:space:]=]+\"?([^[:space:]\"]+) ]]; then
  base="origin/${BASH_REMATCH[1]#origin/}"
fi
