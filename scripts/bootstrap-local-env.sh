#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
example_file="${project_root}/.env.example"
env_file="${project_root}/.env"
temporary_file="$(mktemp "${project_root}/.env.generated.XXXXXX")"
trap 'rm -f "${temporary_file}"' EXIT

is_generated_secret() {
  case "$1" in
    NEUROX_*_DB_PASSWORD|RABBITMQ_PASSWORD|MINIO_*_PASSWORD|\
    PGBACKREST_REPO_CIPHER_PASS|KEYCLOAK_ADMIN_PASSWORD|\
    KEYCLOAK_E2E_USER_PASSWORD|KEYCLOAK_E2E_CLIENT_SECRET|\
    GRAFANA_ADMIN_PASSWORD|UPLOAD_TOKEN_SECRET|\
    DATA_ENCRYPTION_SECRET|BLIND_INDEX_SECRET)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

while IFS= read -r line || [[ -n "${line}" ]]; do
  if [[ ! "${line}" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]]; then
    printf '%s\n' "${line}" >> "${temporary_file}"
    continue
  fi
  key="${BASH_REMATCH[1]}"
  example_value="${BASH_REMATCH[2]}"
  existing_line=""
  if [[ -f "${env_file}" ]]; then
    existing_line="$(
      grep -E "^${key}=" "${env_file}" | tail -n 1 || true
    )"
  fi
  existing_value="${existing_line#*=}"
  if [[ -n "${existing_value}" ]]; then
    value="${existing_value}"
  elif is_generated_secret "${key}"; then
    value="$(openssl rand -hex 32)"
  else
    value="${example_value}"
  fi
  printf '%s=%s\n' "${key}" "${value}" >> "${temporary_file}"
done < "${example_file}"

chmod 600 "${temporary_file}"
mv "${temporary_file}" "${env_file}"
trap - EXIT

required_missing=()
while IFS= read -r key; do
  if ! grep -Eq "^${key}=.+" "${env_file}"; then
    required_missing+=("${key}")
  fi
done < <(
  grep -Eo '\$\{[A-Z0-9_]+:\?' "${project_root}/docker-compose.yml" \
    | sed -E 's/^\$\{//; s/:\?$//' \
    | sort -u
)

if (( ${#required_missing[@]} > 0 )); then
  printf 'Required values still missing:\n' >&2
  printf '  %s\n' "${required_missing[@]}" >&2
  exit 1
fi

printf 'Local .env is ready. Existing non-empty values were preserved.\n'
printf 'No secret values were printed. Do not commit .env.\n'
