# NeuroX Full Product Audit

**Audit date:** 2026-07-28  
**Audited branch:** `dev`  
**Audited commit:** `392c67b`  
**Product scope:** supplier onboarding and invoice exception handling  
**Audit basis:** source inspection, repository documentation, focused backend and
frontend checks, Compose configuration inspection, and comparison with the
proposal and engineering blueprint.

## 1. Executive verdict

NeuroX is **not merely a visual prototype anymore**. It contains a substantial
production-shaped implementation: a real FastAPI service, PostgreSQL models and
RLS, RabbitMQ outbox/inbox processing, MinIO document storage, local OCR
adapters, Qdrant retrieval, Keycloak integration, OPA gates, two workflow
workers, persisted HITL tasks, a mock ERP boundary, notifications, a real
API-backed Next.js interface, and a persisted application copilot.

It is also **not yet a complete or defensible end-to-end product**.

The largest risk is not missing enterprise infrastructure. The largest risk is
that a clean installation cannot yet prove the two promised workflows using the
checked-in scenarios. Important reference data is not bootstrapped, several
supplier checks described in the proposal are absent, evaluation cases are
manifests rather than executed evaluations, and there is no browser E2E suite.
The current machine also cannot run the stack because Docker is stopped and
only about 9.2 GiB of disk space is free.

### Competition readiness

| Area | Verdict | Honest interpretation |
|---|---|---|
| Architecture | **Strong but unproven live** | The boundaries are credible; many distributed-system guarantees have only unit or static evidence. |
| Supplier onboarding | **Partial** | Core document, duplicate, sanctions, policy, HITL, and ERP paths exist. Several proposal-critical supplier controls do not. |
| Invoice exception workflow | **Substantially implemented, not E2E verified** | Three-way matching, duplicate invoice, tax, bank-change, review, policy, HITL, and ERP logic exist, but clean bootstrap and live journeys are missing. |
| Agentic behavior | **Real but bounded** | Gemini can select registered tools and specialists run concurrently. This is not a free-form autonomous multi-agent swarm, and it should not be presented as one. |
| Document intelligence | **Real, partial accuracy** | Local native PDF/Docling/Tesseract/EasyOCR routing is implemented. Extraction and validation remain narrow and regex-heavy. |
| UI and explainability | **Real API-backed implementation** | Work queues, evidence, execution paths, latency, HITL, and copilot exist. They have not been browser-verified against the live stack. |
| Security controls | **Credible implementation, incomplete live proof** | RLS, tenant context, RBAC, masking, signed/versioned decisions, OPA, and audit code exist. The default automated suite does not exercise the real infrastructure. |
| Evaluation | **Not complete** | One hundred declared synthetic cases exist; there is no full materialization, execution, scoring, or threshold report. |
| Live demo readiness | **NO-GO today** | Docker is not running, reference data/bootstrap is incomplete, and the two complete journeys are not acceptance-tested. |

### The correct product story

NeuroX should be described as:

> A controlled agentic vendor-to-pay application in which an LLM plans and
> explains bounded work, specialist services execute evidence-based checks in
> parallel, deterministic controls retain authority, and humans approve
> sensitive transitions.

It should **not** be described as:

- a fully autonomous procurement replacement;
- a fully verified enterprise deployment;
- a swarm of independent autonomous agents;
- a system that has met the published numerical evaluation thresholds;
- a completed supplier and invoice product until the live acceptance journeys
  pass.

## 2. Status definitions used in this audit

| Status | Meaning |
|---|---|
| **VERIFIED** | The capability exists and an applicable focused check passed during this audit. This does not imply live distributed E2E verification unless explicitly stated. |
| **IMPLEMENTED** | Meaningful production code exists, but the real dependency or full journey was not exercised in this audit. |
| **PARTIAL** | Some path exists, but behavior, coverage, bootstrap, UX, or failure handling is incomplete. |
| **HARDCODED / DEMO ADAPTER** | The behavior is fixed, regex/template-driven, locally simulated, or manually configured. It may be acceptable for the competition if disclosed. |
| **NOT BUILT** | No production implementation was found. |
| **BLOCKED** | Verification cannot proceed because of a named environmental or external prerequisite. |

These labels are deliberately stricter than several labels in
`CURRENT_STATUS.md`. A unit test proves an implementation contract; it does not
prove a live RabbitMQ, MinIO, Keycloak, Qdrant, SMTP, OCR, Gemini, or browser
journey.

## 3. Evidence collected in this audit

### Checks that passed

| Check | Result |
|---|---|
| Backend test suite with external Gemini disabled | **82 passed, 2 skipped** |
| Frontend ESLint | **Passed** |
| Frontend TypeScript `--noEmit` | **Passed** |
| Docker Compose configuration rendering | **Passed** before the runtime status check |
| Git worktree before this audit file | Clean |

Backend command used:

```bash
cd services/api
ALLOW_EXTERNAL_LLM=false GEMINI_API_KEY= .venv/bin/pytest -q
```

The two skipped tests require a live PostgreSQL integration environment.

### Checks that could not be completed

