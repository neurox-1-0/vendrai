# NeuroX master acceptance TODO

Only acceptance-test-backed work may move to `VERIFIED` in
`CURRENT_STATUS.md`.

## Competition delivery track

The controlling competition sequence is
[`docs/competition/COMPETITION_PRODUCT_BUILD_PLAN.md`](./docs/competition/COMPETITION_PRODUCT_BUILD_PLAN.md).
Until the competition build passes, prioritize:

1. The complete functional product profile, with optional operations isolated.
2. Live projection and durable reconciliation for the implemented dynamic,
   failure-isolated specialist fan-out/fan-in.
3. Complete supplier and invoice browser journeys.
4. Execution-map, evidence, HITL, recovery, and diagnostic UX.
5. The bounded application copilot and guided spotlight experience.
6. Rehearsal, evaluation, security checks, and judge preparation.

Do not add unrelated enterprise infrastructure before these gates are complete.

## Competition capabilities implemented in the current working tree

- [x] Add Gemini goal planning with an allowlisted capability registry,
  prerequisite/dependency validation and visible planner failures.
- [x] Execute eligible supplier and invoice specialists concurrently and retain
  successful siblings when another specialist raises an exception.
- [x] Persist real execution steps, rationale, dependencies, attempts, typed
  failures, start/end times, critical path and parallel time saved.
- [x] Add a case execution map and sanitized auditor/admin diagnostics drawer.
- [x] Add a separate read-only copilot with masked tenant/user-scoped history,
  versioned CAG, live authorized case context, self-registering semantic UI
  targets, allowlisted actions, accessible guided tours and versioned
  tenant-scoped feedback.
- [x] Regenerate OpenAPI/Orval contracts and add copilot/graph contract tests.
- [x] Keep all functional services in `product-up`, while moving only
  telemetry dashboards and continuous WAL backup into `operations-up`.

## Implemented on `dev` plus the current CI-recovery branch

- [x] Rebuild the P0/P1 database model and reversible migration chain.
- [x] Add least-privilege database roles, transaction tenant context and RLS.
- [x] Add Keycloak PKCE/RBAC and secret-driven synthetic acceptance users.
- [x] Add MinIO quarantine/private buckets, presigned uploads and ClamAV gating.
- [x] Add per-page native/Docling/Tesseract/EasyOCR routing and local PII masking.
- [x] Add parent/child policy ingestion, dense+sparse retrieval, RRF and reranking.
- [x] Add versioned OFAC/UN/EU adapters with provenance and stale-list blocking.
- [x] Consolidate supplier and invoice execution into durable PostgreSQL-backed LangGraphs.
- [x] Add real Gemini structured contradiction, clarification and evidence critique.
- [x] Add deterministic duplicate, sanctions, PO/GRN, policy and evidence controls.
- [x] Put OPA in the ERP authorization path and fail closed on stale evidence,
  unresolved controls, unsafe state or segregation-of-duties failure.
- [x] Add clarification, control review, final approval and ERP confirmation interrupts.
- [x] Add idempotent mock ERP and independent durable notification retries.
- [x] Add versioned event contracts, outbox/inbox reliability and durable SSE replay.
- [x] Add generated OpenAPI/Orval contracts and drift gates.
- [x] Replace mock frontend data with real work queues, documents, corrections,
  clarifications, reviews, evidence, notifications and admin integration health.
- [x] Add correlated OpenTelemetry, Tempo/Prometheus/Grafana configuration and source redaction.
- [x] Add pgBackRest/WAL object-storage backup configuration and restore runbook.
- [x] Add a reproducible 100-case synthetic evaluation manifest.
- [x] Add CI gates for lint, typing, tests, migrations, live RLS/checkpoints,
  contracts, dependency audits, SBOM, image scan and secret scan.
- [x] Freeze historical Alembic revisions, add a mutable-metadata regression
  test, patch stale runtime bases and repair the frontend container build.

## P0 — acceptance blockers before PR to `dev`

