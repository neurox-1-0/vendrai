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
EasyOCR, Qdrant retrieval, OPA, Mailpit and the ERP sandbox. It does not omit
OCR or replace services with hardcoded data.

Open:

- Web: <http://localhost:3000>
- API docs in development: <http://localhost:8000/docs>
- Keycloak: <http://localhost:8080>
- Mailpit: <http://localhost:8025>

The product command bootstraps synthetic users from secrets in `.env`; it does
not commit passwords. Set `AUTH_MODE=keycloak` for role acceptance.
`AUTH_MODE=development` is restricted to local engineering. Production
configuration rejects development authentication and placeholder credentials.

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

## Release truth

See [CURRENT_STATUS.md](./CURRENT_STATUS.md) for evidence-backed state and [MASTER_TODO.md](./MASTER_TODO.md) for acceptance blockers. The implementation is not an enterprise release until the remaining integration, security, chaos, load and 100-case evaluation gates pass.

## Competition product documents

- [Competition product build plan](./docs/competition/COMPETITION_PRODUCT_BUILD_PLAN.md)
- [Technical architecture and agent explainer](./docs/competition/TECHNICAL_ARCHITECTURE_AND_AGENT_EXPLAINER.md)
- [Demo and buyer pitch guide](./docs/competition/DEMO_AND_BUYER_PITCH_GUIDE.md)
- [Judges Q&A and gap register](./docs/competition/JUDGES_QA_AND_GAP_REGISTER.md)
