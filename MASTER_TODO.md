# NeuroX master acceptance TODO

Only acceptance-test-backed work may move to `VERIFIED` in `CURRENT_STATUS.md`.

## P0 — release blockers

- [ ] Run the full Compose stack and verify migration upgrade/downgrade with PostgreSQL 16.
- [ ] Add live RLS tests using non-superuser API, worker, relay and audit roles.
- [ ] Add Keycloak token/role/tenant integration tests and production user provisioning runbook.
- [ ] Persist LangGraph checkpoints with PostgreSQL and test kill/resume at clarification and approval interrupts.
- [ ] Add official OFAC, UN and EU adapter fixtures, provenance verification, refresh scheduling and stale-list blocking.
- [ ] Build at least 100 synthetic/anonymized evaluation cases and enforce every numerical gate from the recovery plan.
- [ ] Add contract tests generated from OpenAPI and versioned event JSON Schemas.
- [ ] Add Playwright journeys for clean onboarding, duplicate review, sanctions candidate, clarification, OCR correction, rejection, stale approval, cancellation and ERP retry.
- [ ] Add security fixtures for cross-tenant Qdrant access, malicious PDFs, prompt injection, PII leakage, forged/replayed approvals, expired upload URLs and audit mutation.
- [ ] Verify RabbitMQ retry/dead-letter behavior through broker and worker restarts; replace in-consumer backoff with tiered retry queues where load tests require it.
- [ ] Verify notification outages never change case progression.
- [ ] Add backup/restore test, failure injection, load profile, SBOM and signed image provenance.

## P1 — complete the vertical slice

- [ ] Add document-page rendering and authorized object-download endpoints with bounding-box overlays and field correction UI.
- [ ] Generate and version the frontend client from OpenAPI; fail CI when generated contracts drift.
- [ ] Add Presidio custom financial/vendor recognizers and measure leakage on adversarial fixtures.
- [ ] Add mixed born-digital/scanned PDF page routing and calibrated OCR confidence thresholds.
- [ ] Add application OpenTelemetry spans across request, outbox, broker, worker, retrieval, LLM, object storage and ERP boundaries.
- [ ] Add clarification-task UI and durable response/resume journey.
- [ ] Add duplicate comparison and sanctions-resolution interfaces with dual-control disposition.
- [ ] Add role-specific ownership, SLA filters and saved work-queue views.
- [ ] Add authorized audit export rather than case-summary-only browser exports.
- [ ] Add Redis rate limiting/cache namespaces and verify tenant-key isolation.
- [ ] Replace local shared-volume object storage with S3-compatible presigned upload/download adapters; retain local backend only for developer mode.

## P2 — hardening and later adapters

- [ ] Provision the optional Langfuse v3 profile with ClickHouse, Valkey and blob storage.
- [ ] Add Slack/Teams notification adapters without coupling them to case transitions.
- [ ] Add Kubernetes manifests only after the Compose acceptance profile passes.
- [x] Start invoice-exception functionality only after supplier onboarding meets all gates.
