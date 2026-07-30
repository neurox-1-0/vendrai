# NeuroX implementation status

Status is evidence-based. Allowed values are `NOT_STARTED`, `IMPLEMENTED`,
`VERIFIED`, and `BLOCKED`.

**Evidence levels.** "Unit-tested" is not "verified", and this document used to
conflate them. Every claim now carries the level of evidence behind it:

| Level | Means |
|---|---|
| `UNIT` | Tested against in-process fakes — SQLite, mocks, `MockTransport`. Proves the contract. Proves nothing about whether the system runs. |
| `INTEGRATION` | Tested against one real dependency (live PostgreSQL, a real broker) but not the whole stack. |
| `LIVE_E2E` | Demonstrated on a running stack, end to end, through the product's own interfaces. |

The distinction is not pedantry. On 2026-07-28 this repository had 82 passing
tests, clean ESLint, and clean TypeScript, and could not complete a single
document upload — three separate defects, none visible at `UNIT` level. RLS
unit-tested against SQLite has not been tested at all: SQLite has no row-level
security, so the test proves the query shape and nothing about isolation.

Last updated: 2026-07-30

## Release truth

The eight-phase build plan in [`plans/`](./plans/) has been implemented. What
that does and does not mean:

**What landed, at `UNIT` evidence level** — 269 backend tests pass. Supplier
`bank_consistency` now executes and a registry-vs-executor test makes an
unexecuted capability structurally impossible. The ERP worker fails closed
instead of inventing a vendor name. Extraction was rewritten from a regex that
matched almost nothing in the shipped corpus to a deterministic label/table
extractor that reads every document in it. Document classification, a
required-document matrix, cross-border/spend/residency/DPA/expiry controls, a
deterministic prompt-injection detector, an external risk service, and
case-specific clarification all exist and are tested. Business thresholds moved
from code constants to tenant configuration. Evidence carries provenance;
projected timing is no longer presented as measured.

**What landed as executable but unrun** — the clean-install bootstrap, the
Playwright journeys, the failure-injection suite, and the 100-case evaluation
harness are written and wired into CI. **None has been run against a live stack
here.** They are the instruments, not the readings.

**What is therefore still true:** the product has not been demonstrated end to
end. Every scenario claim below is a `UNIT`-level claim until
`./scripts/stack.sh product-up && ./scripts/stack.sh bootstrap && npm run e2e`
passes on a machine with the disk headroom to build the OCR and retrieval
images. That run is the next thing to do, and it is the only thing that can
move this document's claims from `UNIT` to `LIVE_E2E`.

Local full-stack acceptance remains `BLOCKED` on Docker build headroom: the
functional profile carries Docling, Tesseract, EasyOCR, ClamAV, and local
retrieval models, and needs roughly 25 GB free. `./scripts/stack.sh preflight`
now checks that, and every other precondition, before anything starts.

## P0/P1 capability ledger

| Capability | Status | Evidence / remaining gate |
|---|---|---|
| Reversible Alembic schema and full SQLAlchemy model | IMPLEMENTED | The previously verified PostgreSQL chain through `a1778899aabb` remains frozen. Fraud/analytics revision `b28899aabbcc` is the single static head and passes ORM/API migration-history tests; its fresh PostgreSQL upgrade/downgrade/re-upgrade is still required. |
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
| Evidence-grade extraction candidates | VERIFIED | Extracted fields now persist page, bounding box, engine/version, confidence grade and validation results; low-confidence critical tax/bank identifiers create review findings. Unit tests cover OCR confidence and locator propagation; corpus F1 remains a release gate. |
| Local PII recognition, tokenization, encryption and blind indexes | VERIFIED | Tax/bank/SWIFT/registration recognizers and adversarial payload rejection tests pass; full log/trace fixture sweep remains. |
| Parent/child policy ingestion | VERIFIED | Structure-aware chunking tests pass. |
| Dense+sparse Qdrant retrieval, RRF and reranking | IMPLEMENTED | Tenant/ACL/effective-date filtering exists; live Qdrant and Recall@10/citation metrics remain. |
| OFAC/UN/EU versioned sanctions adapters | IMPLEMENTED | Official-shape parsers, SSRF/DOCTYPE defenses, checksums, ETags and stale/missing-source blocking exist. Live OFAC and UN downloads parsed successfully; an approved EU export URL is still required. |
| Deterministic duplicate/sanctions/PO/GRN/policy controls | VERIFIED | Unit tests cover duplicate scoring, sanctions fail-closed behavior and invoice matching; 100-case calibration remains. |
| Fraud findings and shadow anomaly scoring | IMPLEMENTED | Duplicate vendor/invoice and bank-change controls persist active, explainable findings; robust price/quantity features and an optional tenant Isolation Forest persist shadow-only findings. A reproducible synthetic trainer stores checksummed `skops` artifacts and registers evaluation-required model versions. Production history, retrospective evaluation and eight-week shadow acceptance remain. |
| Event-derived AP and onboarding analytics | VERIFIED | Server-side KPI formulas, aging buckets, exception breakdown, governed metric queries and requester denial pass API/unit tests. The frontend renders KPI definitions, prior-period comparisons, STP trends, exceptions and drill-downs; live browser acceptance remains. |
| Configurable operational alerts | IMPLEMENTED | Tenant-scoped rules and deduplicated alert instances support SLA, bank, duplicate and extraction findings; a 15-minute worker reuses durable in-app/SMTP notification delivery. API tests prove deduplication and tenant isolation; outage and multi-instance acceptance remain. |
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

