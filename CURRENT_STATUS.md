# NeuroX implementation status

Status is evidence-based. Allowed values are `NOT_STARTED`, `IMPLEMENTED`,
`VERIFIED`, and `BLOCKED`.

Last updated: 2026-07-27

## Release truth

`dev` now contains the production-shaped P0/P1 implementation. The current
`fix/ci-migrations-images` branch repairs the first GitHub CI failures and must
be rerun before its PR is merged. The product is not yet an enterprise release:
complete Compose acceptance, browser journeys, numerical evaluations,
security/chaos/load tests and the backup/restore drill remain.

Local full-stack acceptance is currently `BLOCKED`: the workstation has
approximately 3.5 GB free after targeted CI image reproduction and no complete
NeuroX OCR/retrieval images cached. The
functional product profile keeps Docling, Tesseract, EasyOCR, ClamAV and local
retrieval models and therefore needs materially more safe Docker build
headroom. Docker Desktop is running and readable. The local bootstrap completed:
the existing Gemini key was preserved and all required internal
service/database/Keycloak/MinIO/Grafana secrets are now present in the ignored,
permission-restricted `.env`. One legacy `vendortopay_db` prototype container
is running, but the current application stack is not. No broad or destructive
Docker cleanup was performed.

## P0/P1 capability ledger

| Capability | Status | Evidence / remaining gate |
|---|---|---|
| Reversible Alembic schema and full SQLAlchemy model | VERIFIED | Fresh PostgreSQL upgrade, downgrade to base and re-upgrade through copilot head `a1778899aabb` passed. Historical revisions now contain frozen Alembic operations and a regression test rejects mutable ORM `create_all`/`drop_all` calls. |
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
| Supplier and invoice durable agent execution | VERIFIED | A validated Gemini plan selects eligible supplier/invoice capabilities; independent specialists execute concurrently with failure isolation and persisted timing. The shared PostgreSQL-checkpointed LangGraph owns contradiction reasoning, verification, clarification/review/approval and ERP interrupts. Live checkpoint disconnect/reconnect passed; full worker-kill journey remains. |
| Planner and capability registry | VERIFIED | Tests prove schema-valid real-gateway planning, mandatory capability enforcement, unknown/missing dependency rejection and dynamic execution groups. Provider failure remains visible and preserves mandatory deterministic work. |
| Failure-isolated parallel specialists | VERIFIED | Tests prove wall-clock overlap and retention of successful siblings when another branch raises. Supplier and invoice workers persist per-branch status, typed error and measured timestamps. |
| Gemini structured reasoning gateway | VERIFIED | Real synthetic `gemini-3.6-flash` structured-output smoke passed; auth/quota/rate/schema/unavailable errors fail visibly. A 100-case quota run remains. |
| Evidence builder, deterministic verifier and Gemini critique | VERIFIED | Graph tests prove evidence hashing, verifier gates, bounded critique and no persisted chain-of-thought. |
| Separate human controls and signed resume | IMPLEMENTED | Clarification, duplicate, sanctions, bank-change, final approval and ERP confirmation tasks are version/evidence-bound; full role browser journeys remain. |
| Evidence-bound idempotent mock ERP | VERIFIED | Tests prove identical replay and reject idempotency-key reuse with a changed payload; timeout/restart E2E remains. |
| Independent in-app and SMTP notifications | VERIFIED | Test proves SMTP failure leaves case status/version unchanged and creates an isolated retry. Live Mailpit/outage acceptance remains. |
| OpenAPI and Orval-generated frontend client | VERIFIED | OpenAPI regeneration, Orval generation, ESLint and TypeScript pass; CI has generated-artifact drift gates. |
| Operational frontend UX | IMPLEMENTED | Real work queues, claiming, SLA/saved filters, status chips, document rendering/correction, clarification, control review, evidence and admin health are wired; browser/accessibility acceptance remains. |
| Agent execution and judge diagnostics UX | IMPLEMENTED | Case UI renders durable planner/specialist/reasoning/verifier/HITL/ERP lanes, attempts, dependencies, rationale, latency, critical path and parallel time saved. A tenant/run-scoped Redis projection exposes `RUNNING` and terminal specialist progress before the worker transaction commits; matching PostgreSQL steps automatically take authority. Projection isolation/reconciliation tests pass, and projection failure cannot stop workflow execution. Auditor/admin diagnostics are sanitized. Browser acceptance remains. |
| Read-only application copilot | IMPLEMENTED | Tenant/user-scoped masked sessions, conversational working memory, versioned CAG retrieval, authorization-filtered case context, Gemini structured answers, explicit local fallback, and versioned tenant-scoped feedback pass API tests. Visible components now self-register semantic assistance metadata; the masked context produces server-validated spotlight actions and accessible adaptive tours without brittle selector lists. Published-help RAG, controlled administrator promotion and full-stack browser acceptance remain. |
| OpenTelemetry/Tempo/Prometheus/Grafana profile | IMPLEMENTED | API/SQL/HTTP, outbox, broker, worker, retrieval and Gemini spans propagate W3C context; collector removes statements, bodies, prompts and URL queries. It is now an explicit operations overlay so optional telemetry cannot block product startup. Live correlation/redaction inspection remains. |
| Integration health view | IMPLEMENTED | Admin-only database, broker, Redis, storage, Qdrant, OCR, Gemini, sanctions, SMTP and ERP checks exist; full-stack validation remains. |
| pgBackRest/WAL backup to isolated object storage | IMPLEMENTED | Encrypted repository configuration and restore runbook exist in the operations overlay; RPO/RTO restore drill remains. |
| Production-shaped Compose boundaries | IMPLEMENTED | `product-up` contains every functional workflow dependency and `operations-up` adds telemetry/backup using the same images and source. Both actual `.env` configurations resolve, and the startup script warns about low disk without deleting data. Image pulls/build and clean full-stack launch remain blocked by available disk space. |
| CI lint/type/test/build/audit/SBOM/scan gates | IMPLEMENTED | The migration failure was reproduced and fixed; patched Python 3.12.13, PostgreSQL 16.13 and Node 22.23.1 bases replace stale vulnerable images. The mock-ERP final image passes the unchanged Trivy HIGH/CRITICAL gate, and the web Docker build now has safe defaults plus a package-manager-free runtime. A fresh GitHub run is still required for all six matrix images. |
| Reproducible 100-case evaluation corpus | IMPLEMENTED | Manifest contains exactly 50 supplier and 50 invoice synthetic scenarios with required adversarial categories. Documents, real-agent execution and numerical release thresholds remain. |
| Browser, chaos, load, backup/restore and full security acceptance | BLOCKED | Frontend-only browser smoke passed for the dashboard, supplier intake, invoice intake and copilot, including honest API-unavailable states. The improved semantic copilot UI passes lint, type and production build, but needs a running API browser journey. Full workflow acceptance still requires more free disk and a clean running product profile. |
| VPS deployment | BLOCKED | Requires successful local acceptance plus VPS access, DNS and SMTP secrets from the owner. |

