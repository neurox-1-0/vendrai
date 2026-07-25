# Vendrai Competition Product Build Plan

## 1. Outcome

Build two complete, live workflows from user-provided synthetic documents and
real service responses:

1. Supplier onboarding.
2. Invoice exception resolution.

The demonstration must prove:

- Context-sensitive planning and routing rather than one fixed path.
- Real parallel specialist execution where dependencies permit.
- Real Gemini structured reasoning, not pre-generated output.
- Durable clarification, review, approval, and ERP-confirmation pauses.
- Evidence-backed explanations without displaying private chain-of-thought.
- Failure recovery and visible partial results.
- A polished interface usable by procurement and finance staff.
- An application copilot that explains and guides, but cannot approve or
  progress a case.

The existing enterprise platform remains the foundation. Competition work now
prioritizes a dependable product experience over adding more infrastructure.

## 2. Honest current baseline

### Already usable

- Real supplier and invoice API surfaces.
- Secure document upload, scanning, extraction, local PII handling, evidence,
  notifications, audit records, and ERP sandbox operations.
- Real Gemini structured contradiction analysis and evidence critique.
- PostgreSQL-backed LangGraph checkpoints and durable human interrupts.
- Deterministic duplicate, sanctions, policy, PO/GRN, evidence, authorization,
  and ERP safety controls.
- Real frontend API calls, work queue, document correction, clarification,
  review, approval, evidence, and SSE refresh.
- A real Gemini goal planner constrained by a server-side capability registry
  and dependency validator.
- Failure-isolated parallel supplier and invoice specialist execution with
  persisted start/end times, attempts, route rationale, typed errors and
  critical-path timing.
- A case execution map and an auditor/admin diagnostics drawer sourced from
  persisted run data.
- A separate, read-only application copilot with tenant/user-scoped masked
  history, versioned CAG, authorized case context and allowlisted
  navigation/spotlight/tour actions.

### Competition-critical gaps

- The orchestration boundary is intentionally hybrid: the worker scheduler runs
  validated I/O specialists and records them as first-class `AgentStep`s; the
  PostgreSQL-checkpointed LangGraph owns bounded reasoning, verification, HITL
  and ERP confirmation. This is visible as one combined execution graph, but
  the specialist scheduler is not itself a LangGraph subgraph.
- Specialist results are durable, but intermediate `RUNNING` step projections
  are not yet committed while the long worker transaction is active. The UI
  polls and updates when durable steps commit; true sub-step live streaming
  remains a release gate.
- Neither workflow has passed a full live browser journey on the complete
  Compose stack.
- The 100-case manifest exists, but the documents and numerical evaluation run
  are not complete.
- The local `.env` is missing required service credentials and Docker access
  could not be approved in the current Codex session. Approximately 4.9 GB is
  free, still below the safe allowance for the OCR/model/observability stack.

## 3. Product boundaries

### Proposal traceability

The competition build remains accountable to
`Proposal/refined_vendor_to_pay_agent_report.tex`:

| Proposal commitment | Competition implementation proof |
|---|---|
| Supplier onboarding and invoice exception handling | Both workflows complete through the browser and ERP sandbox |
| Supervisor orchestration | Planner plus validated capability registry |
| Specialist agents | Separate typed document, entity, sanctions, policy, PO/GRN, match, reasoning, evidence, and verifier executions |
| Parallel investigation | Persisted overlapping step intervals and UI swimlanes |
| Dynamic agentic loop | Different evidence produces different planned routes, clarification, retry, or review |
| Ambiguity handling | Confidence, contradiction, and insufficient-evidence paths |
| Structured recovery | Typed errors, bounded retries, retained sibling work, durable resume |
| Evidence Builder and Verifier | Evidence packet, citation checks, hash, deterministic verification, and critique |
| Meaningful HITL | Duplicate, sanctions, bank, final approval, and ERP gates |
| ERP execution after approval | OPA-authorized idempotent sandbox operation with explicit confirmation |
| Agent trace UI | Live graph, path rationale, latency, attempts, evidence, and sanitized diagnostics |
| Measurable MVP | Browser journeys, agentic-path proofs, extraction/retrieval metrics, safety and latency gates |

### What is genuinely agentic

The orchestrator and reasoning agents may:

- Select eligible specialist agents from an allowlisted capability registry.
- Choose additional evidence or policy retrieval.
- Ask targeted clarification questions.
- Retry or substitute a provider within configured limits.
- Route to a required human control.
- Revise a plan when evidence is missing, contradictory, or low-confidence.
- Stop with `INSUFFICIENT_EVIDENCE` or a provider-specific blocker.

