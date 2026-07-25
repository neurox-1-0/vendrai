# NeuroX implementation status

Status is evidence-based. Allowed values are `NOT_STARTED`, `IMPLEMENTED`, `VERIFIED`, and `BLOCKED`.

Last updated: 2026-07-25

## Repository truth

The `dev` branch is a production-shaped pre-release implementation, not an enterprise release. The frontend is no longer a static prototype and the invoice path no longer sends raw documents to an external model, but live multi-container, security, quality-evaluation, load, chaos, backup/restore and disaster-recovery acceptance gates remain.

## Shared supplier-onboarding platform

| Capability | Status | Evidence / remaining gate |
|---|---|---|
| Tenant-scoped case, document, run, event, evidence, approval, notification and ERP schema | IMPLEMENTED | SQLAlchemy models and migrations exist; live RLS and end-to-end service tests remain. |
| Reversible pre-release Alembic chain | VERIFIED | Fresh PostgreSQL 16 upgrade to head, downgrade to base and re-upgrade to head passed on 2026-07-25. |
| Least-privilege database roles and tenant RLS context | IMPLEMENTED | API/workers set transaction-local tenant context and migrations define roles/policies; live cross-role PostgreSQL tests remain. |
| Keycloak JWT validation, PKCE web login, RBAC and segregation of duties | IMPLEMENTED | Realm/client configuration and API permission gates exist; live Keycloak role/tenant tests remain. |
| Optimistic case versions and idempotent mutations | VERIFIED | API tests cover submission idempotency, stale version checks and evidence-bound decisions. |
| Transactional outbox, inbox deduplication and durable case events | IMPLEMENTED | Atomic outbox/inbox code exists; live broker restart and duplicate-delivery tests remain. |
| Isolated RabbitMQ retries and dead-letter queues | IMPLEMENTED | Per-worker quorum queues, tiered TTL retries, publisher confirms, manual acknowledgement and isolated DLQs exist; broker-level failure injection remains. |
| Tamper-evident append-only audit chain | IMPLEMENTED | Hash chaining and database mutation protection exist; live mutation/recovery tests remain. |
| Quarantine upload, file validation and ClamAV gate | IMPLEMENTED | Upload validation and local processing code exist; malicious-file, archive-bomb and live S3/ClamAV tests remain. |
| Native PDF extraction plus Docling/Tesseract/EasyOCR worker | IMPLEMENTED | Isolated document image and native/OCR routing exist; mixed-document confidence evaluation remains. |
| Local PII masking, encryption and blind indexes | IMPLEMENTED | Sensitive extracted values are encrypted/blind-indexed and persisted text is masked; adversarial leakage evaluation remains. |
| Parent/child policy chunks | VERIFIED | Structure-aware chunking unit tests pass. |
| Dense+sparse retrieval, RRF and reranking | IMPLEMENTED | Tenant/ACL/effective-date filters and Qdrant retrieval services exist; Recall@10/citation evaluation remains. |
| Versioned local sanctions data and deterministic matching | IMPLEMENTED | Importer and matching code exist; approved official data, refresh scheduling and ≥100-case calibration remain. |
| Explicit supplier workflow, evidence verification and HITL pause | IMPLEMENTED | Deterministic workflow and persisted approval/clarification tasks exist; PostgreSQL LangGraph checkpoint kill/resume remains. |
| Controlled working, episodic, semantic and procedural memory schema | IMPLEMENTED | Storage models exist; authorization, retention and evaluation of memory retrieval remain. |
| External LLM privacy gateway | IMPLEMENTED | External use is disabled by default and bounded to allowlisted/tokenized context; provider privacy and leakage tests remain. |
| Evidence-bound mock ERP synchronization | IMPLEMENTED | Approval/evidence gates and idempotent operations exist; timeout/retry/replay E2E tests remain. |
| Independent in-app/email notifications | IMPLEMENTED | Notification events retry independently and do not mutate case state; live SMTP outage test remains. |
| Real frontend API integration | VERIFIED | Mock business arrays/timers were removed; ESLint, TypeScript and production build pass. |
| Accessible operational UX | IMPLEMENTED | Text+icon status chips, responsive navigation and evidence/progress views exist; Playwright and accessibility acceptance remain. |
| Production-shaped Compose boundaries | IMPLEMENTED | Web/API/relay/document/agent/invoice/retrieval/notification/ERP services and infrastructure resolve in Compose; full-stack launch is not verified. |
| CI quality/security gates | IMPLEMENTED | `dev` and `main` run isolated Python tests/type checks, frontend checks, dependency audits, image scan and secret scan; GitHub run remains. |
| OpenTelemetry | IMPLEMENTED | Collector topology exists; application-level correlated spans and redaction verification remain. |
| Optional Langfuse v3 profile | NOT_STARTED | Requires ClickHouse, Valkey and blob storage before it can be enabled correctly. |
| 100-case evaluation and release thresholds | NOT_STARTED | Mandatory before enterprise release. |
| Backup/restore, load, chaos and security acceptance | NOT_STARTED | Mandatory before enterprise release. |

## Invoice-exception recovery slice

| Capability | Status | Evidence / remaining gate |
|---|---|---|
| AP domain models and reversible schema | VERIFIED | Decimal-backed PO/GRN/invoice/exception models are present and the PostgreSQL migration cycle passes. |
| Draft/upload/submit API with RBAC and idempotency | VERIFIED | API tests prove one draft case is reused through upload and submission and unauthorized auditors are rejected. |
| Privacy-first local invoice extraction | IMPLEMENTED | Worker consumes only masked `DocumentPage` text, rejects ambiguous/incomplete documents and contains no raw Gemini file upload; adversarial leakage E2E remains. |
| Deterministic PO/GRN matching, duplicate, bank and tax checks | IMPLEMENTED | Signed Decimal variance, mandatory GRN/PO evidence, tenant/vendor duplicate lookup and blind-index bank comparison have unit coverage; representative evaluation remains. |
| Policy-grounded evidence packet and fail-closed verification | IMPLEMENTED | Canonical tamper-sensitive evidence hashes and policy citations are required; live retrieval outage/publication tests remain. |
| Durable approval, clarification and escalation | IMPLEMENTED | Evidence/version-bound HITL, explicit duplicate/HOLD states and fresh admin escalation tasks exist; worker kill/resume and full UI journey remain. |
| Invoice LangGraph PostgreSQL checkpointer | NOT_STARTED | The unused hard-coded mock graph was removed. The current invoice workflow is durable through DB state/outbox but is not yet a LangGraph checkpointed graph. |
| Mock ERP invoice resolution | IMPLEMENTED | Resolution is idempotent, evidence-gated and writes invoice history after confirmation; live timeout/retry E2E remains. |
| Real invoice frontend and SSE progress | VERIFIED | UI creates a real invoice draft, uploads documents to that case, submits it and consumes durable run events; lint/type/build pass. |

## Latest local verification

- API tests: `18 passed`.
- Agent intelligence tests: `4 passed`.
- Ruff, Python compilation and both isolated mypy gates: passed.
- Frontend ESLint, TypeScript and Next.js 16.2.11 production build: passed.
- npm production dependency audit: `0 vulnerabilities`.
- PostgreSQL 16 migration upgrade/downgrade/re-upgrade: passed.
- Compose configuration resolution: passed.
- Full service stack, Keycloak, RabbitMQ failure paths, ClamAV, Qdrant, SMTP and ERP E2E: not run.
- Python dependency audit, container scan and GitHub CI: not rerun in this local pass.

`IMPLEMENTED` must not be read as `VERIFIED`; only the acceptance evidence named in this file can move a capability to `VERIFIED`.
