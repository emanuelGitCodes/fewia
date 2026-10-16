#!/usr/bin/env bash
# Run dev_supervisor.gates against a throwaway PostgreSQL named fewia_eval.
# Every argument passes through to dev_supervisor.gates.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

name="fewia-gate-pg-$$"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
url="postgresql+psycopg://fewia:fewia@127.0.0.1:${port}/fewia_eval"

cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$name" \
  -e POSTGRES_USER=fewia -e POSTGRES_PASSWORD=fewia -e POSTGRES_DB=fewia_eval \
  -p "127.0.0.1:${port}:5432" postgres:16 >/dev/null

for _ in $(seq 1 30); do
  docker exec "$name" pg_isready -U fewia -d fewia_eval >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$name" pg_isready -U fewia -d fewia_eval >/dev/null

export DATABASE_URL="$url"
export FEWIA_JOB_TEST_DATABASE_URL="$url"
export FEWIA_EVALUATION_DATABASE_URL="$url"

(cd backend && uv run alembic upgrade head)
uv run --project backend python -m dev_supervisor.gates --cwd "$root" "$@"
