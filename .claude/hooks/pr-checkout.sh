#!/usr/bin/env bash
# Shared by the pull request hooks. Source it after reading `$cmd`.
# Sets `dir` to the checkout a leading `cd <dir> &&` names, else the
# project root. Sets `base` to the `--base` ref, else `origin/main`.
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
if [[ "$cmd" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:];&]+) ]]; then
  dir="${BASH_REMATCH[1]/#\~/$HOME}"
  [[ "$dir" = /* ]] || dir="${CLAUDE_PROJECT_DIR:-$PWD}/$dir"
fi
base="origin/main"
if [[ "$cmd" =~ --base[[:space:]=]+\"?([^[:space:]\"]+) ]]; then
  base="${BASH_REMATCH[1]}"
  if git -C "$dir" rev-parse --verify -q "origin/$base" >/dev/null 2>&1; then
    base="origin/$base"
  fi
fi