### What remains deterministic

The model cannot:

- Change tenant or role permissions.
- Clear sanctions or merge duplicate vendors.
- Alter matching tolerances or policy authority.
- Approve bank-detail changes.
- Approve its own recommendation.
- Write directly to the database or ERP.
- Mark an unavailable check as passed.
- Bypass evidence hashes, case versions, segregation of duties, or OPA.

This is not a fixed business pipeline. It is bounded autonomy surrounded by
non-negotiable controls.

## 4. Runtime design

### 4.1 Shared agent contract

Every specialist receives a scoped task envelope and returns:

```json
{
  "status": "SUCCESS | PARTIAL | BLOCKED | FAILED",
  "data": {},
  "evidence": [],
  "error_code": null,
  "retryable": false,
  "latency_ms": 0,
  "provider_version": "string",
  "idempotency_key": "string",
  "reason_codes": [],
  "suggested_next_actions": []
}
```

Each invocation persists its start, finish, attempt, dependencies, redacted
input hash, output hash, evidence IDs, provider version, and trace ID.

### 4.2 Planner and capability registry

Introduce a typed capability registry. A capability defines:

- Supported workflow and prerequisites.
- Allowed tools and data classification.
- Input and output schemas.
- Timeout, retry policy, and concurrency group.
- Whether failure is optional, retryable, or transition-blocking.
- Human controls required by its findings.

The Planner Agent receives only the current state summary and registry. It
returns a structured set of eligible tasks and its evidence-based reason for
choosing them. The application validates the plan before dispatch. Unknown
agents, invalid dependencies, excessive fan-out, and unauthorized tools are
rejected.

### 4.3 Real parallel fan-out

The validated worker scheduler executes independent specialist coroutines with
failure isolation. Each operation returns its own status, result, typed error,
start/end timestamps and measured latency. One failed branch cannot erase a
successful sibling. Durable reasoning, verification and human pauses continue
inside LangGraph.

Supplier first-round fan-out:

- Document Intelligence Agent.
- Entity Resolution Agent when minimum identity fields exist.
- Sanctions Agent when a usable name or identifier exists.
- Policy Research Agent from category, geography, spend, and data-access scope.

Invoice first-round fan-out:

- Invoice Document Agent.
- PO Retrieval Agent.
- GRN Retrieval Agent.
- Vendor Resolution Agent.
- Duplicate Invoice Agent.
- Policy Research Agent.

Some nodes can start immediately; others become eligible when their
prerequisites arrive. Successful siblings remain committed when another branch
fails. The aggregator records actual wall-clock overlap and the critical path.

### 4.4 Adaptive loop

The loop is:

`observe → plan → validate plan → dispatch eligible specialists → aggregate → reason → verify → act or pause`

Allowed next actions are:

- `RUN_SPECIALISTS`
- `RETRIEVE_MORE_POLICY`
- `RETRY_TOOL`
- `REQUEST_CLARIFICATION`
- `CREATE_CONTROL_REVIEW`
- `BUILD_EVIDENCE_PACKET`
- `BLOCK`

The loop has a maximum iteration count, deadline, token budget, tool-call
budget, and duplicate-action detector. Exhaustion becomes a visible blocker;
it never becomes approval.

## 5. Workflow A: supplier onboarding

### Input

- User-entered case intent and supplier category.
- Uploaded synthetic tax certificate, bank evidence, supplier questionnaire,
  insurance/contract documents as applicable.
- Actual policy PDFs in the tenant knowledge base.
- Current official sanctions dataset snapshot with provenance.
- Persistent ERP sandbox vendor records.

### Dynamic paths

1. Clean supplier: extract → parallel checks → evidence → procurement approval
   → ERP confirmation.
2. Possible duplicate: pause for duplicate disposition, then re-plan.
3. Sanctions candidate: pause for compliance resolution; the model cannot clear
   it.
4. Bank inconsistency: finance review and verified correction.
5. Missing or unclear document: targeted clarification, new upload, then resume
   from the checkpoint.
6. Software/data supplier: retrieve the relevant policy and add the required
   review based on cited evidence.
7. Provider failure: retry independently, preserve sibling results, then show a
   blocked/recovery action.

### Completion definition

A supplier case is complete only when:

