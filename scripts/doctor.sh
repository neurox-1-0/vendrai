#!/usr/bin/env bash
# Three-tier health report for a running stack.
#
# 'docker compose ps' answers only the first question. Containers can all be
# Up (healthy) while the product cannot serve a single business scenario,
# because the vendor master, invoice history, policies, and sanctions data are
# never loaded. Reporting those as separate tiers makes that state visible and
# measurable instead of a surprise at demo time.
#
#   Tier 1  Liveness           - processes are running, one-shot jobs exited 0
#   Tier 2  Readiness          - dependencies answer correctly
#   Tier 3  Business-readiness - the data a scenario needs is actually present
#
# See plans/01-phase-0-startability.md item 0.5.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

tier1_failures=0
tier2_failures=0
tier3_failures=0
current_tier=1

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
skip() { printf '  \033[90mSKIP\033[0m  %s\n' "$1"; }
fail() {
  printf '  \033[31mFAIL\033[0m  %s\n' "$1"
  shift
  while (( $# > 0 )); do
    printf '        %s\n' "$1"
    shift
  done
  case "${current_tier}" in
    1) tier1_failures=$((tier1_failures + 1)) ;;
    2) tier2_failures=$((tier2_failures + 1)) ;;
    3) tier3_failures=$((tier3_failures + 1)) ;;
  esac
}

heading() {
  current_tier="$1"
  printf '\n\033[1mTier %s - %s\033[0m\n' "$1" "$2"
}

compose() { docker compose --profile acceptance "$@"; }

# Run a command inside a service container. Used for every dependency probe so
# the check exercises the same network path the application does - a probe from
# the host would pass against services the app cannot actually reach, which is
# exactly how the MinIO network defect (D-005) stayed hidden.
in_api() { compose exec -T api "$@" 2> /dev/null; }

# --- Tier 1: liveness -------------------------------------------------------

# Long-running services. Each must be Up.
declare -a LONG_RUNNING=(
  postgres rabbitmq redis qdrant minio clamav keycloak opa mailpit
  api outbox-relay document-worker agent-worker invoice-worker
  retrieval-api retrieval-worker notification-worker alert-worker
  sanctions-worker erp-worker mock-erp web
)

# One-shot jobs. Each must have exited 0.
declare -a ONE_SHOT=(migrate seed minio-init keycloak-bootstrap)

container_state() {
  compose ps --all --format '{{.Service}}\t{{.State}}\t{{.ExitCode}}' 2> /dev/null \
    | awk -v s="$1" -F'\t' '$1 == s { print $2 "\t" $3; exit }'
}

