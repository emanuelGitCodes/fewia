#!/usr/bin/env bash
# Runs one FEWIA hook from .claude/hooks/ for Codex. .codex/hooks.json
# calls it with the hook file name. Codex does not set CLAUDE_PROJECT_DIR
# and starts a hook in the session cwd, so this wrapper sets
# CLAUDE_PROJECT_DIR to the git root and FEWIA_HOOK_HOST to codex.
set -euo pipefail

case "${1:-}" in
  ""|*/*) echo "codex-hook.sh: give one hook file name" >&2; exit 1 ;;
esac
root="$(git rev-parse --show-toplevel)"
export CLAUDE_PROJECT_DIR="$root" FEWIA_HOOK_HOST=codex
exec "$root/.claude/hooks/$1"
