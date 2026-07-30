#!/usr/bin/env bash
# Preconditions for starting the stack.
#
# Every check here exists because it failed silently once. Docker reports a
# port conflict as a bind error several minutes into a build; a missing .env
# key surfaces as a compose variable error with no hint of which key; a
# Postgres password change against an existing volume looks like an
# authentication bug in the application. Catching these at the boundary, with
# the fix named in the message, is the whole point.
#
# See plans/01-phase-0-startability.md item 0.4.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

failures=0
warnings=0

# Ports the stack publishes on the host. Keep in sync with docker-compose.yml
# and docker-compose.operations.yml.
declare -a PUBLISHED_PORTS=(3000 8000 8080 8025 9000 9001)

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; warnings=$((warnings + 1)); }
fail() {
  printf '  \033[31mFAIL\033[0m  %s\n' "$1"
  shift
  while (( $# > 0 )); do
    printf '        %s\n' "$1"
    shift
  done
  failures=$((failures + 1))
}

# --- Docker daemon ----------------------------------------------------------

check_docker() {
  if ! command -v docker > /dev/null 2>&1; then
    fail "Docker CLI not found on PATH" \
      "Install Docker Desktop: https://www.docker.com/products/docker-desktop"
    return
  fi
  if ! docker info > /dev/null 2>&1; then
    fail "Docker daemon is not reachable" \
      "Start Docker Desktop and wait for the whale icon to stop animating."
    return
  fi
  pass "Docker daemon reachable"
}

check_compose() {
  local version
  if ! version="$(docker compose version --short 2> /dev/null)"; then
    fail "Docker Compose v2 not available" \
      "'docker compose' (with a space) is required; 'docker-compose' v1 is not supported." \
      "Update Docker Desktop, or install the compose plugin."
    return
  fi
  case "${version}" in
    2.*|v2.*|[3-9].*)
      pass "Docker Compose v${version#v}"
      ;;
    *)
      fail "Docker Compose ${version} is too old" "Compose v2 or newer is required."
      ;;
  esac
}

# --- Host resources ---------------------------------------------------------

# A clean build pulls PyTorch, Docling models, and OCR data. 25 GB is the
# measured floor; below that the build fails partway through with a confusing
# pip or layer-write error.
readonly REQUIRED_DISK_GB=25
readonly REQUIRED_MEMORY_GB=8

check_disk() {
  local available_kb available_gb
  available_kb="$(df -Pk "${project_root}" | awk 'NR == 2 { print $4 }')"
  available_gb=$(( available_kb / 1048576 ))
  if (( available_gb < REQUIRED_DISK_GB )); then
    fail "Only ${available_gb} GB free on the project volume (need ${REQUIRED_DISK_GB} GB for a clean build)" \
      "Free space, or reclaim Docker's: docker system prune -a --volumes" \
      "Note that prune is destructive - it deletes unused images and volumes."
    return
  fi
  pass "Disk headroom ${available_gb} GB (need ${REQUIRED_DISK_GB} GB)"
}

check_memory() {
  local total_bytes total_gb
  total_bytes="$(docker info --format '{{.MemTotal}}' 2> /dev/null || echo 0)"
  if [[ "${total_bytes}" == "0" || -z "${total_bytes}" ]]; then
    warn "Could not read the memory assigned to Docker; skipping the check"
    return
  fi
  total_gb=$(( total_bytes / 1073741824 ))
  if (( total_gb < REQUIRED_MEMORY_GB )); then
    fail "Docker has ${total_gb} GB of memory (need ${REQUIRED_MEMORY_GB} GB)" \
      "Docker Desktop -> Settings -> Resources -> Memory." \
      "On WSL2, set memory= in %USERPROFILE%\\.wslconfig and run 'wsl --shutdown'."
    return
  fi
  pass "Docker memory ${total_gb} GB (need ${REQUIRED_MEMORY_GB} GB)"
}

# --- Ports ------------------------------------------------------------------

# Returns the name of the container publishing the given port, if any.
port_holder_container() {
  docker ps --filter "publish=$1" --format '{{.Names}}' 2> /dev/null | head -n 1
}

# Returns a "pid/name" description of the host process listening on the port.
port_holder_process() {
  local port="$1"
  if command -v ss > /dev/null 2>&1; then
    ss -ltnp 2> /dev/null | awk -v p=":${port}$" '$4 ~ p { print $NF; exit }'
    return
  fi
  if command -v netstat > /dev/null 2>&1; then
    # Windows netstat reports the owning PID in the last column.
    netstat -ano 2> /dev/null \
      | awk -v p=":${port}$" '$1 ~ /^TCP/ && $4 ~ p && $5 == "LISTENING" { print "pid " $6; exit }'
  fi
}

port_is_free() {
  local port="$1"
  if command -v ss > /dev/null 2>&1; then
    ! ss -ltn 2> /dev/null | awk -v p=":${port}$" '$4 ~ p { found = 1 } END { exit !found }'
    return
  fi
  if command -v netstat > /dev/null 2>&1; then
    ! netstat -an 2> /dev/null \
      | awk -v p=":${port}$" '$4 ~ p && $NF == "LISTENING" { found = 1 } END { exit !found }'
    return
  fi
  return 0
}

# Ports already published by *our own* stack are not a conflict - a second
# product-up over a running stack is a supported operation.
port_held_by_our_stack() {
  local holder="$1"
  [[ "${holder}" == neurox-* ]]
}