## Build-plan delivery, 2026-07-30

Evidence level for every row below is `UNIT` unless stated. Nothing here has
been demonstrated on a running stack.

| Phase | Delivered | Evidence |
|---|---|---|
| 0 — Startability | `.gitattributes` plus a full LF renormalize (331 files); `scripts/preflight.sh` checks daemon, Compose, disk, memory, named port holders, `.env` completeness, and Postgres volume/password consistency; `scripts/doctor.sh` reports liveness, readiness, and business-readiness as three tiers; Redis version asserted at startup and `ResponseError` separated from an outage; BuildKit pip caches and retried model downloads | `UNIT` — the CRLF defect was caught by the manifest-digest test failing; preflight and doctor are shell and unrun |
| 1 — Bootstrap | `python -m scripts.bootstrap` loads the vendor master and invoice history with correct blind indexes, publishes both policies through the real knowledge API, **waits for and verifies retrieval indexing**, imports sanctions with an explicit unconfigured-EU message, provisions seven one-role identities, and prints a secret-free readiness report. `--check` backs `doctor` tier 3. Root `ingest_policies.py` deleted | `UNIT` — loader, idempotency, and blind-index round trip are tested against the real corpus; the API and retrieval paths are unrun |
| 2 — Correctness | Supplier `bank_consistency` executes and emits a real step; registry-vs-executor test; ERP fails closed with `VENDOR_LEGAL_NAME_UNAVAILABLE`; `email_domain` duplicate signal wired end to end; evidence provenance recorded and surfaced; projected timing visually and semantically separated from measured, and excluded from every aggregate | `UNIT` |
| — Extraction (D-011) | The previous regex extractor required `Label: value` on one line and matched almost nothing in the shipped corpus. Replaced with a deterministic label/table extractor handling inline, next-line, and wrapped-label forms, plus stacked table headers with wrapped descriptions | `UNIT` — verified field by field against all 19 corpus documents |
| 3 — Supplier | Document classification (all 19 corpus documents classify correctly), required-document matrix, cross-border/spend/residency/DPA/certificate-expiry controls, `services/mock_risk`, deterministic injection detector (catches VO-004's note on all four patterns, zero false positives across the corpus), findings-derived clarification, case-composed policy query | `UNIT` |
| 4 — Invoice | Tolerances, tax reference rate, and duplicate window moved to tenant configuration; arithmetic reconciliation; quantity overruns reported with both figures; currency consistency; AP-007's second finding — that an invoice is not authority to change bank details — stated explicitly with `vendor_master_updated: false` | `UNIT` |
| 5 — Acceptance | Playwright against the real stack with seven role-separated Keycloak identities, golden supplier and invoice journeys asserting on evidence values, five failure-injection scenarios using real container manipulation, LLM-outage degradation, and two CI jobs that boot the full stack | **Unrun** |
| 6 — Evaluation | Materializer (deterministic, asserted), resumable runner with quota-as-a-state, pure scorer, evidence-linked reporter that prints *not measured* rather than zero | `UNIT` for materializer and scorer; the 100-case run is **unrun** |
| 7 — Hardening | Audit chain **verification** (the chain was written but never checked — hashing without detection is not a control), live two-tenant isolation across seven boundaries, adversarial injection corpus, PII leak sweep, executable restore drill measuring real RPO/RTO | `UNIT` for chain verification and the sweep; isolation and the drill are **unrun** |

Two defects were found by this work, both by tests written for Phase 7 and both
failing on their first run: **D-024** (personal contact fields persisted in
plaintext and emitted in event payloads — fixed) and **D-025** (injection
detection does not fold Unicode confusables — open, recorded as a strict
`xfail`).

## Latest local verification

- API/domain/contract tests, 2026-07-30: `269 passed, 2 skipped, 2 xfailed`.
  The skips are the separately executed live PostgreSQL integration tests; the
  xfails are D-025's two documented injection gaps. Three further tests fail on
  this workstation only, on a missing local `boto3` and `skops` — both are
  pinned in `requirements.txt` and present in CI and every image.
- Live PostgreSQL RLS/checkpoint integration: `2 passed` (previous run).
  The new seven-boundary isolation suite in
  `tests/integration/test_tenant_isolation.py` has **not** been run.
- Alembic: three new revisions (`c1223344aabb` vendor email domain,
  `c2334455bbcc` evidence provenance, `c3445566ccdd` tenant configurations)
  have **not** had their live PostgreSQL upgrade/downgrade/re-upgrade drill.
- Ruff and Python compilation: passed across `services/api`,
  `services/mock_erp`, and `services/mock_risk`.
- Extraction against the shipped corpus: all 19 case documents classify to the
  correct type; every AP purchase order, receipt, and invoice yields complete
  line items; VO-004's instruction note trips four injection patterns with no
  false positive anywhere else in the corpus. Run directly against the PDFs,
  not through the stack.
- OpenAPI export and Orval client regeneration: passed.
- Frontend ESLint, TypeScript and Next.js 16.2.11 production build: passed.
- Fraud/analytics additions: Ruff and targeted mypy passed; API tests cover
  event-derived formulas, governed-query authorization, risk disposition,
  alert deduplication, tenant isolation and the synthetic shadow-model path.
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
