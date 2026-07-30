# NeuroX enterprise vendor-to-pay recovery platform

NeuroX currently contains an evidence-driven supplier-onboarding platform and a recovered invoice-exception slice. Deterministic controls own authorization, tenant isolation, sanctions/duplicate blocking, three-way matching, approvals and ERP authorization. LLM reasoning is optional, bounded and never receives raw documents or sensitive identifiers.

## Runtime boundaries

- `web`: Next.js work queues, secure intake, evidence review and notifications.
- `api`: FastAPI contracts, Keycloak/RBAC, RLS context and durable case events.
- `outbox-relay`: atomic database-to-RabbitMQ event publication.
- `document-worker`: quarantine, ClamAV, native PDF parsing, Docling/Tesseract/EasyOCR and local masking.
- `retrieval-worker` / `retrieval-api`: local dense+sparse policy index, RRF and reranking.
- `agent-worker`: validated Gemini planning, failure-isolated parallel
  duplicate/sanctions/policy investigation and durable approval interruption.
- `invoice-worker`: validated planning, parallel PO/GRN/vendor retrieval,
  deterministic matching, policy evidence and durable invoice approval.
- `alert-worker`: evaluates tenant-scoped SLA and fraud rules every 15 minutes,
  deduplicates alert instances and reuses durable notification delivery.
- `/api/v1/analytics`, `/risk-findings`, `/alert-rules` and `/alerts`: expose
  server-derived KPIs, governed metric questions, explainable active/shadow
  findings and auditable alert operations.
- `notification-worker`: independent in-app/email delivery and delayed retries.
- `erp-worker` / `mock-erp`: evidence-bound, idempotent vendor creation.
- `opa`: fail-closed authorization for every ERP write using state, evidence,
  version, segregation-of-duties and mandatory-review facts.

PostgreSQL is authoritative. RabbitMQ quorum queues carry versioned events.
Qdrant is a derived tenant-filtered policy index. Redis is limited to cache,
coordination, and an expiring PII-free live execution projection; matching
PostgreSQL steps always take precedence. Documents remain local.

The case workspace includes a persisted execution map and sanitized judge
diagnostics. The separate application copilot uses versioned procedural CAG and
authorization-filtered case context; it can navigate or spotlight the product
but has no workflow-mutation capability.

## Local setup

Requirements: Docker Compose, Node.js 22.18+ and Python 3.12+.