check_ports() {
  local port holder process conflicts=0
  for port in "${PUBLISHED_PORTS[@]}"; do
    if port_is_free "${port}"; then
      continue
    fi
    holder="$(port_holder_container "${port}")"
    if [[ -n "${holder}" ]] && port_held_by_our_stack "${holder}"; then
      continue
    fi
    conflicts=$((conflicts + 1))
    if [[ -n "${holder}" ]]; then
      fail "Port ${port} is published by container '${holder}'" \
        "Stop it: docker stop ${holder}"
    else
      process="$(port_holder_process "${port}")"
      fail "Port ${port} is in use by ${process:-an unidentified process}" \
        "Stop whatever is listening on ${port}, or change the host port in docker-compose.yml."
    fi
  done
  if (( conflicts == 0 )); then
    pass "Published ports free: ${PUBLISHED_PORTS[*]}"
  fi
}

# --- Environment ------------------------------------------------------------

# Every ${VAR:?} in the compose files is a hard requirement. Deriving the list
# from the files themselves means it cannot drift.
required_env_keys() {
  local -a files=(docker-compose.yml)
  [[ -f docker-compose.operations.yml ]] && files+=(docker-compose.operations.yml)
  grep -hEo '\$\{[A-Z0-9_]+:\?' "${files[@]}" \
    | sed -E 's/^\$\{//; s/:\?$//' \
    | sort -u
}

check_env() {
  if [[ ! -f .env ]]; then
    fail ".env does not exist" \
      "Create it: ./scripts/bootstrap-local-env.sh"
    return
  fi

  local -a missing=() placeholder=()
  local key value
  while IFS= read -r key; do
    value="$(grep -E "^${key}=" .env | tail -n 1 || true)"
    value="${value#*=}"
    if [[ -z "${value}" ]]; then
      missing+=("${key}")
    elif [[ "${value}" == CHANGE_ME* ]]; then
      placeholder+=("${key}")
    fi
  done < <(required_env_keys)

  if (( ${#missing[@]} > 0 )); then
    fail ".env is missing ${#missing[@]} required key(s): ${missing[*]}" \
      "Fill them in, or regenerate: ./scripts/bootstrap-local-env.sh"
  fi
  if (( ${#placeholder[@]} > 0 )); then
    fail ".env still holds CHANGE_ME placeholders: ${placeholder[*]}" \
      "Replace them, or regenerate: ./scripts/bootstrap-local-env.sh"
  fi
  if (( ${#missing[@]} == 0 && ${#placeholder[@]} == 0 )); then
    pass ".env resolves every required compose variable"
  fi

  # An LLM key is optional for startup but every agent workflow needs it, so a
  # missing one should be known now rather than at the first case submission.
  if ! grep -Eq '^GEMINI_API_KEY=.+' .env; then
    warn "GEMINI_API_KEY is empty - agent workflows will fall back to deterministic checks only"
  fi
}

# --- Postgres volume consistency --------------------------------------------

# The Postgres image only applies POSTGRES_PASSWORD when it initialises an
# empty data directory. Changing NEUROX_MIGRATION_DB_PASSWORD in .env after
# the volume exists leaves the old password in place, and every service then
# fails to authenticate - which reads as an application bug.
check_postgres_volume() {
  local volume="neurox_postgres_data"
  if ! docker volume inspect "${volume}" > /dev/null 2>&1; then
    pass "No existing Postgres volume (a fresh one will be initialised)"
    return
  fi

  local password
  password="$(grep -E '^NEUROX_MIGRATION_DB_PASSWORD=' .env | tail -n 1 || true)"
  password="${password#*=}"
  if [[ -z "${password}" ]]; then
    return  # already reported by check_env
  fi

  local container
  container="$(docker ps --filter "name=neurox-postgres" --format '{{.Names}}' | head -n 1)"
  if [[ -z "${container}" ]]; then
    warn "Postgres volume '${volume}' exists but the container is not running; password consistency unverified"
    return
  fi

  if docker exec -e PGPASSWORD="${password}" "${container}" \
      psql -U neurox_migration -d neurox -c 'SELECT 1' > /dev/null 2>&1; then
    pass "Postgres volume password matches .env"
    return
  fi

  fail "Postgres rejects the NEUROX_MIGRATION_DB_PASSWORD in .env" \
    "The volume was initialised with a different password; Postgres only reads it on first init." \
    "Restore the original password in .env, or reset the volume (DESTRUCTIVE - deletes all data):" \
    "  docker compose down && docker volume rm ${volume}"
}

# --- Entry point ------------------------------------------------------------

main() {
  printf 'Preflight checks\n'
  check_docker
  # Everything below needs a working daemon; bail early rather than emitting a
  # cascade of failures that all have the same cause.
  if (( failures > 0 )); then
    printf '\n\033[31mPreflight failed\033[0m (%d problem(s)). Nothing was started.\n' "${failures}" >&2
    exit 1
  fi
  check_compose
  check_disk
  check_memory
  check_ports
  check_env
  check_postgres_volume

  printf '\n'
  if (( failures > 0 )); then
    printf '\033[31mPreflight failed\033[0m (%d problem(s), %d warning(s)). Nothing was started.\n' \
      "${failures}" "${warnings}" >&2
    exit 1
  fi
  if (( warnings > 0 )); then
    printf '\033[33mPreflight passed with %d warning(s).\033[0m\n' "${warnings}"
  else
    printf '\033[32mPreflight passed.\033[0m\n'
  fi
}

main "$@"