check_long_running() {
  local service state row down=()
  for service in "${LONG_RUNNING[@]}"; do
    row="$(container_state "${service}")"
    state="${row%%$'\t'*}"
    if [[ "${state}" != "running" ]]; then
      down+=("${service}(${state:-absent})")
    fi
  done
  if (( ${#down[@]} > 0 )); then
    fail "${#down[@]} service(s) not running: ${down[*]}" \
      "Inspect: docker compose logs --tail 100 ${down[0]%%(*}"
    return
  fi
  pass "All ${#LONG_RUNNING[@]} long-running services are up"
}

check_one_shot() {
  local job row state code failed=()
  for job in "${ONE_SHOT[@]}"; do
    row="$(container_state "${job}")"
    state="${row%%$'\t'*}"
    code="${row##*$'\t'}"
    if [[ -z "${state}" ]]; then
      failed+=("${job}(never ran)")
    elif [[ "${state}" != "exited" ]]; then
      failed+=("${job}(${state})")
    elif [[ "${code}" != "0" ]]; then
      failed+=("${job}(exit ${code})")
    fi
  done
  if (( ${#failed[@]} > 0 )); then
    fail "${#failed[@]} one-shot job(s) did not complete: ${failed[*]}" \
      "Inspect: docker compose logs ${failed[0]%%(*}"
    return
  fi
  pass "All one-shot jobs exited 0: ${ONE_SHOT[*]}"
}

check_restart_loops() {
  local looping
  looping="$(
    docker ps --filter 'name=neurox-' --format '{{.Names}}\t{{.Status}}' 2> /dev/null \
      | awk -F'\t' '$2 ~ /Restarting/ { printf "%s ", $1 }'
  )"
  if [[ -n "${looping}" ]]; then
    fail "Container(s) in a restart loop: ${looping}" \
      "A crash loop usually means a missing dependency or a bad env value." \
      "Inspect: docker compose logs --tail 50 <service>"
    return
  fi
  pass "No container is restart-looping"
}

# --- Tier 2: readiness ------------------------------------------------------

check_api_health() {
  local endpoint status
  for endpoint in live ready; do
    status="$(in_api python -c "
import json, urllib.request
with urllib.request.urlopen('http://localhost:8000/health/${endpoint}', timeout=5) as response:
    print(json.load(response).get('status', 'unknown'))
" || true)"
    status="${status//$'\r'/}"
    if [[ "${status}" == "healthy" ]]; then
      pass "API /health/${endpoint} healthy"
    else
      fail "API /health/${endpoint} reported '${status:-unreachable}'" \
        "Inspect: docker compose logs --tail 50 api"
    fi
  done
}

check_rabbitmq() {
  local queues
  # NeuroX never uses the default "/" vhost (see RABBITMQ_DEFAULT_VHOST in
  # docker-compose.yml) - list_queues defaults to "/" unless told otherwise,
  # so omitting --vhost here always reports zero queues on a perfectly
  # healthy broker.
  queues="$(compose exec -T rabbitmq rabbitmqctl list_queues --vhost neurox --quiet --no-table-headers name 2> /dev/null | tr -d '\r' | grep -c . || true)"
  if [[ -z "${queues}" || "${queues}" == "0" ]]; then
    fail "RabbitMQ has no declared queues" \
      "Workers declare queues on connect; if this is empty they never connected." \
      "Inspect: docker compose logs --tail 50 agent-worker"
    return
  fi
  pass "RabbitMQ has ${queues} declared queue(s)"
}

check_minio_buckets() {
  local missing=() bucket
  for bucket in neurox-documents neurox-quarantine; do
    if ! in_api python -c "
import os, sys, urllib.request
url = os.environ['S3_ENDPOINT_URL'] + '/${bucket}'
try:
    urllib.request.urlopen(url, timeout=5)
except urllib.error.HTTPError as error:
    # 403 means the bucket exists and refuses anonymous listing, which is the
    # configured state. 404 means it does not exist.
    sys.exit(0 if error.code == 403 else 1)
except Exception:
    sys.exit(1)
" > /dev/null 2>&1; then
      missing+=("${bucket}")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    fail "MinIO bucket(s) missing or unreachable: ${missing[*]}" \
      "Re-run the initialiser: docker compose up minio-init"
    return
  fi
  pass "MinIO buckets present: neurox-documents, neurox-quarantine"
}

check_qdrant() {
  if in_api python -c "
import os, urllib.request
urllib.request.urlopen(os.environ['QDRANT_URL'] + '/collections', timeout=5)
" > /dev/null 2>&1; then
    pass "Qdrant reachable"
    return
  fi
  fail "Qdrant is not reachable from the API" \
    "Inspect: docker compose logs --tail 50 qdrant"
}

check_keycloak_realm() {
  if in_api python -c "
import json, urllib.request
url = 'http://keycloak:8080/realms/neurox/.well-known/openid-configuration'
with urllib.request.urlopen(url, timeout=5) as response:
    json.load(response)['issuer']
" > /dev/null 2>&1; then
    pass "Keycloak realm 'neurox' resolves"
    return
  fi
  fail "Keycloak realm 'neurox' does not resolve" \
    "The realm import may have failed. Inspect: docker compose logs --tail 50 keycloak"
}

check_opa() {
  if in_api python -c "
import json, os, urllib.request
body = json.dumps({'input': {}}).encode()
request = urllib.request.Request(
    os.environ['OPA_URL'] + '/v1/data',
    data=body,
    headers={'Content-Type': 'application/json'},
)
with urllib.request.urlopen(request, timeout=5) as response:
    json.load(response)
" > /dev/null 2>&1; then
    pass "OPA answers policy queries"
    return
  fi
  fail "OPA is not answering" \
    "Inspect: docker compose logs --tail 50 opa"
}

check_retrieval_api() {
  if in_api python -c "
import os, urllib.request
urllib.request.urlopen(os.environ['RETRIEVAL_URL'] + '/health', timeout=10)
" > /dev/null 2>&1; then
    pass "Retrieval API healthy"
    return
  fi
  fail "Retrieval API is not healthy" \
    "First start downloads the embedding model and can take several minutes." \
    "Inspect: docker compose logs --tail 50 retrieval-api"
}

check_mock_erp() {
  if in_api python -c "
import os, urllib.request
urllib.request.urlopen(os.environ['MOCK_ERP_URL'] + '/health', timeout=5)
" > /dev/null 2>&1; then
    pass "Mock ERP healthy"
    return
  fi
  fail "Mock ERP is not healthy" "Inspect: docker compose logs --tail 50 mock-erp"
}

# --- Tier 3: business-readiness ---------------------------------------------

# Delegated wholesale to the bootstrap's own checker so the two cannot drift.
# The bootstrap decides what "business-ready" means; doctor only reports it.
check_business_readiness() {
  local output exit_code=0
  output="$(compose exec -T api python -m scripts.bootstrap --check 2>&1)" || exit_code=$?
  if (( exit_code == 0 )); then
    printf '%s\n' "${output}" | sed 's/^/  /'
    pass "Business-ready"
    return
  fi
  printf '%s\n' "${output}" | sed 's/^/  /'
  fail "Not business-ready" \
    "Load reference data, policies, and sanctions: ./scripts/stack.sh bootstrap"
}

# --- Entry point ------------------------------------------------------------

main() {
  if ! docker info > /dev/null 2>&1; then
    printf 'Docker daemon is not reachable. Start Docker Desktop.\n' >&2
    exit 1
  fi

  printf '\033[1mNeuroX doctor\033[0m\n'

  heading 1 "Liveness"
  check_long_running
  check_one_shot
  check_restart_loops

  heading 2 "Readiness"
  if (( tier1_failures > 0 )); then
    skip "Readiness probes skipped - fix tier 1 first"
  else
    check_api_health
    check_rabbitmq
    check_minio_buckets
    check_qdrant
    check_keycloak_realm
    check_opa
    check_retrieval_api
    check_mock_erp
  fi

  heading 3 "Business-readiness"
  if (( tier1_failures > 0 || tier2_failures > 0 )); then
    skip "Business-readiness skipped - fix tiers 1 and 2 first"
  else
    check_business_readiness
  fi

  printf '\n\033[1mSummary\033[0m\n'
  summarise 1 "Liveness" "${tier1_failures}"
  summarise 2 "Readiness" "${tier2_failures}"
  summarise 3 "Business-readiness" "${tier3_failures}"

  if (( tier1_failures > 0 || tier2_failures > 0 )); then
    exit 1
  fi
  if (( tier3_failures > 0 )); then
    # A distinct code so CI can require tiers 1-2 while a not-yet-bootstrapped
    # stack is still a recognisable, expected state.
    exit 3
  fi
}

summarise() {
  if (( $3 == 0 )); then
    printf '  \033[32mTier %s %s: green\033[0m\n' "$1" "$2"
  else
    printf '  \033[31mTier %s %s: %d failure(s)\033[0m\n' "$1" "$2" "$3"
  fi
}

main "$@"