- Every required document/check is complete or explicitly resolved.
- Evidence citations and hashes verify.
- Required separate reviewers have decided.
- Final approval is version-checked.
- The ERP sandbox confirms an idempotent vendor creation.
- Notification and audit records are visible.

## 6. Workflow B: invoice exception resolution

### Input

- Uploaded synthetic invoice and optional PO/GRN documents.
- Persistent ERP sandbox PO, GRN, vendor, and invoice-history records.
- Tenant invoice/tolerance policies.

### Dynamic paths

1. Clean three-way match.
2. Price or quantity variance within tolerance.
3. Variance above tolerance requiring procurement or finance review.
4. Missing PO or GRN requiring clarification.
5. Duplicate invoice candidate requiring human disposition.
6. Vendor identity mismatch.
7. Tax or currency contradiction.
8. Bank-detail change requiring a separate finance control.
9. ERP timeout followed by idempotent retry and explicit confirmation.

### Completion definition

An invoice case is complete only when:

- Invoice, PO, GRN, and history evidence used by the decision is identified.
- Every exception and tolerance calculation is visible.
- Policy citations support the proposed resolution.
- Mandatory reviews and final approval are complete.
- The ERP sandbox confirms the exact resolution operation.
- Notification failure, if any, remains separate from case completion.

## 7. UI and UX

### 7.1 Case workspace

Replace the raw event-centric layout with five coordinated areas:

1. **Case summary:** business goal, current state, owner, SLA, and next safe
   action.
2. **Agent execution map:** persisted graph with parallel lanes, selected path,
   dependencies, attempts and measured timings. A short-lived live projection
   is still required to show `RUNNING` sub-steps before transaction commit.
3. **Evidence workspace:** document page highlights, extracted fields,
   confidence, contradictions, and policy citations.
4. **Decision panel:** one clearly scoped HITL decision, impact, evidence hash,
   and what happens next.
5. **Recovery panel:** retryable failure, retained successful work, owner, and
   recovery action.

### 7.2 Observable execution map

Each node displays:

- Queued, running, succeeded, partial, waiting for human, retrying, blocked, or
  failed status.
- Start time, end time, node latency, attempts, and provider.
- Why the node was selected.
- Redacted input summary and structured conclusion.
- Evidence count and reason codes.
- Dependencies and downstream route.

The header displays total elapsed time, active compute time, human waiting time,
critical-path duration, and parallel time saved.

Do not display hidden chain-of-thought. Display a short, generated explanation
that is validated against evidence IDs and deterministic outcomes.

### 7.3 Judge/diagnostic mode

An admin-only “Inspect run” drawer shows:

- Workflow definition and selected route.
- Redacted event stream and trace correlation.
- Agent/tool attempts and latencies.
- Retrieval queries, filters, scores, reranker result, and citations.
- Model, prompt, policy, sanctions, parser, and workflow versions.
- Checkpoint/resume history.
- OPA allow/deny result and human decision binding.
- ERP idempotency key and provider confirmation.
- Audit-chain verification result.

It must never reveal credentials, unmasked PII, presigned URLs, database
statements, or private model reasoning.

## 8. Application copilot

The copilot is a separate assistance agent, not the workflow authority.

### Capabilities

- Answer product and policy FAQ with citations.
- Explain the current case, status, evidence, and safe next action according to
  the user's role.
- Navigate to an allowed screen.
- Highlight a registered UI element and run a step-by-step product tour.
- Apply harmless view changes such as filters after user confirmation.
- Explain why a workflow paused and what evidence would resolve it.

### Explicit limits

- No approval, rejection, sanctions disposition, field correction, submission,
  ERP operation, or permission change.
- No arbitrary DOM selectors, JavaScript, URL, SQL, or tool names from model
  output.
- No access to cases the principal cannot already read.
- No use of chat history as business authority.

### Safe UI action protocol

The model returns an answer, citations, and zero or more allowlisted UI actions:

```json
{
  "answer": "Open the evidence panel and review the highlighted bank field.",
  "citations": ["faq:correct-field:v3", "case-evidence:..."],
  "actions": [
    {
      "type": "NAVIGATE",
      "target": "case.detail",
      "params": {"case_id": "authorized-id"}
    },
    {
      "type": "SPOTLIGHT",
      "target": "case.document.bank_account",
      "params": {}
    }
  ]
}
```

The frontend maps stable target IDs to components. It validates authorization,
asks for confirmation when an action changes the view, and rejects unknown
targets.

### Context, CAG, RAG, and personalization