| Check | Result |
|---|---|
| Product Compose status | **BLOCKED:** Docker daemon is not running |
| Full service health/readiness | **Not run:** product stack is down |
| Supplier live journey | **Not run** |
| Invoice live journey | **Not run** |
| Keycloak login/RBAC journey | **Not run** |
| Live MinIO/ClamAV/OCR/Qdrant/RabbitMQ/OPA/SMTP/ERP integration | **Not run** |
| Real Gemini workflow call in this audit | **Not run:** external calls were disabled for the deterministic test suite |
| Playwright browser acceptance | **Not available:** no Playwright suite exists |
| Published extraction/retrieval/duplicate metrics | **Not available:** no executable evaluation scorer/report exists |

The data volume currently has approximately **9.2 GiB free**. That is not a
safe amount for rebuilding the full image set and downloading OCR/embedding
models. This does not mean the application inherently needs 45 GiB at runtime;
Docker build layers, duplicate Python packages, model caches, database images,
and stopped images can together consume that amount during development.

## 4. High-level feature inventory

### 4.1 Platform and data safety

| Capability | Status | What exists | What remains |
|---|---|---|---|
| FastAPI business API | **VERIFIED** | Versioned case, document, run, task, knowledge, notification, analytics, audit, and admin routers exist; focused tests pass. | Exercise all endpoints against the live product profile. |
| PostgreSQL authoritative store | **IMPLEMENTED** | Broad SQLAlchemy model, Alembic history, versioned cases, tasks, events, outbox/inbox, evidence, memory, knowledge, sanctions, and audit entities. | Fresh upgrade/downgrade/re-upgrade and restore drill on the current head. |
| Tenant RLS | **IMPLEMENTED** | Transaction-local tenant context, RLS policies, and separate roles exist. | Run the live two-tenant suite on current migrations and prove worker/relay/auditor denial paths. |
| Keycloak OIDC and RBAC | **IMPLEMENTED** | PKCE frontend flow, JWT validation, role mapping, service boundaries, and bootstrap assets exist. | Live login, token refresh, role matrix, and segregation-of-duties browser tests. |
| Development authentication | **HARDCODED / DEMO ADAPTER** | Explicit developer mode can auto-provision a default identity. | Do not use it in the judged acceptance profile. The default identity combines roles that bypass a realistic separation-of-duties demonstration. |
| Transactional outbox/inbox | **IMPLEMENTED** | Atomic outbox writes, publisher confirms, inbox deduplication, manual acknowledgement, retry queues, and DLQ code exist. | Live duplicate-event, broker restart, poison message, relay death, and redelivery tests. |
| Tamper-evident audit | **IMPLEMENTED** | Audit chaining and evidence hashes exist. | Live mutation-resistance and export verification. |
| Encryption/blind indexes | **IMPLEMENTED** | Sensitive extracted values can be encrypted and matched using blind indexes. | Key rotation and recovery procedures; live log/event/trace leakage test. |
| Redis cache/rate limits | **IMPLEMENTED** | Tenant-prefixed cache/rate-limit boundaries exist. | Live outage behavior and proof that Redis loss cannot corrupt workflow truth. |
| Generated OpenAPI client | **IMPLEMENTED** | FastAPI contract export, Orval generation, and generated frontend client exist. | Browser contract journeys and CI E2E drift proof. |

### 4.2 Secure document processing

| Capability | Status | What exists | What remains |
|---|---|---|---|
| Presigned quarantine upload | **IMPLEMENTED** | MinIO/S3 initiation and completion flows, quarantine/private buckets, object metadata, hashes, and document jobs exist. | Live expired URL, duplicate upload, bad MIME/magic byte, size, malformed PDF, and encrypted PDF tests. |
| Malware scanning | **IMPLEMENTED** | ClamAV streaming scan and clean/infected state handling exist. | Live EICAR/malicious fixture and ClamAV outage tests. |
| Local OCR routing | **IMPLEMENTED** | Native PDF first, Docling, Tesseract, and EasyOCR fallback code is present in the document worker image. | Run representative born-digital and scanned PDFs and publish measured accuracy/latency. |
| Page geometry/evidence | **IMPLEMENTED** | Page dimensions, parser metadata, confidence, text blocks, and bounding-box evidence are persisted. | Verify highlights against actual rendered pages in the browser. |
| Field extraction | **PARTIAL** | Regex extraction for legal name, tax ID, bank account, SWIFT, and address. | Document classification, company registration, country, currency, dates, expiry, multiple field candidates, tables, and cross-document reconciliation. |
| Field validation | **PARTIAL** | Basic non-empty, identifier length, and SWIFT length validation. | Country-specific tax rules, IBAN checksum, BIC semantics, account/currency consistency, date/expiry logic, and calibrated field confidence. |
| OCR confidence | **HARDCODED / DEMO ADAPTER** | Parser/default confidence values and fallback thresholds are used. | Calibrate on the synthetic corpus; do not present current scores as measured probabilities. |
| Human correction | **IMPLEMENTED** | Versioned field correction endpoint and UI components exist. | Browser journey proving correction, evidence invalidation, reanalysis, and stale-decision protection. |
| PII masking | **PARTIAL** | Local regex recognizers and optional Presidio pattern recognizers cover email, phone, IBAN/SWIFT, and labeled financial/vendor identifiers. | A full Presidio analyzer/NLP pass, names/free-form addresses/national IDs, adversarial payload fixtures, and live proof across model payloads, logs, traces, and events. |
| Prompt-injection defense | **PARTIAL** | Gemini prompts state that document content is untrusted; the model has no direct SQL or credentials. | No deterministic document-instruction detector or visible `UNTRUSTED_DOCUMENT_INSTRUCTION` finding was found. Build and test one. |