## Latest local verification

- API/domain/contract tests: `78 passed, 2 skipped`; the skips are the separately
  executed live PostgreSQL integration tests.
- Live PostgreSQL RLS/checkpoint integration: `2 passed`.
- Alembic PostgreSQL 16 downgrade-to-base and re-upgrade-to-head: passed.
- Ruff, mypy domain gate and Python compilation: passed.
- OpenAPI export and Orval client regeneration: passed.
- Frontend ESLint, TypeScript and Next.js 16.2.11 production build: passed.
- Generated contracts include run steps/graph/diagnostics and copilot
  sessions/messages/feedback/semantic assistance targets with mutation
  idempotency enforcement.
- Failure-isolated concurrency tests prove three specialist operations overlap
  and a failed branch does not erase a successful sibling. Live-projection
  tests prove tenant/run scoping, expiry, malformed-payload rejection,
  durable-step precedence and workflow continuity during projection failure.
- npm production dependency audit: `0 vulnerabilities`.
- API, document and retrieval Python requirement audits: no known
  vulnerabilities in the last completed audit; CI reruns them.
- Compose configuration and event/OpenAPI JSON validation: passed.
- Product/operations profile resolution and stack launcher shell validation:
  passed. Heavy image build was not started with only 8.9 GB free.
- Real Gemini structured synthetic call: passed with `gemini-3.6-flash`.
- Live official-source adapter smoke: OFAC and UN passed; EU is intentionally
  fail-closed until an approved official export URL is configured.
- Frontend browser smoke: dashboard, supplier intake, invoice intake and
  copilot render correctly with no browser console errors. Full workflow and
  accessibility acceptance remains blocked because the API/workers are not
  running.

`IMPLEMENTED` never means production-verified. Only the evidence named above
can move a capability to `VERIFIED`.
