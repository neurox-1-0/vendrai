#!/usr/bin/env bash
# Execute the backup/restore runbook and measure what it actually costs.
#
# A runbook that has never been executed is a hypothesis. This turns
# docs/backup-restore-runbook.md into something that either works or fails
# loudly, and reports the RPO and RTO it measured rather than the ones the
# document hopes for.
#
# Restores into a throwaway volume and container. The live postgres_data volume
# is never touched - a restore overwrites database files, and a drill that can
# destroy production data will not be run often enough to be useful.
#
# See plans/08-phase-7-hardening.md item 7.5.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

DRILL_VOLUME="neurox_restore_drill_$(date +%s)"
DRILL_CONTAINER="neurox-restore-drill-$$"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.operations.yml --profile operations)

cleanup() {
  docker rm --force "${DRILL_CONTAINER}" > /dev/null 2>&1 || true
  if [[ "${KEEP_VOLUME:-}" != "1" ]]; then
    docker volume rm "${DRILL_VOLUME}" > /dev/null 2>&1 || true
  else
    printf 'Kept drill volume: %s\n' "${DRILL_VOLUME}"
  fi
}
trap cleanup EXIT

fail() {
  printf '\033[31mDrill failed:\033[0m %s\n' "$1" >&2
  exit 1
}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# --- Preconditions ----------------------------------------------------------

step "Checking the operations profile is running"
if ! "${COMPOSE[@]}" ps --status running --format '{{.Service}}' | grep -qx postgres; then
  fail "PostgreSQL is not running under the operations profile.
       Start it first: ./scripts/stack.sh operations-up"
fi

step "Verifying the backup repository"
"${COMPOSE[@]}" exec -T postgres pgbackrest --stanza=neurox check \
  || fail "pgbackrest check failed; there is no verified backup to restore from."

# --- Establish a recovery point --------------------------------------------

step "Recording a recovery marker"
# A row written now, then restored, is the only honest proof that the restore
# recovered recent data rather than an old backup that happened to load.
marker="drill-$(date -u +%Y%m%dT%H%M%SZ)"
marker_written_at="$(date -u +%s)"
"${COMPOSE[@]}" exec -T postgres psql -U neurox_migration -d neurox -c \
  "CREATE TABLE IF NOT EXISTS restore_drill_markers (
     marker text PRIMARY KEY, written_at timestamptz NOT NULL DEFAULT now());
   INSERT INTO restore_drill_markers (marker) VALUES ('${marker}');" \
  > /dev/null || fail "could not write the recovery marker"

step "Forcing a WAL switch so the marker reaches the archive"
"${COMPOSE[@]}" exec -T postgres psql -U neurox_migration -d neurox -c \
  "SELECT pg_switch_wal()" > /dev/null

step "Taking a differential backup"
"${COMPOSE[@]}" exec -T postgres neurox-backup diff \
  || fail "the differential backup failed"

# --- Restore into isolation -------------------------------------------------

restore_started_at="$(date -u +%s)"

step "Creating an isolated volume and container"
docker volume create "${DRILL_VOLUME}" > /dev/null
network="$(docker inspect --format '{{range $key, $_ := .NetworkSettings.Networks}}{{$key}} {{end}}' \
  "$("${COMPOSE[@]}" ps --format '{{.Name}}' postgres | head -n 1)" | awk '{print $1}')"

docker run --detach --name "${DRILL_CONTAINER}" \
  --network "${network}" \
  --env-file .env \
  --env POSTGRES_DB=neurox \
  --env POSTGRES_USER=neurox_migration \
  --volume "${DRILL_VOLUME}:/var/lib/postgresql/data" \
  --entrypoint sleep \
  neurox-postgres:local infinity > /dev/null