Docling, Tesseract, and EasyOCR are all local components for different cases:
Docling preserves document structure, Tesseract handles common scanned pages,
and EasyOCR is a fallback for low-confidence pages. They are not three paid API
keys. Keeping them is reasonable, but their large Python/PyTorch dependencies
should remain isolated in the document-worker image.

### 4.3 Supplier-onboarding workflow

| Capability | Status | What exists | What remains |
|---|---|---|---|
| Case/document lifecycle | **IMPLEMENTED** | Supplier case creation, upload, submit, worker events, status transitions, evidence, tasks, cancellation, and SSE events. | Live journey from a new tenant through ERP confirmation. |
| Gemini planning | **IMPLEMENTED** | Structured planner selects registered capabilities; mandatory tools and dependencies are validated. | Live invalid-schema/quota/429/recovery tests and visible planner evidence in the UI. |
| Parallel specialists | **VERIFIED at unit level** | Duplicate, sanctions, and policy operations can run through the parallel executor with sibling-failure isolation. | Live timing proof and worker restart tests. |
| Duplicate vendor detection | **PARTIAL** | Normalization, similarity scoring, exact blind-index evidence, candidate persistence, and human review paths exist. | Seed/load the vendor master automatically; calibrate recall; expand address/email/phone/transliteration evidence. |
| Sanctions screening | **PARTIAL** | OFAC/UN/EU adapters, provenance, staleness, aliases, fuzzy candidates, and human resolution exist. | Configure a working official EU source, bootstrap/import datasets before demos, and add country/date/address disambiguation. |
| Policy retrieval | **PARTIAL** | Published policy documents can be chunked/indexed/retrieved and cited. | Automatically publish the included supplier policy, verify retrieval metrics, and implement version/end-date semantics. |
| Bank consistency | **NOT WIRED** | `bank_consistency` is registered as a supplier capability. | The supplier worker does not create an operation for it. Gemini may select it, but it is silently not executed. This is a P0 correctness bug. |
| Required-document completeness | **NOT BUILT** | Uploaded documents can be processed. | No proposal-level supplier document matrix or conditional requirements engine was found. |
| Cross-border/financial risk controls | **NOT BUILT** | General risk findings exist. | Currency/country risk, beneficiary mismatch, banking-country mismatch, spend thresholds, and finance-routing controls. |
| Compliance document checks | **NOT BUILT** | Policy and sanctions checks exist. | Expiry, insurance, DPA, information-security review, and certificate requirements described by the proposal. |
| Clarification | **PARTIAL** | Durable clarification tasks and resume semantics exist. | Questions are generic templates rather than field/document-specific resolution plans. |
| Evidence verification | **IMPLEMENTED** | Deterministic evidence verification plus Gemini critique and hash-bound tasks. | Live negative/adversarial proof. |
| HITL approval | **IMPLEMENTED** | Durable approval/review tasks, expected version, evidence hash, signed decisions, and SoD checks. | Browser proof with separate role identities, stale approval, rejection, and replay. |
| ERP creation | **PARTIAL / DEMO ADAPTER** | Idempotent evidence-bound mock ERP operation, OPA gate, and explicit confirmation exist. | Remove the fallback legal name `Human-approved vendor`; missing authoritative vendor data must fail closed. A real ERP adapter is outside P0/P1. |

### 4.4 Invoice-exception workflow

| Capability | Status | What exists | What remains |
|---|---|---|---|
| Invoice/PO/GRN extraction | **PARTIAL** | Template-aware regex extraction and evidence persistence exist. | Robust table/line-item extraction, more layouts, confidence calibration, and document-type validation. |
| Vendor resolution | **PARTIAL** | Vendor matching and review path exist. | Automatically load the vendor master and validate more ambiguous cases. |
| Three-way match | **IMPLEMENTED** | Invoice, PO, and GRN amounts/quantities can be compared with deterministic tolerances. | Live AP-001–AP-003 journeys and trusted-source boundary. User-uploaded PO/GRN files are currently treated as reference evidence and are not an ERP-authoritative feed. |
| Duplicate invoice detection | **PARTIAL** | Deterministic comparison with invoice history exists. | Invoice history is not seeded automatically; run and measure AP-004. |
| Tax mismatch | **IMPLEMENTED** | Deterministic tax arithmetic/check findings exist. | Jurisdiction-specific tax validation and live AP-005 proof. |
| Missing PO handling | **IMPLEMENTED** | Missing-reference findings and review/clarification paths exist. | Live AP-006 journey. |
| Bank-detail change | **IMPLEMENTED** | Bank comparison, protected review, and human decision paths exist. | Requires a seeded/resolved vendor master; run AP-007 and replay/stale-decision tests. |
| Policy retrieval | **PARTIAL** | AP policy retrieval and citations are wired. | Publish/index included AP policy automatically and meet measured Recall@10/citation precision. |
| Gemini reasoning/critique | **IMPLEMENTED** | Tokenized contradiction analysis, clarification planning, and evidence critique use structured outputs when enabled. | Real workflow quota/error/recovery tests. |
| HITL and ERP resolution | **IMPLEMENTED** | Review/approval gates, version/evidence binding, OPA, idempotent mock ERP, and confirmation flow exist. | Full role-separated browser journey and ERP timeout/retry proof. |

