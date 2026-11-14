#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$root"

name="fewia-gate-pg-$$"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])' 2>/dev/null)"; then
  printf '%s\n' 'Database port allocation failed.' >&2
  exit 1
fi
url="postgresql+psycopg://fewia:fewia@127.0.0.1:${port}/fewia_eval"

if ! docker run -d --name "$name" \
  -e POSTGRES_USER=fewia -e POSTGRES_PASSWORD=fewia -e POSTGRES_DB=fewia_eval \
  -p "127.0.0.1:${port}:5432" postgres:16 >/dev/null 2>&1; then
  printf '%s\n' 'Database container startup failed.' >&2
  exit 1
fi

for ((attempt = 0; attempt < 30; attempt++)); do
  if docker exec "$name" pg_isready -h 127.0.0.1 -p 5432 -U fewia -d fewia_eval \
    >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! docker exec "$name" pg_isready -h 127.0.0.1 -p 5432 -U fewia -d fewia_eval \
  >/dev/null 2>&1; then
  printf '%s\n' 'Database readiness failed.' >&2
  exit 1
fi

export DATABASE_URL="$url"
export FEWIA_JOB_TEST_DATABASE_URL="$url"
export FEWIA_EVALUATION_DATABASE_URL="$url"
export FEWIA_REQUIRE_DB=1

(cd backend && uv run alembic upgrade head && uv run alembic check)
uv run --project backend python -m dev_supervisor.gates --cwd "$root" "$@"
