# NeuroX master acceptance TODO

Only acceptance-test-backed work may move to `VERIFIED` in `CURRENT_STATUS.md`.

## Completed recovery work

- [x] Fast-forward local `dev` to the Vendrai `dev` history without modifying the untracked procurement corpus.
- [x] Repair the duplicate invoice-history RLS migration and verify PostgreSQL 16 upgrade/downgrade/re-upgrade.
- [x] Run CI on both `main` and `dev` with isolated API/agent import boundaries.
- [x] Remove raw invoice-document upload to Gemini and delete the unused hard-coded invoice graph/tools.
- [x] Replace the dummy invoice case/timer UI with one real draft/upload/submit case flow and durable SSE.
- [x] Add server-side invoice RBAC, idempotency, optimistic versions and evidence-bound approval controls.
- [x] Add local fail-closed extraction, Decimal matching, authoritative PO/GRN lookup, duplicate checks, blind-index bank comparison and policy evidence gating.
- [x] Replace placeholder evidence hashes with canonical tamper-sensitive hashes.
- [x] Add explicit duplicate/HOLD approval paths and safe escalation to a new admin task.
- [x] Add per-worker quorum retry queues, publisher confirms, manual acknowledgements and isolated dead-letter queues.
- [x] Upgrade frontend dependencies and clear the production npm audit.

## P0 — enterprise release blockers

- [ ] Launch the complete Compose profile and run a clean supplier-onboarding plus invoice-exception journey.
- [ ] Add live RLS tests using non-superuser API, worker, relay and audit roles.
- [ ] Add Keycloak token/role/tenant tests and a production user-provisioning runbook.
- [ ] Persist supplier and invoice LangGraph checkpoints in PostgreSQL; test worker kill/resume at clarification and approval interrupts.
- [ ] Add approved official OFAC, UN and EU adapters, provenance checks, refresh scheduling and stale-list blocking.
- [ ] Build at least 100 synthetic/anonymized evaluation cases and enforce every numerical extraction, retrieval, duplicate, citation and privacy gate.
- [ ] Generate contract tests from OpenAPI and versioned event JSON Schemas.
- [ ] Add Playwright journeys for clean onboarding, duplicate review, sanctions candidate, missing document, OCR correction, rejection, escalation, stale approval, cancellation and ERP retry.
- [ ] Add security fixtures for cross-tenant API/Qdrant access, malicious PDFs, prompt injection, PII leakage, SQL injection, forged/replayed approvals, expired upload URLs, unauthorized tools and audit mutation.
- [ ] Verify RabbitMQ retry/DLQ behavior under broker restart, worker death, poison messages and duplicate delivery.
- [ ] Verify notification/SMTP failure never changes or blocks case progression.
- [ ] Verify ERP timeout/replay idempotency and require explicit confirmation before completion.
- [ ] Run Python dependency audit, secret scan, image scan/SBOM and signed provenance in CI.
- [ ] Add backup/restore acceptance, failure injection, load profile and recovery runbooks.

## P1 — complete the vertical slices

- [ ] Add document-page rendering and authorized object-download endpoints with bounding-box overlays and field-correction UI.
- [ ] Generate and version the frontend client from OpenAPI; fail CI when generated contracts drift.
- [ ] Add Presidio custom financial/vendor recognizers and measure leakage on adversarial fixtures.
- [ ] Add mixed born-digital/scanned PDF page routing and calibrated OCR confidence thresholds.
- [ ] Add application OpenTelemetry spans across request, outbox, broker, worker, retrieval, LLM, object storage and ERP boundaries.
- [ ] Add clarification-task UI and durable response/resume journey.
- [ ] Add duplicate comparison and sanctions-resolution interfaces with dual-control disposition.
- [ ] Add role-specific ownership, SLA filters and saved work-queue views.
- [ ] Add authorized audit export rather than browser-only case summaries.
- [ ] Add Redis rate limiting/cache namespaces and verify tenant-key isolation.
- [ ] Replace local shared-volume object storage with S3-compatible presigned upload/download adapters; retain local storage only for developer mode.
- [ ] Consume human-confirmed invoice extraction corrections during resumed analysis.
- [ ] Require authoritative ERP/API PO and GRN data in production; keep uploaded reference documents visibly non-authoritative.

## P2 — hardening and later adapters

- [ ] Provision the optional Langfuse v3 profile with ClickHouse, Valkey and blob storage.
- [ ] Add Slack/Teams notification adapters without coupling them to case transitions.
- [ ] Add Kubernetes manifests only after the Compose acceptance profile passes.
- [ ] Reuse the verified platform for broader invoice exception and payment workflows only after all P0 gates pass.