The invoice workflow is currently closer to a complete competition journey than
the supplier workflow. It should be stabilized first as one golden path, then
the supplier gaps should be closed.

### 4.5 RAG, CAG, agent planning, and memory

| Capability | Status | What exists | What remains |
|---|---|---|---|
| Policy ingestion | **PARTIAL** | API publication flow and chunk/index code exist. | No automatic clean-install ingestion of the included policy PDFs. |
| Parent/child chunking | **IMPLEMENTED** | Heading/section-aware parent/child metadata and chunk sizing exist. | Evaluate on the included policies and inspect citations. |
| Dense+sparse retrieval | **IMPLEMENTED** | Local MiniLM dense embeddings, BM25 sparse vectors, Qdrant fusion, filters, and reranking. | Live Qdrant tests, threshold calibration, outage behavior, and measured Recall@10. |
| Access/effective-date filtering | **PARTIAL** | Tenant, ACL, publication, and effective-date filters exist. | Expiry/supersession logic and a live test of Qdrant date-range behavior. |
| Insufficient evidence | **IMPLEMENTED** | Retrieval can fail closed instead of inventing policy support. | Calibrate thresholds and surface remediation consistently. |
| Procedural CAG | **HARDCODED / DEMO ADAPTER** | Versioned help entries, safe actions, and fallback instructions are in code. | Admin-authored/versioned publication, automated validation, and safe promotion. |
| Copilot retrieval | **PARTIAL** | Route/context-aware lexical retrieval and Gemini answer generation use persisted sessions. | It is not embedding/RAG-based FAQ retrieval. Feedback is stored but does not improve or promote CAG content. |
| Working memory | **IMPLEMENTED** | LangGraph checkpoints/current workflow state. | Live worker-kill/resume without duplicate effects. |
| Conversation memory | **IMPLEMENTED** | Tenant/user-scoped, masked recent copilot messages. | Explicit retention controls and optional user settings. |
| Semantic memory | **IMPLEMENTED** | Published tenant policy knowledge. | Clean bootstrap and evaluation. |
| Procedural memory | **PARTIAL** | Versioned prompts, schemas, workflow definitions, and fixed help pack. | Governed publication and rollback for the help pack. |
| Episodic memory | **SCHEMA ONLY** | An episodic-memory persistence entity exists. | No meaningful production retrieval/use was found. It is not required for the competition. |
| Personalization memory | **NOT BUILT** | User-scoped chat history exists. | No separate preference/profile memory. This should not be prioritized before the workflows. |
| Chain-of-thought storage | **Correctly not built** | Evidence, conclusions, citations, reason codes, and timings are persisted instead. | Continue this design; do not expose private chain-of-thought to judges or users. |

### 4.6 Agentic behavior: what is real and what is not

**What is real:**

- Gemini receives a typed capability registry and produces a structured plan.
- The application validates the plan, mandatory controls, dependencies, and
  allowlisted tools.
- Independent specialists can execute concurrently.
- Successful sibling results survive another specialist's failure.
- Deterministic checks remain authoritative.
- The graph can pause for clarification, review, approval, and ERP
  confirmation.
- Persisted events expose tool selection, evidence, reason codes, retries,
  latency, and the execution path without exposing chain-of-thought.
- Provider authentication, quota, rate-limit, invalid-output, and availability
  failures have distinct reason codes.

**What is bounded or incomplete:**

- Specialists are services/modules in the agent worker, not separately deployed
  autonomous agent processes.
- The planner makes one bounded planning decision; there is no general
  perceive-plan-act loop that repeatedly replans after every observation.
- Specialist scheduling happens outside the LangGraph subgraph; LangGraph is
  primarily used for reasoning, verification, and durable human gates.
- There is no general replan-after-tool-failure loop.
- Tool results are standardized inside parts of the graph, but not every
  specialist boundary uses the exact promised public `ToolResult` structure.
- Supplier `bank_consistency` can be selected but is not executed.
- “Multi-agent” should be demonstrated as coordinated specialist agents under a
  controlled orchestrator, not as an unrestricted autonomous swarm.

This architecture is appropriate for a high-risk B2B workflow. More autonomy is
not automatically better; the competition value comes from visible planning,
branching, parallel tool use, recovery, evidence, and meaningful HITL.

### 4.7 Frontend and user experience

