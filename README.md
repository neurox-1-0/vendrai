# NeuroX enterprise supplier onboarding

NeuroX is an evidence-driven supplier-onboarding vertical slice. Deterministic controls own authorization, tenant isolation, sanctions blocking, duplicate scoring, approvals and ERP authorization. LLM reasoning is optional, bounded and never receives raw documents or sensitive identifiers.

## Runtime boundaries

- `web`: Next.js work queues, secure intake, evidence review and notifications.
- `api`: FastAPI contracts, Keycloak/RBAC, RLS context and durable case events.
- `outbox-relay`: atomic database-to-RabbitMQ event publication.
- `document-worker`: quarantine, ClamAV, native PDF parsing, Docling/Tesseract/EasyOCR and local masking.
- `retrieval-worker` / `retrieval-api`: local dense+sparse policy index, RRF and reranking.
- `agent-worker`: deterministic duplicate/sanctions/policy aggregation and approval interruption.
- `notification-worker`: independent in-app/email delivery and delayed retries.
- `erp-worker` / `mock-erp`: evidence-bound, idempotent vendor creation.

PostgreSQL is authoritative. RabbitMQ quorum queues carry versioned events. Qdrant is a derived tenant-filtered policy index. Redis is limited to cache/coordination. Documents remain local.

## Local setup

Requirements: Docker Compose, Node.js 22.17+ and Python 3.12+.

```bash
cp .env.example .env
```

Replace every `CHANGE_ME` value with independently generated secrets. External LLM calls are disabled by default and are not required for the deterministic onboarding path.

```bash
docker compose up --build
```

Open:

- Web: <http://localhost:3000>
- API docs in development: <http://localhost:8000/docs>
- Keycloak: <http://localhost:8080>
- Mailpit: <http://localhost:8025>

The default Compose profile uses development identity unless `AUTH_MODE=keycloak` is set. For Keycloak mode, create users in the imported `neurox` realm, assign one or more realm roles, and keep PKCE enabled. Production configuration is rejected if development authentication or placeholder service credentials remain.

## Local verification without containers

```bash
cd services/api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q

cd ../../services/agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q

cd ../../apps/web
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

## Policy and sanctions data

Create and publish tenant policies through `/api/v1/knowledge/documents`. Publication emits an indexing event; retrieval enforces tenant, role, publication and effective-date filters before ranking.

Official sanctions files are not bundled. Normalize an approved official export to `external_id,name,aliases,countries`, verify its checksum and import it locally:

```bash
cd services/api
.venv/bin/python scripts/import_sanctions.py \
  --source OFAC \
  --version 2026-07-19 \
  --source-url https://example.invalid/replace-with-approved-official-url \
  --file /approved/path/ofac.csv \
  --sha256 REPLACE_WITH_APPROVED_SHA256
```

If sanctions or applicable policy data is unavailable, analysis fails closed into a visible verification state.

## Release truth

See [CURRENT_STATUS.md](./CURRENT_STATUS.md) for evidence-backed state and [MASTER_TODO.md](./MASTER_TODO.md) for acceptance blockers. The implementation is not an enterprise release until the remaining integration, security, chaos, load and 100-case evaluation gates pass.
