#!/usr/bin/env bash
set -euo pipefail

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$NEUROX_APP_DB_PASSWORD" \
  --set=worker_password="$NEUROX_WORKER_DB_PASSWORD" \
  --set=relay_password="$NEUROX_RELAY_DB_PASSWORD" \
  --set=audit_password="$NEUROX_AUDIT_DB_PASSWORD" <<'SQL'
CREATE ROLE neurox_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
CREATE ROLE neurox_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'worker_password';
CREATE ROLE neurox_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS PASSWORD :'relay_password';
CREATE ROLE neurox_audit LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'audit_password';
GRANT CONNECT ON DATABASE neurox TO neurox_app, neurox_worker, neurox_relay, neurox_audit;
GRANT USAGE, CREATE ON SCHEMA public TO neurox_migration;
ALTER DEFAULT PRIVILEGES FOR ROLE neurox_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO neurox_app, neurox_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE neurox_migration IN SCHEMA public GRANT SELECT ON TABLES TO neurox_audit;
ALTER DEFAULT PRIVILEGES FOR ROLE neurox_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO neurox_app, neurox_worker;
SQL