| Capability | Status | What exists | What remains |
|---|---|---|---|
| Real API data | **IMPLEMENTED** | TanStack Query/generated client usage replaces the original mock business arrays and timers. | Verify every page against the live backend. |
| Dashboard/work queue | **IMPLEMENTED** | Case metrics, work queues, filters, claiming/ownership, SLA indicators, and statuses exist. | Role-by-role browser journeys and empty/error/loading-state review. |
| Supplier/invoice intake | **IMPLEMENTED** | Case forms, upload flow, submission, and progress paths exist. | Real upload/OCR journeys and validation UX. |
| Case command center | **IMPLEMENTED** | Evidence, findings, citations, documents, tasks, audit, and actions are presented. | End-user usability review and real-data bounding-box verification. |
| Execution path and latency | **IMPLEMENTED** | Projected/persisted agent step graph, status, latency, critical path, and events are displayed. | Prove that displayed timings come from live operations and remain accurate after retry/resume. |
| SSE progress | **IMPLEMENTED** | Event replay/reconnect logic and durable event IDs exist. | Browser reconnect/replay test with API restart. |
| HITL UI | **IMPLEMENTED** | Approval, review, clarification, correction, and ERP confirmation components/routes exist. | Complete role-separated journeys and stale/replayed decision tests. |
| Status accessibility | **PARTIAL** | Text/icon status chips and many non-color cues exist. | Keyboard-only, screen-reader, focus order, contrast, and responsive acceptance testing. |
| Copilot | **IMPLEMENTED, bounded** | Persisted Q&A, screen context, safe UI actions, spotlight tours, and dynamic semantic targets. It cannot approve or progress a case. | Browser verification, richer governed help content, and content-management workflow. |
| Dynamic spotlight guidance | **IMPLEMENTED** | Components self-register semantic targets; the backend returns allowlisted actions by target ID, reducing selector hardcoding. | Add registration tests and a missing-target fallback for every major route. |
| Notifications | **IMPLEMENTED** | Durable in-app records, read state, email delivery attempts, retries, and visible failure status. | Live Mailpit and SMTP outage tests proving case progression is unaffected. |
| Reports/audit export | **PARTIAL** | Reports, analytics, case data downloads, and audit endpoints exist. | Secure asynchronous audit-export journey, expiring downloads, and browser test. Some report export remains client-side. |
| Browser E2E | **NOT BUILT** | No Playwright configuration or project journey suite was found. | Implement the named VO/AP acceptance journeys. |

### 4.8 Integrations and operations

| Capability | Status | What exists | What remains |
|---|---|---|---|
| PostgreSQL/RabbitMQ/Redis/Qdrant/MinIO/Keycloak/ClamAV/OPA/Mailpit | **IMPLEMENTED in Compose** | Product profile declares the required services and workers. | Start and verify on a machine with adequate disk/RAM. |
| OCR worker isolation | **IMPLEMENTED** | Heavy OCR dependencies are isolated from the API image. | Measure actual image/cache size and document it after a clean build. |
| Mock ERP | **DEMO ADAPTER** | Persistent idempotent local ERP service for supplier creation and invoice resolution. | Disclose clearly in the demo. Real SAP/Oracle integration is not part of P0/P1. |
| SMTP | **IMPLEMENTED** | Generic STARTTLS adapter and local Mailpit path. | Real SMTP is not required for local judging; run local failure/retry acceptance. |
| OpenTelemetry | **IMPLEMENTED/PARTIAL** | Correlation and redaction hooks exist. Optional operations overlay contains observability components. | End-to-end trace proof is not required before core workflow acceptance. |
| Grafana/Tempo/Langfuse | **Correctly optional** | Operations profile, not required for core application behavior. | Defer unless all P0 workflow gates are green. |
| Backup/restore | **PARTIAL/UNVERIFIED** | Operations design/assets exist. | Live pgBackRest/WAL restore drill can be P1 after the competition workflow is stable. |
| Container CI | **IMPLEMENTED** | Dockerfile build/scan matrix and dependency/secret checks exist. | Current GitHub CI must be observed green after the merged migration/image changes. |
| Full Compose CI | **NOT BUILT** | Component checks exist. | No CI job boots the entire product and runs the two workflows. |

## 5. Scenario-by-scenario truth

The checked-in corpus is useful, but files existing in `data/synthetic/corpus`
does not mean the scenarios have passed.

| Scenario | Current status | Primary reason |
|---|---|---|
| VO-001 clean domestic supplier | **PARTIAL** | Core path exists, but policy/sanctions/reference bootstrap and live end-to-end proof are missing. |
| VO-002 near-duplicate supplier | **PARTIAL** | Duplicate logic exists; existing vendor master is not automatically loaded. |
| VO-003 cross-border/high-risk supplier | **NOT COMPLETE** | Sanctions exists, but country/currency/cross-border, expiry, insurance, and approval-matrix controls are missing. |
| VO-004 scanned/noisy supplier | **PARTIAL** | OCR path exists; no measured extraction score and no deterministic prompt-injection finding. |
| VO-005 bank mismatch/finance review | **NOT COMPLETE** | Supplier bank-consistency capability is registered but not executed. |
| AP-001 clean three-way match | **PARTIAL** | Match logic exists; no live full-stack journey. |
| AP-002 price variance | **PARTIAL** | Deterministic tolerance logic exists; no live journey or calibrated corpus report. |
| AP-003 quantity variance | **PARTIAL** | Deterministic quantity/GRN logic exists; no live journey. |
| AP-004 duplicate invoice | **PARTIAL** | Logic exists; invoice history is not bootstrapped. |
| AP-005 tax mismatch | **PARTIAL** | Arithmetic finding exists; no jurisdiction-specific or live acceptance proof. |
| AP-006 missing PO | **PARTIAL** | Missing-reference path exists; no live clarification/review journey. |
| AP-007 bank-detail change | **PARTIAL** | Protected review exists; requires loaded vendor reference data and live proof. |

