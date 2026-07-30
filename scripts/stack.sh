#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

usage() {
  cat <<'EOF'
Usage: ./scripts/stack.sh <command>

Commands:
  preflight        Check host preconditions without starting anything.
  product-up       Start the complete product workflow runtime.
  product-down     Stop the product runtime without deleting volumes.
  operations-up    Start product runtime plus telemetry and WAL backup.
  operations-down  Stop the operations runtime without deleting volumes.
  bootstrap        Load reference data, policies, and sanctions (idempotent).
  doctor           Report liveness, readiness, and business-readiness.
  status           Show current NeuroX containers.

Options:
  --skip-preflight  Start without checking host preconditions. Only useful
                    when a check is wrong; fix the check instead.

Bootstrap options are passed through, e.g.
  ./scripts/stack.sh bootstrap --allow-missing-eu-sanctions
EOF
}

run_preflight() {
  if [[ "${1:-}" == "--skip-preflight" ]]; then
    printf 'Skipping preflight checks.\n' >&2
    return 0
  fi
  "${project_root}/scripts/preflight.sh"
}

command_name="${1:-}"
shift || true

case "${command_name}" in
  preflight)
    exec "${project_root}/scripts/preflight.sh" "$@"
    ;;
  product-up)
    run_preflight "${1:-}"
    docker compose --profile acceptance up --build --detach
    printf '\nStack started. Check it with: ./scripts/stack.sh doctor\n'
    ;;
  product-down)
    docker compose --profile acceptance down
    ;;
  operations-up)
    run_preflight "${1:-}"
    docker compose \
      -f docker-compose.yml \
      -f docker-compose.operations.yml \
      --profile acceptance \
      --profile operations \
      up --build --detach
    printf '\nStack started. Check it with: ./scripts/stack.sh doctor\n'
    ;;
  operations-down)
    docker compose \
      -f docker-compose.yml \
      -f docker-compose.operations.yml \
      --profile operations \
      down
    ;;
  bootstrap)
    docker compose --profile acceptance exec -T api python -m scripts.bootstrap "$@"
    ;;
  doctor)
    exec "${project_root}/scripts/doctor.sh" "$@"
    ;;
  status)
    docker compose --profile acceptance ps
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
