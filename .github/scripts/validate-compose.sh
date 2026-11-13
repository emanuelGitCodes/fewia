#!/usr/bin/env bash
set -euo pipefail

umask 077
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
fixtures="$(mktemp -d /tmp/fewia-compose.XXXXXXXX)"
cleanup() { rm -rf -- "$fixtures"; }
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
chmod 700 "$fixtures"

for file in admin-password runtime-password pairing-key kroger-client-id kroger-secret kroger-token-key; do
  printf '%s\n' 'compose-validation-only' > "$fixtures/$file"
  chmod 600 "$fixtures/$file"
done

env_file="$fixtures/compose.env"
{
  printf 'FEWIA_HOST_UID=%s\n' "$(id -u)"
  printf 'FEWIA_HOST_GID=%s\n' "$(id -g)"
  printf 'FEWIA_LOCAL_ADMIN_PASSWORD_FILE=%s/admin-password\n' "$fixtures"
  printf 'FEWIA_LOCAL_RUNTIME_PASSWORD_FILE=%s/runtime-password\n' "$fixtures"
  printf 'FEWIA_LOCAL_PAIRING_KEY_FILE=%s/pairing-key\n' "$fixtures"
  printf 'FEWIA_KROGER_CLIENT_ID_FILE=%s/kroger-client-id\n' "$fixtures"
  printf 'FEWIA_KROGER_SECRET_FILE=%s/kroger-secret\n' "$fixtures"
  printf 'FEWIA_KROGER_TOKEN_KEY_FILE=%s/kroger-token-key\n' "$fixtures"
  printf '%s\n' 'FEWIA_OPENAI_API_KEY=compose-validation-only'
} > "$env_file"
chmod 600 "$env_file"

cd "$root"
validate() {
  env -i PATH="$PATH" HOME="${HOME:-$fixtures}" \
    docker compose --env-file "$env_file" -f compose.yaml "$@" config --quiet
}
validate
validate -f compose.kroger.yaml
validate -f compose.tools.yaml