## 6. Hardcoded, simulated, or manually wired register

Not every hardcoded item is fraudulent. A competition project can use explicit
demo adapters. The issue is whether the UI presents a fixed value as a live
decision or whether the team claims a capability that is not executing.

| Location | Hardcoded/simulated behavior | Risk and required action |
|---|---|---|
| `services/mock_erp/` | Local mock ERP instead of SAP/Oracle | Acceptable and necessary for P0/P1. Label it “ERP sandbox” in the demo. |
| `services/api/app/copilot.py` | Fixed `HELP_ENTRIES`, safe action map, and help-pack version | Acceptable initial CAG, but not self-updating. Add governed publication later; never let chat feedback rewrite production guidance automatically. |
| Supplier agent worker | Fixed policy query and generic clarification text | Replace with case/document-specific structured issues and resolution questions. |
| Supplier planner/worker boundary | `bank_consistency` is advertised but has no operation | P0 defect. Either implement it or remove it from the advertised registry until implemented. |
| Document extraction | Narrow regex field patterns and first-match behavior | Expand and evaluate; present as deterministic extraction, not general document understanding. |
| OCR confidence | Default/native/fallback confidence constants | Calibrate; label current values as extraction confidence heuristics. |
| Duplicate/sanctions/retrieval | Fixed similarity and evidence thresholds | Thresholds are normal, but need evaluation and versioning before claiming accuracy. |
| Development auth | One default identity can have multiple roles | Never use for the judged SoD journey. Use Keycloak users in the acceptance profile. |
| Mock ERP supplier creation | Fallback name `Human-approved vendor` | Unsafe silent fallback. Fail the operation when authoritative legal name is absent. |
| `services/api/scripts/seed.py` | Fixed synthetic tenant/users only | Expand into repeatable scenario bootstrap; keep passwords in environment/secrets. |
| Root `ingest_policies.py` | Fixed tenant UUID and `/tmp/knowledge_base/*.pdf` paths | Ad-hoc manual utility, not a product bootstrap. Replace with a checked-in CLI/API bootstrap using configuration and deterministic idempotency. |
| `evaluation/cases.jsonl` | Repeated base scenarios with mutation declarations | It is a test manifest, not 100 executed evidence cases. Build a materializer, runner, scorer, and report. |
| Invoice parser | Regex/template extraction and vendor-name heuristic | Works for the synthetic templates; broaden fixtures and disclose current coverage. |
| Uploaded PO/GRN | Treated as matching reference evidence | Fine for a synthetic competition workflow, but not equivalent to an authoritative ERP PO/receipt feed. Mark source provenance. |
| UI projected execution path | Can show planned/projected nodes before completion | Valuable UX if visually distinguished. Never present projected duration as measured latency. |

## 7. Missing clean-install data and automation

This is the most immediate end-to-end blocker.

The current seed script creates a synthetic tenant and local users, but it does
not automatically load:

- `existing_vendor_master.csv`;
- `existing_invoice_history.csv`;
- the supplier policy PDF;
- the invoice/AP policy PDF;
- initial knowledge publication and Qdrant indexing;
- sanctions datasets and entries;
- deterministic scenario-to-user/role assignments.

The corpus README instructs the developer to load some of these resources
manually. The root policy-ingestion script uses a fixed tenant and `/tmp` paths
and is not invoked by Compose. Therefore a fresh `product-up` can be healthy
while named business scenarios still fail or block for missing evidence.

Required fix:

1. Create one idempotent `demo-bootstrap` command.
2. Create the synthetic tenant and role-separated users.
3. Load vendor and invoice history reference data.
4. Publish both policy PDFs through the real knowledge API/service.
5. Wait for Qdrant indexing and verify retrieval.
6. Import official sanctions data or fail with one explicit setup message.
7. Create, upload, and submit scenarios only through public product interfaces.
8. Print a readiness report without secrets.

This is infrastructure only where it enables functionality; it is not
enterprise ceremony.

## 8. Test and evaluation truth

### What the current tests prove

- Pure/domain state transitions and deterministic calculations have meaningful
  coverage.
- API contracts, authorization branches, idempotency, evidence hashing,
  masking, planning validation, graph branching, specialist sibling isolation,
  analytics, and several worker behaviors have focused tests.
- The frontend lints and type-checks.
- The repository has migration, RLS, contract, secret, dependency, and container
  CI jobs.

### What they do not prove

Many tests replace infrastructure using SQLite, mocks, `MockTransport`, or
monkeypatching. The passing suite does not prove:

- real RabbitMQ retries/DLQs/publisher confirms;
- real MinIO presigned upload and quarantine transitions;
- real ClamAV scanning;
- actual Docling/Tesseract/EasyOCR processing;
- real Qdrant hybrid retrieval and filtering;
- Keycloak PKCE and role behavior;
- real OPA policy decisions;
- live Mailpit/SMTP retry independence;
- worker death and LangGraph checkpoint recovery;
- mock ERP timeout and idempotent recovery;
- real Gemini planning/critique in both workflows;
- browser usability or accessibility;
- the numerical acceptance thresholds.

### The “100 cases” gap