step "Restoring from the backup repository"
docker exec "${DRILL_CONTAINER}" bash -lc '
  set -euo pipefail
  rm -rf /var/lib/postgresql/data/*
  pgbackrest --stanza=neurox --delta restore
' || fail "pgbackrest restore failed"

step "Starting the restored database"
docker exec --detach --user postgres "${DRILL_CONTAINER}" \
  bash -lc 'pg_ctl -D /var/lib/postgresql/data -w -t 300 start'

for attempt in $(seq 1 60); do
  if docker exec "${DRILL_CONTAINER}" pg_isready -U neurox_migration -d neurox > /dev/null 2>&1; then
    break
  fi
  if (( attempt == 60 )); then
    fail "the restored database never accepted connections"
  fi
  sleep 2
done

restore_completed_at="$(date -u +%s)"

# --- Verify the restore is usable, not merely running -----------------------

step "Verifying the schema revision"
revision="$(docker exec "${DRILL_CONTAINER}" psql -U neurox_migration -d neurox -tAc \
  'SELECT version_num FROM alembic_version')"
[[ -n "${revision}" ]] || fail "the restored database has no Alembic revision"
printf '  Alembic revision: %s\n' "${revision}"

step "Verifying the recovery marker survived"
found="$(docker exec "${DRILL_CONTAINER}" psql -U neurox_migration -d neurox -tAc \
  "SELECT marker FROM restore_drill_markers WHERE marker = '${marker}'" || true)"
if [[ "${found}" != "${marker}" ]]; then
  fail "the marker written before the backup is not present after the restore.
       The restore succeeded but recovered stale data - the measured RPO is
       worse than this drill can express."
fi

step "Verifying tenant and audit counts"
docker exec "${DRILL_CONTAINER}" psql -U neurox_migration -d neurox -c \
  "SELECT
     (SELECT count(*) FROM tenants) AS tenants,
     (SELECT count(*) FROM cases) AS cases,
     (SELECT count(*) FROM audit_logs) AS audit_entries;"

step "Verifying the audit hash chain"
# An unverifiable chain provides no integrity guarantee, and a restore is
# exactly when you need to know the chain came back intact.
"${COMPOSE[@]}" exec -T api python - <<'PYTHON' || fail "audit chain verification failed"
import asyncio, os, sys

async def main() -> int:
    import psycopg
    from app.domain.audit_integrity import verify_chain

    class Row:
        def __init__(self, **fields): self.__dict__.update(fields)

    url = os.environ["DRILL_DATABASE_URL"]
    async with await psycopg.AsyncConnection.connect(url) as connection:
        rows = await connection.execute(
            "SELECT audit_log_id, tenant_id, case_id, actor_type, actor_id, "
            "action, resource_type, resource_id, metadata, previous_hash, "
            "record_hash FROM audit_logs ORDER BY tenant_id, created_at, audit_log_id"
        )
        records = [
            Row(
                audit_log_id=row[0], tenant_id=row[1], case_id=row[2],
                actor_type=row[3], actor_id=row[4], action=row[5],
                resource_type=row[6], resource_id=row[7], metadata_json=row[8],
                previous_hash=row[9], record_hash=row[10],
            )
            for row in await rows.fetchall()
        ]
    result = verify_chain(records)
    print(f"  Audit chain: {result.verified_count} records, "
          f"{'intact' if result.intact else 'BROKEN'}")
    for item in result.breaks[:5]:
        print(f"    {item.kind} at {item.audit_log_id}: {item.detail}")
    return 0 if result.intact else 1

sys.exit(asyncio.run(main()))
PYTHON

# --- Report measured numbers, not target numbers ----------------------------

rto_seconds=$(( restore_completed_at - restore_started_at ))
rpo_seconds=$(( restore_started_at - marker_written_at ))

printf '\n\033[1mMeasured recovery figures\033[0m\n'
printf '  RTO (restore to accepting connections)  %d min %d s\n' \
  $(( rto_seconds / 60 )) $(( rto_seconds % 60 ))
printf '  RPO (marker age at restore start)       %d min %d s\n' \
  $(( rpo_seconds / 60 )) $(( rpo_seconds % 60 ))
printf '\nThese are measured, not targets. Record them in\n'
printf 'docs/backup-restore-runbook.md and correct the runbook wherever\n'
printf 'reality differed from what it describes.\n'
