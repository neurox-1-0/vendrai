#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

usage() {
  cat <<'EOF'
Usage: ./scripts/stack.sh <command>

Commands:
  product-up       Start the complete product workflow runtime.
  product-down     Stop the product runtime without deleting volumes.
  operations-up    Start product runtime plus telemetry and WAL backup.
  operations-down  Stop the operations runtime without deleting volumes.
  status           Show current NeuroX containers.
EOF
}

warn_low_disk() {
  available_kb="$(df -Pk "${project_root}" | awk 'NR == 2 { print $4 }')"
  if (( available_kb < 15728640 )); then
    available_gb=$(( available_kb / 1048576 ))
    printf 'Warning: only about %s GB is free. The OCR/retrieval build may exhaust disk space.\n' "${available_gb}" >&2
    printf 'No Docker data will be deleted automatically.\n' >&2
  fi
}

case "${1:-}" in
  product-up)
    warn_low_disk
    docker compose --profile acceptance up --build --detach
    ;;
  product-down)
    docker compose down
    ;;
  operations-up)
    docker compose \
      -f docker-compose.yml \
      -f docker-compose.operations.yml \
      --profile acceptance \
      --profile operations \
      up --build --detach
    ;;
  operations-down)
    docker compose \
      -f docker-compose.yml \
      -f docker-compose.operations.yml \
      --profile operations \
      down
    ;;
  status)
    docker compose ps
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