The repository contains a reproducible 100-entry evaluation manifest. That is a
good start, but it does not currently:

- materialize all declared mutations into documents/reference data;
- submit the cases through the actual API;
- wait/resume through human tasks;
- call real Gemini for full-agent cases;
- compute field macro F1;
- compute duplicate recall/exact-match accuracy;
- compute policy Recall@10 and citation precision;
- test cross-tenant leakage;
- emit an evidence-linked pass/fail report.

Until that runner exists and passes, do not claim the thresholds in the plan.

## 9. Security and privacy gap register

| Risk | Current control | Remaining proof/fix |
|---|---|---|
| Cross-tenant access | Tenant IDs, RLS, auth scopes, Qdrant filters, object keys, cache prefixes | Live two-tenant API/worker/retrieval/object tests on current schema. |
| LLM data leakage | Tokenized minimal schemas, masking gateway, external LLM default-off, no raw document payload intent | Adversarial fixtures across prompts, logs, traces, events; expand PII detection. |
| Prompt injection | Untrusted-context prompt and typed/allowlisted tools | Deterministic injection detector, visible finding, malicious-document acceptance test. |
| Unauthorized workflow action | Deterministic state machine, version/evidence binding, SoD, OPA | Live forged/replayed/stale human decisions and OPA outage. |
| Unauthorized ERP write | Evidence-bound idempotency and independent OPA check | Remove fallback supplier name; live timeout/retry/duplicate request. |
| Audit manipulation | Hash chain and append-only intent | Live DB role tests and mutation detection/export verification. |
| Malicious document | Quarantine, MIME/magic checks, page limits, ClamAV | Live EICAR, malformed/encrypted/oversized files and parser timeout. |
| Sanctions false pass | Required sources/staleness and human resolution | Working EU official source, import bootstrap, metadata-rich disambiguation, outage test. |
| Notification outage | Asynchronous delivery/retries separate from case state | Live SMTP failure proof. |

## 10. Documentation and repository hygiene findings

1. `CURRENT_STATUS.md` is useful but several **VERIFIED** labels mean
   “unit-tested implementation,” not “live full-stack verified.” It should
   include an evidence-level column or use the stricter labels in this audit.
2. `MASTER_TODO.md` correctly retains many acceptance blockers and is closer to
   the true release state.
3. `LOG.md` records frontend-only smoke and past provider/import smoke, but no
   full two-workflow Compose acceptance.
4. `README.md` appropriately says the project is not release-ready; retain that
   honesty.
5. Two Git remotes point to the same repository, and local `dev` tracks the
   stale `vendrai/dev` reference even though `origin/dev` matches the audited
   commit. This causes the misleading “ahead 32” status. Fix the upstream before
   the next PR.
6. `.DS_Store` files are tracked and should be removed in a dedicated hygiene
   change.
7. The root `ingest_policies.py` is an ad-hoc script and should be replaced by
   the supported bootstrap path.
8. The official Gemini documentation currently lists
   `gemini-3.6-flash` as a stable model and documents structured output support.
   Keep the model configurable and pinned; do not depend on an undocumented
   alias. See the official [Gemini 3.6 Flash documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash).

## 11. P0: work required before the live competition demo

These items are ordered by product value, not enterprise fashion.

### P0.1 — Make a clean installation produce a working product

- Start Docker and free enough disk for one clean build.
- Build the idempotent synthetic demo bootstrap described above.
- Publish/index both policies.
- Load vendor and invoice history.
- Import and verify all required sanctions sources.
- Provide one command that ends with health plus business-readiness checks.

**Acceptance:** a clean clone plus `.env` can reach a ready state without
manual SQL, copying files to `/tmp`, or editing source constants.

### P0.2 — Finish the supplier workflow promised in the proposal

- Wire and test `bank_consistency`.
- Add required-document rules and explicit missing-document clarification.
- Add country/currency/cross-border and bank-beneficiary mismatch checks needed
  by VO-003/VO-005.
- Add certificate/expiry checks required by the selected demo scenarios.
- Generate case-specific clarification questions from structured missing or
  contradictory evidence.
- Remove the mock ERP legal-name fallback and fail closed.

**Acceptance:** VO-001, VO-002, VO-004, and VO-005 complete through real
uploads, real checks, real Gemini, human decisions, and ERP confirmation.
VO-003 must either be implemented or removed from the promised demo scope.

### P0.3 — Stabilize one complete invoice journey, then all AP scenarios

- Run AP-001 first as the golden path.
- Run AP-002–AP-007 using bootstrapped reference data.
- Distinguish uploaded reference documents from authoritative ERP data in
  evidence/provenance.
- Verify duplicate, tax, missing PO, bank-change, and tolerance paths.

**Acceptance:** the UI and audit log show actual input-derived evidence, planner
selection, parallel timings, human control, and idempotent ERP result.

### P0.4 — Add real browser acceptance

- Add Playwright configuration and synthetic fixtures.
- Cover login, intake/upload, SSE progress, execution map, clarification,
  correction, duplicate review, sanctions review, approval, stale decision,
  ERP confirmation, notifications, and copilot spotlight.
- Run role-separated Keycloak users.
- Capture screenshots/traces only as test artifacts, never as a substitute for
  the live product.

