# NeuroX implementation status

Status is evidence-based. Allowed values are `NOT_STARTED`, `IMPLEMENTED`,
`VERIFIED`, and `BLOCKED`.

Last updated: 2026-07-25

## Release truth

`feature/p0-p1-enterprise-e2e` is a production-shaped P0/P1 implementation
branch based on clean commit `1928fd0`. It is not yet an enterprise release and
must not be merged to `dev` until the complete Compose acceptance profile,
browser journeys, numerical evaluations, security/chaos/load tests and
backup/restore drill pass.

Local full-stack acceptance is currently `BLOCKED`: the workstation has only
approximately 3.5 GB free, while the OCR/model/observability stack needs about
50 GB of safe working space. No broad or destructive Docker cleanup was
performed.

## P0/P1 capability ledger

| Capability | Status | Evidence / remaining gate |
|---|---|---|
| Reversible Alembic schema and full SQLAlchemy model | VERIFIED | PostgreSQL 16 downgrade to base and upgrade through `a066778899aa` passed. |
| API, worker, relay, audit and migration database roles | VERIFIED | Live two-tenant tests prove cross-role grants and RLS isolation. |
| Transaction-local tenant context | VERIFIED | Live non-superuser API/worker/audit/relay test passed; LangGraph checkpoint tables also use tenant-prefixed RLS. |
| Keycloak OIDC, PKCE, RBAC and synthetic user bootstrap | IMPLEMENTED | Acceptance realm/client/bootstrap exist; live token, role and tenant tests require the full stack. |
| Optimistic versions and mutation idempotency | VERIFIED | API/contract tests cover stale decisions, replayed submissions and evidence-bound mutations. |
| Transactional outbox/inbox and versioned event contracts | VERIFIED | Unit/contract tests validate safety-command routing, payload schemas, idempotency and PII rejection; live broker restart/DLQ tests remain. |
| Quorum queues, manual acknowledgements, retry queues and DLQs | IMPLEMENTED | Isolated queues and required-route handling exist; broker/worker failure injection remains. |
| Durable SSE replay | IMPLEMENTED | PostgreSQL events and `Last-Event-ID` replay are wired; multi-instance/browser acceptance remains. |
| Tamper-evident audit and authorized exports | IMPLEMENTED | Hash chaining, mutation protection and expiring exports exist; live mutation and export-download security tests remain. |
| S3/MinIO quarantine and private document storage | IMPLEMENTED | Presigned upload, completion validation, duplicate hashes and private download exist; live MinIO expiry/isolation tests remain. |
| ClamAV document gate | IMPLEMENTED | Quarantine scan/move and failure states exist; malicious PDF/archive-bomb acceptance remains. |
| Native PDF plus per-page Docling/Tesseract/EasyOCR | VERIFIED | Mixed native/scanned routing and low-confidence fallback unit tests pass; corpus-level F1 is not measured. |
| Local PII recognition, tokenization, encryption and blind indexes | VERIFIED | Tax/bank/SWIFT/registration recognizers and adversarial payload rejection tests pass; full log/trace fixture sweep remains. |
| Parent/child policy ingestion | VERIFIED | Structure-aware chunking tests pass. |
| Dense+sparse Qdrant retrieval, RRF and reranking | IMPLEMENTED | Tenant/ACL/effective-date filtering exists; live Qdrant and Recall@10/citation metrics remain. |
| OFAC/UN/EU versioned sanctions adapters | IMPLEMENTED | Official-shape parsers, SSRF/DOCTYPE defenses, checksums, ETags and stale/missing-source blocking exist. Live OFAC and UN downloads parsed successfully; an approved EU export URL is still required. |
| Deterministic duplicate/sanctions/PO/GRN/policy controls | VERIFIED | Unit tests cover duplicate scoring, sanctions fail-closed behavior and invoice matching; 100-case calibration remains. |
| Fail-closed OPA ERP authorization | IMPLEMENTED | ERP writes require an independent decision over state, evidence hash, case version, SoD, verification and mandatory reviews. Typed gateway tests pass; the pinned OPA image compile/runtime test is blocked by Docker registry CDN DNS. |
| Supplier and invoice durable LangGraphs | VERIFIED | Both explicit graphs use PostgreSQL checkpointing, typed results and durable clarification/review/approval/ERP interrupts; live checkpoint disconnect/reconnect test passed. Full worker-kill journey remains. |
| Gemini structured reasoning gateway | VERIFIED | Real synthetic `gemini-3.6-flash` structured-output smoke passed; auth/quota/rate/schema/unavailable errors fail visibly. A 100-case quota run remains. |
| Evidence builder, deterministic verifier and Gemini critique | VERIFIED | Graph tests prove evidence hashing, verifier gates, bounded critique and no persisted chain-of-thought. |
| Separate human controls and signed resume | IMPLEMENTED | Clarification, duplicate, sanctions, bank-change, final approval and ERP confirmation tasks are version/evidence-bound; full role browser journeys remain. |
| Evidence-bound idempotent mock ERP | VERIFIED | Tests prove identical replay and reject idempotency-key reuse with a changed payload; timeout/restart E2E remains. |
| Independent in-app and SMTP notifications | VERIFIED | Test proves SMTP failure leaves case status/version unchanged and creates an isolated retry. Live Mailpit/outage acceptance remains. |
| OpenAPI and Orval-generated frontend client | VERIFIED | OpenAPI regeneration, Orval generation, ESLint and TypeScript pass; CI has generated-artifact drift gates. |
| Operational frontend UX | IMPLEMENTED | Real work queues, claiming, SLA/saved filters, status chips, document rendering/correction, clarification, control review, evidence and admin health are wired; Playwright/accessibility acceptance remains. |
| OpenTelemetry/Tempo/Prometheus/Grafana profile | IMPLEMENTED | API/SQL/HTTP, outbox, broker, worker, retrieval and Gemini spans propagate W3C context; collector removes statements, bodies, prompts and URL queries. Live correlation/redaction inspection remains. |
| Integration health view | IMPLEMENTED | Admin-only database, broker, Redis, storage, Qdrant, OCR, Gemini, sanctions, SMTP and ERP checks exist; full-stack validation remains. |
| pgBackRest/WAL backup to isolated object storage | IMPLEMENTED | Encrypted repository configuration and restore runbook exist; RPO/RTO restore drill remains. |
| Production-shaped Compose boundaries | IMPLEMENTED | All application/infrastructure services and health dependencies resolve with `docker compose config`; image pulls/build and clean launch are disk-blocked. |
| CI lint/type/test/build/audit/SBOM/scan gates | IMPLEMENTED | Workflow is pinned to Python 3.12/Node 22.22 and includes migration, live RLS/checkpoint, contract drift, audits, SBOM, Trivy and gitleaks. A GitHub run has not yet executed for this branch. |
| Reproducible 100-case evaluation corpus | IMPLEMENTED | Manifest contains exactly 50 supplier and 50 invoice synthetic scenarios with required adversarial categories. Documents, real-agent execution and numerical release thresholds remain. |
| Playwright, chaos, load, backup/restore and full security acceptance | BLOCKED | Requires approximately 50 GB free disk and a clean running acceptance profile. |
| VPS deployment | BLOCKED | Requires successful local acceptance plus VPS access, DNS and SMTP secrets from the owner. |

## Latest local verification

- API/domain/contract tests: `61 passed, 2 skipped`; the skips are the separately
  executed live PostgreSQL integration tests.
- Live PostgreSQL RLS/checkpoint integration: `2 passed`.
- Alembic PostgreSQL 16 downgrade-to-base and re-upgrade-to-head: passed.
- Ruff, mypy domain gate and Python compilation: passed.
- OpenAPI export and Orval client regeneration: passed.
- Frontend ESLint, TypeScript and Next.js 16.2.11 production build: passed.
- npm production dependency audit: `0 vulnerabilities`.
- API, document and retrieval Python requirement audits: no known
  vulnerabilities in the last completed audit; CI reruns them.
- Compose configuration and event/OpenAPI JSON validation: passed.
- Real Gemini structured synthetic call: passed with `gemini-3.6-flash`.
- Live official-source adapter smoke: OFAC and UN passed; EU is intentionally
  fail-closed until an approved official export URL is configured.

`IMPLEMENTED` never means production-verified. Only the evidence named above
can move a capability to `VERIFIED`.