For complete macOS, Linux and Windows/WSL2 setup, provider choices, health
checks, synthetic browser journeys, automated tests and troubleshooting, see
[`RUN_PROJECT.md`](./RUN_PROJECT.md). To run without Docker at all (Windows),
see [Native Windows setup (no Docker)](#native-windows-setup-no-docker) below.

```bash
./scripts/bootstrap-local-env.sh
```

The bootstrap creates the ignored root `.env`, generates independent local
service secrets, preserves an existing `GEMINI_API_KEY`, and never prints
secret values. Use only synthetic business data. Invoice processing sends only
locally extracted, masked minimum context to Gemini; source documents never
leave the platform.

```bash
./scripts/stack.sh product-up
```

`product-up` is the complete functional product: both workflows, Keycloak
bootstrap, PostgreSQL, RabbitMQ, Redis, MinIO, ClamAV, Docling, Tesseract,
EasyOCR, Qdrant retrieval, OPA, Mailpit, the ERP sandbox, and the risk
sandbox. It does not omit OCR or replace services with hardcoded data.

It runs `./scripts/stack.sh preflight` first, which checks the Docker daemon,
Compose version, disk headroom, memory, published ports, `.env` completeness,
and Postgres volume/password consistency — and names the container or process
holding a conflicting port rather than letting Compose fail on it minutes into
a build.

```bash
./scripts/stack.sh bootstrap
```

**A healthy stack is not a usable one.** Every container can be green while
every business scenario fails, because the vendor master, invoice history,
policies, and sanctions data are not loaded. `bootstrap` loads them — through
the product's own API, so the run also exercises authorization, idempotency,
audit, and indexing — and prints a readiness report. It is idempotent; running
it twice changes nothing.

If `SANCTIONS_EU_URL` is not configured, bootstrap completes and tells you
plainly that supplier scenarios will block at screening, which is the designed
fail-closed behaviour. Pass `--allow-missing-eu-sanctions` to proceed anyway
for invoice-only testing.

```bash
./scripts/stack.sh doctor
```

`doctor` reports three tiers, because they are genuinely different questions:
liveness (processes running, one-shot jobs exited 0), readiness (dependencies
answering correctly), and business-readiness (the data a scenario actually
needs). Tier 3 fails until `bootstrap` has run, and that is the point.

Open:

- Web: <http://localhost:3000>
- API docs in development: <http://localhost:8000/docs>
- Keycloak: <http://localhost:8080>
- Mailpit: <http://localhost:8025>

The product command bootstraps synthetic users from secrets in `.env`; it does
not commit passwords. Set `AUTH_MODE=keycloak` for role acceptance.
`AUTH_MODE=development` is restricted to local engineering. Production
configuration rejects development authentication and placeholder credentials.

## Native Windows setup (no Docker)

Docker Compose is the supported path. Running fully natively is possible but
manual: every infra service in `docker-compose.yml` is installed and
configured directly on Windows instead of containerized, and PowerShell (not
WSL2/Bash) drives it.

### 1. Install the native binaries

| Component | Install | Version (matches `docker-compose.yml`) |
|---|---|---|
| PostgreSQL | `winget install PostgreSQL.PostgreSQL.18` (or any PG16+) | — |
| Redis | `winget install Redis` (or any native Windows build) | — |
| Python | `winget install Python.Python.3.12` | 3.12 |
| Erlang/OTP | `winget install Erlang.ErlangOTP` (RabbitMQ dependency) | any |
| RabbitMQ | download `rabbitmq-server-*.exe` from the [releases page](https://github.com/rabbitmq/rabbitmq-server/releases) and run the installer | 3.13.x (see caveat below) |
| Qdrant | download `qdrant-x86_64-pc-windows-msvc.zip` from [releases](https://github.com/qdrant/qdrant/releases), extract `qdrant.exe` | v1.14.1 |
| MinIO + mc | download `minio.exe` and `mc.exe` from [dl.min.io](https://dl.min.io) (server + client, windows-amd64) | matches compose `RELEASE` tag |
| OPA | download `opa_windows_amd64.exe` from [releases](https://github.com/open-policy-agent/opa/releases) | v1.5.1 |
| Mailpit | `winget install axllent.mailpit` | v1.27.0 |
| ClamAV | `winget install Cisco.ClamAV` | any recent 1.x |
| Tesseract OCR | `winget install UB-Mannheim.TesseractOCR` | any |
| Keycloak | download `keycloak-26.2.5.zip` from [releases](https://github.com/keycloak/keycloak/releases), extract | 26.2.5 |

Put downloaded/extracted binaries under a `native/` folder at the repo root
(already gitignored). Postgres and Redis typically already run as Windows
services once installed.

### 2. Configure each service

- **Postgres**: create the `neurox` database and a `neurox_migration`
  superuser role (matching what the Docker image's `POSTGRES_USER` bootstrap
  does), then run the role/grant SQL from
  [`infra/postgres/001-roles.sh`](./infra/postgres/001-roles.sh) against it,
  substituting the `NEUROX_*_DB_PASSWORD` values from `.env`.
- **RabbitMQ**: enable the management plugin, then create the `neurox` vhost
  and `neurox` user with `RABBITMQ_PASSWORD` from `.env`, granting it full
  permissions on that vhost.
- **MinIO**: start `minio.exe server <data-dir> --console-address :9001` with
  `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` from `.env`, then use `mc.exe` to
  replicate what `minio-init` does in Compose — create the
  `neurox-quarantine`/`neurox-documents` buckets, set them private, and create
  the app user/policy from
  [`infra/minio/neurox-policy.json`](./infra/minio/neurox-policy.json).
- **ClamAV**: point `clamd.conf`/`freshclam.conf` at a writable data
  directory, set `TCPSocket 3310` / `TCPAddr 127.0.0.1`, run `freshclam.exe`
  once to fetch definitions, then start `clamd.exe`.
- **OPA**: `opa.exe run --server --addr=0.0.0.0:8181 policies/`.
- **Keycloak**: copy
  [`infra/keycloak/neurox-realm.json`](./infra/keycloak/neurox-realm.json)
  into `<keycloak>/data/import/`, then run
  `bin\kc.bat start-dev --import-realm --http-port=8080` with
  `KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD` from `.env`. For
  full role-based testing, use `kcadm.bat` to replicate
  [`infra/keycloak/bootstrap-acceptance.sh`](./infra/keycloak/bootstrap-acceptance.sh)
  (creates the 7 synthetic users and the `neurox-e2e` client) against
  `http://localhost:8080`.

### 3. Python services

All Python processes (`api` + every `*-worker`, plus `mock-erp`) can share one
venv, since `requirements-document.txt`/`requirements-retrieval.txt` don't
conflict with the base `requirements.txt`:

```powershell
py -3.12 -m venv services/api/.venv
services/api/.venv/Scripts/pip install -r services/api/requirements.txt -r services/api/requirements-document.txt -r services/api/requirements-retrieval.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

`services/api/app/config.py` already defaults every host to `localhost` — add
only these overrides to root `.env` (constructing full connection strings
from the individual `.env` passwords, since Compose normally does that
interpolation):

```dotenv
DATABASE_URL=postgresql+asyncpg://neurox_app:<NEUROX_APP_DB_PASSWORD>@localhost:5432/neurox
WORKER_DATABASE_URL=postgresql+asyncpg://neurox_worker:<NEUROX_WORKER_DB_PASSWORD>@localhost:5432/neurox
RABBITMQ_URL=amqp://neurox:<RABBITMQ_PASSWORD>@localhost:5672/neurox
RETRIEVAL_URL=http://localhost:8100
OPA_URL=http://localhost:8181
MOCK_ERP_URL=http://localhost:8090
STORAGE_BACKEND=s3
S3_ACCESS_KEY=<MINIO_APP_USER>
S3_SECRET_KEY=<MINIO_APP_PASSWORD>
```

Then run migrations and seed once, against the `neurox_migration` /
`neurox_app` roles respectively:

```powershell
cd services/api
$env:DATABASE_URL = "postgresql+asyncpg://neurox_migration:<NEUROX_MIGRATION_DB_PASSWORD>@localhost:5432/neurox"
.venv/Scripts/python.exe -m alembic upgrade head
$env:DATABASE_URL = "postgresql+asyncpg://neurox_app:<NEUROX_APP_DB_PASSWORD>@localhost:5432/neurox"
.venv/Scripts/python.exe -m scripts.seed
```

### 4. Web app

Create `apps/web/.env.local` (gitignored, standard Next.js dev convention):

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_AUTH_MODE=keycloak
NEXT_PUBLIC_KEYCLOAK_URL=http://localhost:8080
NEXT_PUBLIC_KEYCLOAK_REALM=neurox
NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=neurox-web
```

Then `npm ci` and `npm run dev` from `apps/web/`.

### 5. Start everything

```powershell
pwsh scripts/run-native.ps1 start
pwsh scripts/run-native.ps1 status
pwsh scripts/run-native.ps1 stop
```

This starts every native binary and Python worker (Postgres/Redis are left
alone since they run as persistent Windows services). It does not start the
web dev server; run that separately.

### Known caveat: RabbitMQ

RabbitMQ's native Windows boot can hang indefinitely right after printing its
version banner, before any of its own boot-step logging — reproduced across
both RabbitMQ 4.1.0 and 3.13.7, and both Erlang 27 and 29. Diagnosis via
`rabbitmqctl eval` traced it to `rabbit:start_it/1` blocked forever waiting on
a reply from an `application_controller` that is itself completely idle —
consistent with a call silently orphaned by an interrupted boot step, most
likely real-time antivirus scanning interfering with the many small files
RabbitMQ's Khepri/Mnesia store writes on first start. Adding a Windows
Defender exclusion for `native/` and the RabbitMQ install directory (requires
an administrator) is the most likely fix; this has not yet been verified on
this machine. Until resolved, document-processing queues, agent workers, and
the outbox relay won't run — the API, auth, storage, malware scanning,
retrieval, and policy checks all work independently of RabbitMQ.

### Optional operations profile

Telemetry dashboards and continuous WAL backup are real operational
capabilities, but they are not required to start and prove the workflows.

```bash
./scripts/stack.sh operations-up
```

This overlays OpenTelemetry Collector, Tempo, Prometheus, Grafana and encrypted
pgBackRest/WAL archival on the same product services. No source fork or fake
runtime is used. Stop either profile without deleting volumes using
`product-down` or `operations-down`.

## Local verification without containers

```bash
cd services/api
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q

cd ../../apps/web
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

## Policy and sanctions data

Create and publish tenant policies through `/api/v1/knowledge/documents`. Publication emits an indexing event; retrieval enforces tenant, role, publication and effective-date filters before ranking.

Official sanctions files are not bundled. An administrator requests imports
through `POST /api/v1/admin/sanctions-imports`; the dedicated worker downloads
only allowlisted official HTTPS sources, validates size/XML safety and records
URL, ETag, checksum, publication time and version before publication. The
workflow requires current OFAC, UN and EU datasets and fails closed if any are
missing or stale.

For a checksum-approved normalized offline import, use:

```bash
cd services/api
.venv/bin/python scripts/import_sanctions.py \
  --source OFAC \
  --version 2026-07-19 \
  --source-url https://ofac.treasury.gov/replace-with-approved-official-export \
  --file /approved/path/ofac.csv \
  --sha256 REPLACE_WITH_APPROVED_SHA256
```

If sanctions or applicable policy data is unavailable, analysis fails closed into a visible verification state.

## Backup and acceptance

In the operations profile, PostgreSQL WAL archiving and pgBackRest use the
isolated `neurox-backups` bucket and separate MinIO credentials. Follow
[`docs/backup-restore-runbook.md`](./docs/backup-restore-runbook.md) and restore
only into a new isolated volume.

The functional product profile keeps all OCR engines and local retrieval
models. Allow at least 8 CPUs, 16 GB RAM and 25–35 GB of free build headroom.
The operations profile and repeated failure/evaluation runs need roughly
45–50 GB of safe headroom because Docker temporarily retains build layers,
model downloads, malware definitions and durable volumes.

```bash
./scripts/stack.sh product-up
```

Before running it, set `AUTH_MODE=keycloak`, keep all test data synthetic, set
`ALLOW_EXTERNAL_LLM=true`, configure the server-side `GEMINI_API_KEY`, and
replace every `CHANGE_ME` secret. Never put credentials in source control or
chat.

### Browser and failure acceptance

Playwright runs against the **real running stack**, never a mocked backend —
a mocked suite would repeat exactly the mistake it exists to catch.

```bash
./scripts/stack.sh product-up
./scripts/stack.sh bootstrap
./scripts/stack.sh doctor          # fail fast if the stack is not healthy

cd apps/web
npm ci && npm run e2e:install
npm run e2e                        # golden supplier and invoice journeys
npm run e2e:failures               # deliberate failure injection
```

The journeys assert on evidence values — the citation, the variance figure, the
audit entry — not on pages rendering. Failure injection stops and starts real
containers, so it runs separately from the journeys and restarts whatever it
stopped.

### Restore drill

The runbook has an executable form, which reports the RPO and RTO it measured
rather than the ones the document hopes for:

```bash
./scripts/stack.sh operations-up
./scripts/restore-drill.sh
```

It restores into a throwaway volume and container; the live `postgres_data`
volume is never touched.

### Evaluation

```bash
docker compose exec api python -m scripts.evaluation materialize
docker compose exec api python -m scripts.evaluation run       # resumable
docker compose exec api python -m scripts.evaluation score
```

All 100 cases need a real LLM, so a full run is 100 live workflows and will hit
quota. The runner checkpoints after every case and treats quota exhaustion as a
pause rather than a failure; resume with `run --resume`. The report publishes
the measured numbers, and prints *not measured* where nothing exercised a
metric rather than rounding it to zero.

## Release truth

See [CURRENT_STATUS.md](./CURRENT_STATUS.md) for evidence-backed state and [MASTER_TODO.md](./MASTER_TODO.md) for acceptance blockers. The implementation is not an enterprise release until the remaining integration, security, chaos, load and 100-case evaluation gates pass.

## Competition product documents

- [Competition product build plan](./docs/competition/COMPETITION_PRODUCT_BUILD_PLAN.md)
- [Technical architecture and agent explainer](./docs/competition/TECHNICAL_ARCHITECTURE_AND_AGENT_EXPLAINER.md)
- [Demo and buyer pitch guide](./docs/competition/DEMO_AND_BUYER_PITCH_GUIDE.md)
- [Judges Q&A and gap register](./docs/competition/JUDGES_QA_AND_GAP_REGISTER.md)


Username: admin (or requester, analyst, procurement, compliance, finance, auditor)

Password: d3bbc9db8663f9282502400c6c2010f116335857e0a0b5c53a0dd018b0687c91