**Acceptance:** at least one supplier and one invoice golden journey pass from
the browser after a clean stack start.

### P0.5 — Prove failure behavior that judges can ask about

- One specialist failure while siblings succeed.
- Gemini invalid key/quota/rate-limit with deterministic work preserved.
- SMTP outage with no case-state change.
- ERP timeout followed by idempotent retry.
- Qdrant outage producing visible insufficient evidence instead of PASS.
- Worker restart at a human interrupt without duplicate side effects.

**Acceptance:** UI reason codes, retry state, evidence, and audit trail match
the actual failure.

### P0.6 — Produce an honest judge console

Expose only redacted evidence:

- goal and selected capability plan;
- why a tool was selected or skipped;
- parallel execution branches and measured latency;
- tool status, provider/parser/data version, and citations;
- deterministic reason codes and blocked transition;
- human interrupt/resume;
- retry and recovery;
- evidence hash and final ERP confirmation.

Do not display chain-of-thought, credentials, raw OCR, bank/tax values, signed
URLs, or internal prompts.

## 12. P1: build after the two golden journeys are stable

1. Materialize and execute the 100-case evaluation suite.
2. Add metric scoring and evidence-linked reports for all required thresholds.
3. Expand document layouts, table extraction, validation, and confidence
   calibration.
4. Add full live infrastructure integration and chaos suites.
5. Add governed CAG/help publication and rollback.
6. Add richer sanctions metadata/disambiguation.
7. Add accessibility and responsive-browser acceptance.
8. Add asynchronous audit export and expiring downloads.
9. Add backup/restore verification.
10. Tune throughput and worker concurrency after measuring real bottlenecks.

## 13. Work that should be deferred

Do not let these items delay the functional demo:

- Kubernetes manifests;
- large-scale Grafana/Tempo dashboards;
- Langfuse self-hosting;
- cloud OCR;
- Slack/Teams notification adapters;
- real SAP/Oracle integration;
- episodic case memory;
- automatic personalization;
- ML anomaly models beyond clearly labeled shadow signals;
- production backup RPO/RTO certification;
- large-scale load testing beyond the competition concurrency target.

The current PostgreSQL, RabbitMQ, MinIO, Qdrant, Keycloak, OPA, local OCR,
Gemini, mock ERP, Mailpit, and Next.js boundaries are enough. The correct next
step is to make them execute the promised functions reliably, not add more
technology.

## 14. What the project owner must provide

For local competition development:

1. Start Docker Desktop.
2. Free at least roughly 25–35 GiB before a clean image/model build. Exact usage
   should be measured after the build.
3. Keep `GEMINI_API_KEY` only in the root `.env`.
4. Confirm the Gemini project has API access and enough quota.
5. Permit downloads from official sanctions sources and model repositories.
6. Configure an official EU sanctions source URL if the current default is
   absent.
7. Use only the checked-in synthetic data.

No additional paid API key is inherently required for:

- PostgreSQL;
- RabbitMQ;
- Redis;
- MinIO;
- Qdrant;
- Keycloak;
- ClamAV;
- OPA;
- Mailpit;
- Docling;
- Tesseract;
- EasyOCR;
- local embedding/reranker models;
- mock ERP.

Those components run locally in Docker. SMTP credentials are needed only when
testing a real external mail server; Mailpit needs no paid account. Official
sanctions downloads normally do not require an API key.

## 15. Definition of demo-ready

The project is demo-ready only when all of the following are true:

- [ ] A clean product start and demo bootstrap succeed.
- [ ] Health and business-readiness checks are green.
- [ ] Both policies are published and retrieval returns correct citations.
- [ ] OFAC, UN, and EU datasets are present, current, and traceable.
- [ ] One supplier and one invoice journey pass through the real browser.
- [ ] At least one branch demonstrates real parallel specialist execution.
- [ ] At least one branch demonstrates a meaningful human interrupt/resume.
- [ ] At least one recoverable failure is shown without hiding or faking it.
- [ ] Gemini is called using tokenized synthetic context and its provider/model
      version is visible.
- [ ] No unmasked sensitive fixture enters model payloads, logs, events, or
      traces.
- [ ] ERP operations are evidence/version/OPA bound and explicitly confirmed.
- [ ] Notification failure is independent of case progression.
- [ ] The UI distinguishes planned timing from measured latency.
- [ ] The audit trail can explain every transition using evidence and reason
      codes.
- [ ] Frontend lint/type/build, backend tests, current migrations, contracts,
      and Playwright golden journeys pass.

## 16. Final assessment

The team did not “ruin” the project by using enterprise patterns. Several of
those patterns—tenant isolation, durable human decisions, evidence hashes,
idempotency, outbox/inbox, fail-closed controls, and privacy boundaries—make the
product credible.

The project became risky when architectural breadth moved ahead of scenario
completion and acceptance evidence. The recovery is therefore straightforward:

1. stop adding platforms;
2. automate reference-data/bootstrap;
3. close the supplier-domain gaps;
4. run two complete live journeys;
5. add browser and failure acceptance;
6. then execute and score the larger evaluation suite.

At the audited commit, NeuroX is a **credible product-shaped beta with real
agentic components**, but it is **not yet a fully completed or live-verified
end-to-end product**.