- **CAG pack:** small versioned product vocabulary, navigation map, workflow
  invariants, tool schemas, and answer format kept in context/cache.
- **RAG:** published tenant FAQ, product help, policy, and authorized case
  evidence retrieved per question.
- **Working context:** current page, selected case, user role, locale, and active
  task.
- **Preferences:** explicit UI preferences such as compact mode, favorite queue,
  and tour progress.

“ACG” is not used as an unexplained marketing acronym. The implementation calls
this the **Context Assembly Gateway**: it constructs the minimum authorized
context from CAG, RAG, page state, and preferences.

CAG packs update only from versioned application releases or admin-published
help content. Usage analytics may propose FAQ improvements, but no unreviewed
conversation automatically rewrites the authoritative CAG pack.

## 9. Public interfaces

Implemented and generated into OpenAPI:

- `GET /api/v1/runs/{id}/graph`
- `GET /api/v1/runs/{id}/steps`
- `GET /api/v1/runs/{id}/diagnostics` for admin/auditor roles only
- `POST /api/v1/copilot/sessions`
- `GET /api/v1/copilot/sessions/{id}/messages`
- `POST /api/v1/copilot/sessions/{id}/messages`

Still to add for controlled knowledge evolution:

- `POST /api/v1/copilot/feedback`
- `GET /api/v1/help/articles`
- `POST /api/v1/admin/help/articles/{id}:publish`
- `GET /api/v1/admin/context-packs`
- `POST /api/v1/admin/context-packs/{id}:publish`

Add versioned events for plan creation, agent dispatch, agent completion,
fan-in, route selection, retry scheduling, interruption, resume, explanation,
and recovery.

## 10. Delivery sequence

### P0. Make the demo runnable

- Create lean `demo` and complete `acceptance` Compose profiles.
- Keep the ERP sandbox persistent and query-driven; remove “mock result”
  language from the product.
- Materialize two golden synthetic document packs plus three failure variants
  for each workflow.
- Prove every visible result originates from the uploaded pack or a live
  service.

### P1. Real multi-agent runtime — implemented, acceptance pending

- Extract specialist services from the large supplier and invoice worker
  functions.
- Add capability registry, planner schema, graph fan-out/fan-in, adaptive
  routing, budgets, and recovery.
- Persist first-class step/run data and overlapping timing.
- Add tests proving two independent specialist intervals overlap.

### P2. Finish supplier onboarding

- Pass clean, duplicate, sanctions, bank mismatch, missing document, conditional
  policy review, and provider outage journeys.
- Complete HITL resumption and ERP confirmation in the browser.

### P3. Finish invoice exception

- Pass clean match, variance, missing PO/GRN, duplicate invoice, vendor mismatch,
  bank change, tax mismatch, and ERP retry journeys.

### P4. Execution UX and explainability — implemented, visual acceptance pending

- Build graph/swimlane UI, latency summary, evidence links, path rationale,
  retry/recovery controls, and admin diagnostics.
- Replace raw JSON as the primary experience. Retain sanitized JSON only in
  diagnostic mode.

### P5. Copilot — core implemented, published-help workflow pending

- The versioned CAG pack, safe UI action registry, spotlight/tours and masked
  sessions are implemented. Add published-help RAG, user feedback and
  administrator promotion.
- Test prompt injection, unauthorized navigation, cross-tenant queries, and
  forbidden action attempts.

### P6. Competition acceptance

- Run both workflows from fresh input without precomputed responses.
- Run failure injection live.
- Complete Playwright, accessibility, evaluation, latency, and PII-leak gates.
- Prepare judge mode, pitch script, architecture diagram, and Q&A.

## 11. Release gates

- No arrays, timers, hidden routes, or fixture responses may produce business
  outcomes in the demo build.
- Changing a document field must change downstream evidence or route.
- Two independent specialists must have overlapping recorded execution windows.
- At least three inputs must produce different valid graph paths.
- Killing the worker at a human pause must resume without repeating completed
  specialists.
- Every LLM conclusion must be schema-valid and evidence-cited.
- Every high-risk action must require the correct human role.
- The copilot must fail closed on forbidden actions and cross-tenant requests.
- Notification outage must not change case progression.
- The full demo must pass twice from fresh state before presentation day.

## 12. Scope deliberately deferred

- Real customer ERP integration.
- Slack and Teams channels.
- Kubernetes.
- Autonomous CAG self-modification.
- General-purpose internet research or open-domain chatbot behavior.
- Payment execution.
- Unbounded autonomous tool discovery.
