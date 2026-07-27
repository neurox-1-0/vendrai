# PostgreSQL backup and restore runbook

NeuroX archives WAL continuously to the private `neurox-backups` bucket with
pgBackRest when the operations overlay is enabled. The functional product
profile intentionally starts without continuous backup so workflow
development is not blocked by optional operational infrastructure. The
operations profile sets `archive_timeout=900`, bounding normal WAL archival
lag to 15 minutes. A daily differential and weekly full backup should be
scheduled by the deployment host.

## Backup check

Run inside the release directory:

```bash
./scripts/stack.sh operations-up
docker compose -f docker-compose.yml -f docker-compose.operations.yml \
  --profile operations exec -T postgres neurox-backup full
docker compose -f docker-compose.yml -f docker-compose.operations.yml \
  --profile operations exec -T postgres pgbackrest --stanza=neurox check
docker compose -f docker-compose.yml -f docker-compose.operations.yml \
  --profile operations exec -T postgres pgbackrest --stanza=neurox info
```

Do not use the application MinIO credential for backup operations. Rotate
`MINIO_BACKUP_PASSWORD` and `PGBACKREST_REPO_CIPHER_PASS` independently.

## Restore acceptance

Restore only into a new, isolated acceptance volume. Never point a restore test
at the active `postgres_data` volume.

1. Record the target backup label and desired point-in-time.
2. Stop application writers and create a new empty PostgreSQL volume.
3. Start the NeuroX PostgreSQL image against only that new volume with the same
   backup repository secrets.
4. Run `pgbackrest --stanza=neurox --delta --type=time
   --target="<UTC timestamp>" restore` inside the isolated database container.
5. Start PostgreSQL, run `pg_isready`, and verify the Alembic revision.
6. Verify tenant counts and the complete hash chain in `audit_logs`.
7. Run API smoke tests with the restored database and rebuild Qdrant from
   published PostgreSQL policy chunks.
8. Record measured RPO and RTO. Release acceptance requires RPO at most
   15 minutes and RTO at most 2 hours.

The restore test is intentionally not automated against the main Compose volume
because restore overwrites database files.
