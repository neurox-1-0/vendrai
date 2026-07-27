# Vendrai Judges Q&A and Gap Register

## Judge questions and defensible answers

### What makes this autonomous?

The system observes case evidence, creates a bounded plan, selects eligible
specialist capabilities, runs independent investigations in parallel, evaluates
their results, and changes its next action when evidence is missing,
contradictory, or unavailable. It can retrieve more evidence, ask a targeted
question, retry, route to a reviewer, or stop. Human approval is required only
where risk and accountability demand it.

Proof to show: three different inputs producing three different persisted graph
paths.

### Is this just a fixed pipeline?

No. The safe lifecycle—intake, verification, approval, and confirmed execution—
is stable, but the investigation subgraph is selected from current evidence.
Agents become eligible based on prerequisites, and the reasoning loop can add
work or clarification. Deterministic controls constrain unsafe outcomes; they
do not preselect every investigation path.

Proof to show: planner output, capability validation, dynamic graph route, and a
re-plan after clarification.

### Why call this multi-agent?

Specialists have distinct goals, tool permissions, schemas, deadlines, and
failure behavior. They write typed evidence into shared state and can execute
concurrently. The planner, reasoning agent, and verifier operate over those
results. Low-level parsing and authorization are correctly described as tools,
not agents.

Proof to show: overlapping specialist step intervals and different result
contracts.

### How does the agent choose tools?

It selects capabilities from a server-controlled registry. The registry declares
prerequisites, tool permissions, data classification, schemas, timeout, and
failure policy. The application validates every plan and rejects unknown or
unauthorized tool requests.

Proof to show: capability declaration, validated plan, and rejected invalid
capability test.

### What does Gemini actually do?

Gemini produces structured contradiction analysis, clarification planning,
bounded next-action recommendations, evidence critique, and user-facing
explanations from tokenized minimum context. It does not perform sanctions
clearance, authorization, deterministic financial calculations, or ERP writes.

Proof to show: live provider latency/model version and schema-validated output
linked to evidence IDs.

### Why use rules if this is agentic?

Agentic systems still need invariants. Deterministic rules define legal and
financial boundaries: tenant access, required approvals, matching calculations,
sanctions blocking, evidence integrity, and ERP authorization. The agent is
autonomous inside those boundaries. Removing them would make the system less
credible, not more agentic.

### How do you prevent hallucination?

The model receives tokenized, task-minimal context. Output must match a strict
schema. Evidence IDs are checked against the packet. A deterministic verifier
rejects unsupported citations and mandatory-control failures. Insufficient
evidence blocks the route. The model cannot directly call the database or ERP.

### How do you handle failure?

Failures are typed as retryable, non-retryable, optional, or mandatory. Retryable
steps use bounded backoff and idempotency. Successful siblings remain committed.
Durable checkpoints survive restarts and human waiting. Mandatory failures block
only unsafe transitions, while notification failures retry independently.

Proof to show: stop a provider, restore it, and show the same run resume without
repeating completed steps.

### How is HITL meaningful?

Human tasks bind the decision to a case version and evidence hash. Duplicate
disposition, sanctions resolution, bank-detail changes, final approval, and ERP
confirmation require the correct role. Stale and replayed decisions fail.

Proof to show: one successful decision and one deliberately stale decision.

### Why not display chain-of-thought?

Private chain-of-thought is neither a reliable audit artifact nor appropriate to
store. Vendrai displays source evidence, reason codes, confidence, selected
route, tool outcomes, policy versions, structured conclusions, and human
decisions. Those are verifiable.

### Is the ERP real?

The competition build uses a persistent ERP sandbox with a real API, database
queries, idempotent operations, errors, and confirmations. It proves the
integration contract without claiming access to a customer's SAP, Oracle, or
Dynamics environment.

### Is the data fake?

All business data is intentionally synthetic for privacy, but it is not
hardcoded output. Documents are uploaded and processed during the run, policies
are indexed and retrieved, sanctions data has source provenance, Gemini is
called live, and ERP sandbox records are actually queried and updated.

