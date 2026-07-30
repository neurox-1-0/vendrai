# Phase 7 — Production hardening

**Depends on:** Phases 5, 6 · **Blocks:** nothing
**Defects addressed:** D-019 (remainder), D-020

---

## Why this phase exists — and why it is last

Everything here is genuinely deferrable until the workflows work. A product that
cannot complete a business journey does not benefit from a backup drill.

But "last" is not "optional." The security controls in this product are its
justification for existing — tenant isolation, PII masking, audit integrity,
fail-closed authorization. Those controls are currently **implemented and
unit-tested, but unproven against real infrastructure** (`AUDIT.md` §8, §9).

The distinction matters. RLS that is unit-tested against SQLite has not been
tested at all — SQLite has no row-level security. The test proves the query
shape, not the isolation.

---

## Work items

### 7.1 — Live cross-tenant isolation (D-020)

**The single most important item in this phase.** A multi-tenant compliance
product with unproven isolation has no defensible claim.

Run against real PostgreSQL with the actual non-superuser roles
(`neurox_app`, `neurox_worker`, `neurox_relay`, `neurox_audit` — created by
[`001-roles.sh`](../infra/postgres/001-roles.sh)), two populated tenants, and
assert denial across **every** boundary:

| Boundary | Test |
|---|---|
| API | Tenant A's token cannot read Tenant B's case, document, task, or audit entry |
| Database | Direct query as `neurox_app` with A's context returns zero B rows |
| Workers | A worker processing A's event cannot touch B's data |
| Object storage | A's presigned URL cannot reach B's object key |
| Retrieval | Qdrant filters exclude B's policy chunks |
| Cache | Redis key prefixes prevent cross-tenant reads |
| Relay | `neurox_relay` has `BYPASSRLS` — verify it cannot leak tenant data into events |

That last row deserves attention: `neurox_relay` is deliberately granted
`BYPASSRLS`. That is a legitimate design choice for an outbox relay, and it is
also the one role where a bug becomes a cross-tenant leak. Test it hardest.

---

### 7.2 — Adversarial PII and prompt-injection fixtures

Phase 3 builds the injection detector. This phase tries to defeat it.

- Injection variants: encoding tricks, split instructions across pages,
  instructions inside table cells and image captions, non-English phrasing.
- PII leak sweep: assert no unmasked tax ID, bank account, or SWIFT appears in
  **model payloads, application logs, OTel traces, event payloads, or error
  messages**. The last two are the ones usually missed.
- Verify the masking gateway on the actual Gemini request body, not a mocked one.

Structure this as a fixture corpus that grows whenever a leak is found, so each
discovered leak becomes a permanent regression test.

---

### 7.3 — Audit integrity under attack

The audit chain is implemented and unit-tested. Prove it against real Postgres:

- Attempt `UPDATE`/`DELETE` on `audit_logs` as each role; expect denial.
- Tamper with a row as a superuser, then verify chain verification **detects**
  it. An unverifiable hash chain provides no integrity guarantee — the detection
  path is the control, not the hashing.
- Verify export integrity and expiring download links.

---

### 7.4 — Infrastructure failure behavior (D-019 remainder)

Phase 5 covers six application-level failures. This phase covers infrastructure:

- RabbitMQ: broker restart mid-flight, publisher confirms, poison message → DLQ,
  redelivery after relay death.
- MinIO: expired presigned URL, oversized upload, wrong MIME/magic bytes,
  malformed and encrypted PDFs.
- ClamAV: EICAR fixture blocked, and ClamAV outage → fail closed
  (`CLAMAV_REQUIRED=true` must actually hold).
- PostgreSQL: connection exhaustion, failover behavior.

These are the tests the current suite substitutes mocks for, and mocks
systematically get timeouts, partial writes, and connection handling wrong.

---

### 7.5 — Backup and restore drill

Assets exist; the drill has never run (`AUDIT.md` §4.8).

Execute a real pgBackRest restore into an **isolated** volume, verify data
integrity, and measure actual RPO/RTO. Document the measured numbers, not the
target numbers.

Follow [`docs/backup-restore-runbook.md`](../docs/backup-restore-runbook.md) and
correct it wherever reality differs — a runbook that has never been executed is
a hypothesis.

---

### 7.6 — Performance against measured bottlenecks

Deliberately last, and deliberately modest.

Measure first: document processing throughput, agent workflow latency
distribution, retrieval latency, database connection saturation under the
competition concurrency target. Then tune **only** what measurement identifies.

`AUDIT.md` §13 explicitly defers large-scale load testing. Respect that.
Speculative optimization before Phase 6's real workload data is guessing.

---

### 7.7 — Documentation truth-up

`AUDIT.md` §10.1 notes that `CURRENT_STATUS.md` labels unit-tested
implementations as **VERIFIED**. Fix the labelling:

- Add an evidence-level column: `UNIT` · `INTEGRATION` · `LIVE_E2E`.
- Downgrade every label not backed by the corresponding evidence.
- Reconcile `CURRENT_STATUS.md`, `MASTER_TODO.md`, and these plans so they do
  not contradict each other.

Also resolve the repository hygiene items: the stale `vendrai/dev` upstream
causing the misleading "ahead 32" status, and tracked `.DS_Store` files
(§10.5, §10.6).

---

## Acceptance criteria

- [ ] Two-tenant isolation proven live across all seven boundaries.
- [ ] `neurox_relay`'s `BYPASSRLS` cannot leak tenant data.
- [ ] Adversarial injection corpus passes; every variant produces a finding.
- [ ] Zero unmasked sensitive values in payloads, logs, traces, events, errors.
- [ ] Audit tampering is detected by chain verification.
- [ ] All infrastructure failure scenarios behave as designed.
- [ ] A real restore drill completes with measured RPO/RTO.
- [ ] `CURRENT_STATUS.md` carries accurate evidence levels.

---

## What remains explicitly deferred

Per `AUDIT.md` §13, and still correct: Kubernetes, Grafana/Tempo dashboards,
Langfuse, cloud OCR, Slack/Teams adapters, real SAP/Oracle integration, episodic
memory, personalization, ML anomaly models beyond labelled shadow signals,
production RPO/RTO certification, and large-scale load testing.

If any of these becomes genuinely necessary, record the decision in
[`91-decisions.md`](./91-decisions.md) rather than letting it in quietly.

---

## Estimated effort

8–10 days. 7.1 and 7.2 are the ones that matter most; if time is constrained,
do those two and defer the rest.
