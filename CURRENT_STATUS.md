# NeuroX implementation status

Status is evidence-based. Allowed values are `NOT_STARTED`, `IMPLEMENTED`, `VERIFIED`, and `BLOCKED`.

Last updated: 2026-07-19

## Supplier-onboarding vertical slice

| Capability | Status | Evidence / remaining gate |
|---|---|---|
| Tenant-scoped case, document, run, event, evidence, approval, notification and ERP schema | VERIFIED | SQLAlchemy metadata compiles; API tests pass. |
| Reversible pre-release Alembic baseline and role grants | IMPLEMENTED | Upgrade/downgrade and RLS are implemented; PostgreSQL container execution is blocked locally because Docker is unavailable. |
| Keycloak JWT validation, PKCE web login, RBAC and segregation of duties | IMPLEMENTED | Contract and realm import exist; live Keycloak integration test remains. |
| PostgreSQL RLS tenant context | IMPLEMENTED | API and workers set transaction-local tenant context; cross-tenant API test passes; live PostgreSQL RLS test remains. |
| Optimistic case versions and idempotent mutations | VERIFIED | Submission/decision gates and API idempotency tests pass. |
| Transactional outbox, inbox deduplication and durable case events | IMPLEMENTED | Atomic writes and relay/consumer code exist; RabbitMQ restart/retry/DLQ tests remain. |
| Tamper-evident append-only audit chain | IMPLEMENTED | Hash chain, advisory serialization lock and database mutation trigger exist; live mutation test remains. |
| Quarantine upload, magic-byte/size/type checks and ClamAV gate | IMPLEMENTED | Deterministic upload validation tests pass; live ClamAV/S3 tests remain. |
| Native PDF extraction + Docling/Tesseract/EasyOCR container | IMPLEMENTED | Local born-digital extraction and isolated OCR image are implemented; low-confidence and malicious-document integration fixtures remain. |
| Local PII protection | IMPLEMENTED | Sensitive values are encrypted, blind-indexed and masked before persisted OCR text; full Presidio/custom-recognizer evaluation remains. |
| Parent/child policy chunks | VERIFIED | Chunking implementation has passing unit tests. |
| Dense+sparse Qdrant retrieval, RRF and cross-encoder reranking | IMPLEMENTED | Tenant/ACL/effective-date filters and index/search services exist; model-backed Recall@10 evaluation remains. |
| Versioned OFAC/UN/EU local sanctions import | IMPLEMENTED | Checksum-gated normalized importer exists; official datasets are not bundled and must be approved/imported. |
| Deterministic duplicate and sanctions scoring | VERIFIED | Unit tests pass; ≥100-case recall/calibration evaluation remains. |
| Explicit bounded workflow, evidence verification and HITL pause | VERIFIED | Deterministic graph tests pass and API persists approval interrupts; PostgreSQL LangGraph checkpointer is not yet integrated. |
| Controlled memory/evaluation schema | IMPLEMENTED | Working checkpoints, approved de-identified episodic records, semantic policy records, procedural prompt/model versions and evaluation results are modeled; memory retrieval/evaluation gates remain. |
| External LLM privacy gateway | IMPLEMENTED | External calls are off by default and minimized/tokenized payloads are enforced; provider evaluation is not complete. |
| Evidence-bound mock ERP synchronization | IMPLEMENTED | Idempotent adapter and hard approval gate exist; end-to-end timeout/retry test remains. |
| Independent in-app/email notifications | IMPLEMENTED | SMTP retries use delayed outbox events and cannot alter case state; outage integration test remains. |
| Real frontend API integration | VERIFIED | All prior mock arrays/timers were removed; lint, TypeScript and production build pass. |
| Accessible/responsive operational UX | IMPLEMENTED | Text+icon status chips, mobile navigation, errors, live event/evidence views and stale-decision behavior exist; Playwright accessibility journeys remain. |
| Production-shaped Compose boundaries | IMPLEMENTED | Services and pinned images are declared; `docker compose up` is blocked locally because Docker is not installed. |
| CI lint/type/test/audit/secret/container gates | IMPLEMENTED | Workflow exists; it has not run in GitHub yet. |
| OpenTelemetry collector/redaction | IMPLEMENTED | Collector topology exists; application span instrumentation is still `NOT_STARTED`. |
| Langfuse v3 optional profile | NOT_STARTED | Intentionally omitted until its ClickHouse/Valkey/blob dependencies are provisioned correctly. |
| 100-case evaluation suite and required quality thresholds | NOT_STARTED | Required before release. |
| Backup/restore, load, chaos and security acceptance run | NOT_STARTED | Required before release. |

## Latest local verification

- API: `7 passed`.
- Agent intelligence: `4 passed`.
- Python compilation: passed.
- Python mypy gate: passed.
- Frontend ESLint: passed.
- Frontend TypeScript: passed.
- Frontend production build: passed.
- Python dependency audits (API, OCR and retrieval images): no known vulnerabilities.
- npm audit: no known vulnerabilities.
- Compose YAML parse: passed.
- Full container launch: `BLOCKED`—Docker is not installed in the current environment.

This repository is now a production-shaped vertical slice, not a finished enterprise release. `IMPLEMENTED` must not be read as `VERIFIED` until its stated acceptance test passes.