### Is the chatbot the agent?

No. The copilot explains, answers FAQ, navigates, highlights controls, and guides
the user. It cannot progress the workflow. The operational agents investigate
and prepare evidence; humans authorize high-risk actions.

### How does personalization work safely?

The system remembers explicit interface preferences, help progress, and saved
views. Personalization cannot change policy, permissions, thresholds, approval
routes, or evidence. Conversation history remains untrusted context.

### How does CAG update over time?

Stable product instructions and UI vocabulary live in a versioned CAG pack.
Published help and policies use RAG. Analytics can propose FAQ changes, but an
administrator reviews and publishes every authoritative update. The system does
not learn policy autonomously from chat.

## Current gap register

| Gap | Severity | Current truth | Closure evidence |
|---|---|---|---|
| Live sub-step projection browser acceptance | Medium | A tenant/run-scoped expiring Redis projection now shows active/terminal specialists before commit; PostgreSQL replaces matching steps and projection failure cannot stop the workflow | Browser proof during real supplier and invoice execution plus Redis outage injection |
| Specialist scheduler is outside LangGraph | Medium | Validated I/O specialists run in a failure-isolated worker fan-out; reasoning/HITL/ERP are checkpointed LangGraph nodes | Explain and defend this deliberate boundary; optionally convert scheduler to a nested subgraph |
| Copilot published-help RAG and promotion workflow | Medium | Versioned CAG, masked history, live case context and safe UI actions exist; controlled help publication is not yet built | Admin-reviewed help-pack version promotion and retrieval evaluation |
| Two full browser workflows not accepted | Critical | Backend pieces exist; complete stack has not passed | Supplier and invoice journeys pass twice from fresh state |
| Full local stack blocked | Critical | About 4.9 GB free, required `.env` service variables are absent, and Docker access approval was unavailable in this session | Generate local secrets, free disk and run clean Compose acceptance |
| ERP integration is a sandbox | High | Correct for competition, not a customer ERP | Honest labeling and live persistent operations |
| Numerical evaluation incomplete | High | Manifest exists; corpus run does not | Recorded extraction, matching, retrieval, safety metrics |
| UI polish not visually accepted | High | Lint/type/build pass; the in-app browser rejected local-site access | Responsive/accessibility browser review and judge rehearsal |
| OPA image/runtime not locally accepted | High | Gateway tests pass; registry DNS blocked pull | Live allow/deny/outage test |
| EU sanctions source not configured | High | Adapter fails closed | Approved source, checksum, timestamp, parser test |
| Diagnostic trace correlation incomplete | Medium | Sanitized graph/versions/integrity drawer exists; live Tempo correlation still needs inspection | Trace-to-run evidence with redaction proof |
| Terminology risks overclaiming | Medium | UI and docs now distinguish persisted conclusions from private reasoning | Rehearse the hybrid scheduler/LangGraph explanation |

## Confirmed competition constraints

- One-week build window.
- Physical presentation with a live product demonstration.
- Python, TypeScript, Gemini and self-built agent frameworks are allowed.
- Agent-as-a-service, no-code agent builders, vendor agents and black-box
  autonomy are not allowed.
- The product must demonstrate autonomous planning, three or more tools,
  dynamic decisions, adaptation, meaningful HITL and a transparent decision
  trail.

Still confirm internet availability, whether judges supply unseen documents,
the exact live-demo duration and whether source inspection is expected.

## Go/no-go criteria for the live demo

Go live only if:

- Both workflows pass twice from fresh state.
- Gemini quota and network checks pass.
- The fallback official sanctions snapshot is current and identified.
- Every judge-visible result is traceable to a live input/service.
- No secret, PII, private reasoning, or signed URL appears in diagnostics.
- The team can explain the planner, tool selection, failure recovery, guardrails,
  and human controls without reading code.

If any criterion fails, postpone the affected path or demonstrate a clearly
identified degraded mode. Never present cached output, a recording or
precomputed results as a live agent run.