- [ ] Owner: free enough workstation space for the complete
  OCR/model/security product build. Current free space fell to approximately
  3.5 GB during CI image reproduction, with no complete NeuroX OCR/retrieval
  image cached. Allow 25–35 GB for the
  product build; 45–50 GB remains the safe target for operations and repeated
  evaluation runs.
- [x] Add a local environment bootstrap that preserves the Gemini key,
  generates internal service/database/Keycloak/MinIO/Grafana secrets and never
  commits `.env`.
- [x] Execute the bootstrap and verify that the actual `.env` resolves the
  Compose configuration without exposing secret values.
- [ ] Launch `./scripts/stack.sh product-up` and verify every health check.
- [ ] Pull the pinned OPA image, run `opa check`, and exercise allow/deny/outage
  decisions; the current Docker registry CDN DNS lookup failed.
- [ ] Run clean supplier onboarding and invoice exception journeys with real Gemini.
- [ ] Verify Keycloak tokens, roles, tenant claims, PKCE and segregation of duties.
- [ ] Verify MinIO presigned expiry, tenant object isolation, ClamAV malicious files
  and archive-bomb/page/size rejection.
- [ ] Verify RabbitMQ broker restart, worker death, duplicate events, poison
  messages, retry tiers and DLQs.
- [ ] Kill/restart workers at clarification, control-review, approval and ERP
  confirmation interrupts and prove no successful step repeats.
- [ ] Configure an approved official EU sanctions export and run live OFAC/UN/EU refresh.
- [ ] Publish the two synthetic policy PDFs and run live Qdrant tenant/ACL/date tests.
- [ ] Materialize and execute 50 supplier plus 50 invoice cases through real services.
- [ ] Enforce extraction F1, duplicate recall, exact identifier, Recall@10,
  citation precision, tenant isolation, ERP authorization and PII leakage thresholds.
- [ ] Run Playwright journeys VO-001–VO-005 and AP-001–AP-007 with accessibility checks.
- [x] Make active specialist `RUNNING` states visible before the durable worker
  transaction commits, then reconcile with persisted `AgentStep` records.
- [ ] Run malicious PDF, prompt injection, SQL injection, forged/replayed decision,
  expired URL, unauthorized tool and audit-mutation security tests.
- [ ] Run Gemini invalid key, quota, 429, invalid schema and outage recovery tests.
- [ ] Run SMTP outage and ERP timeout/replay acceptance.
- [ ] Run 10-concurrent-workflow latency/load profile.
- [ ] Perform encrypted pgBackRest backup and isolated restore; record measured RPO/RTO.
- [ ] Push `fix/ci-migrations-images`, rerun GitHub CI and verify every
  migration/build/SBOM/Trivy job. The known migration, stale-base and empty
  frontend build-argument failures are fixed locally.
- [ ] Open the CI-recovery PR into `dev` after the rerun is green.

## P1 — operational completion gates

- [ ] Validate bounding-box highlights and corrected-field resume in real browser journeys.
- [ ] Validate saved queue filters, claiming/releasing and SLA status behavior across roles.
- [ ] Validate audit export authorization, expiry and downloaded hash.
- [ ] Inspect live traces end to end and prove no PII, prompt, signed URL or SQL leakage.
- [ ] Validate Redis tenant-prefixed rate-limit/cache isolation.
- [ ] Publish operator runbooks for user provisioning, sanctions refresh, DLQ replay,
  provider quota recovery and key rotation.

## VPS acceptance — owner inputs

- [ ] Ubuntu 24.04 x86_64 VPS: at least 8 vCPU, 32 GB RAM and 200 GB disk.
- [ ] SSH access and a domain DNS record pointing to the VPS.
- [ ] Server-side SMTP host, port, username, password and verified From address.
- [ ] Production-generated service/database/encryption secrets.
- [ ] Gemini project quota/billing suitable for the 100-case run.
- [ ] Deploy only the release that passed local and CI acceptance.

## Later work

- [ ] Correctly provision optional Langfuse v3 with ClickHouse, Valkey and blob storage.
- [ ] Add Slack/Teams adapters without coupling them to case transitions.
- [ ] Add Kubernetes manifests after Compose acceptance is proven.
- [ ] Replace mock ERP and synthetic identity only through separately scoped integrations.
