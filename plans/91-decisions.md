# Architectural decisions

Decisions made while planning the full build, with the reasoning behind them.
Recorded so they can be revisited deliberately rather than drifted away from.

---

## ADR-001 — Docker is the supported local runtime; native Windows is best-effort

**Date:** 2026-07-29 · **Status:** Accepted

### Context

A full native Windows setup was attempted on 2026-07-28 to remove the Docker
dependency. Eleven of twelve services were brought up successfully: PostgreSQL,
Redis, Qdrant, MinIO, ClamAV, OPA, Mailpit, Keycloak (realm + 7 role-separated
users + e2e client), mock-ERP, the API, and the web app.

RabbitMQ could not be made to work. It hangs indefinitely immediately after
printing its version banner, before any boot-step logging. Reproduced across:

- RabbitMQ 4.1.0 and 3.13.7
- Erlang/OTP 27.3.4 and 29.0.4
- Default and `localhost` node names
- With and without an `inetrc` resolver override

`rabbitmqctl eval` traced it to `rabbit:start_it/1` blocked forever waiting on
`application_controller`, which is itself idle with an empty mailbox — the
signature of an orphaned call. Most probable cause is real-time antivirus
scanning interfering with the many small files RabbitMQ's Khepri/Mnesia store
writes on first boot. Confirming it requires administrator rights to set
Defender exclusions, which were unavailable.

Native Windows also produced three further platform frictions:

1. The bundled Windows Redis was 3.0.504 (~2016), missing `EXPIRE … NX`
   (Redis 7.0+) that the rate limiter depends on.
2. Port 6380 could not be bound — it falls inside a Windows reserved
   port-exclusion range.
3. Keycloak's `kcadm.bat` silently failed on the repository path because it
   contains spaces (`New folder (9)`), requiring relocation to `C:\tools`.

### Decision

Docker Compose is the supported local runtime and receives the tooling
investment. The native Windows path stays documented in `README.md` as
best-effort, with the RabbitMQ limitation stated plainly.

### Rationale

Every native blocker was a fight with the platform rather than with the product.
That time is better spent on the twenty open defects in the register. Docker
already works and normalises all of these differences.

### Consequences

- Phase 0 invests in Docker startup reliability, not native parity.
- Contributors need Docker Desktop; documented as a hard requirement.
- The native runbook and `scripts/run-native.ps1` remain for anyone who needs
  them, with limitations stated up front.
- If native Windows becomes a requirement later, start by testing the Defender
  exclusion hypothesis with admin rights.

---

## ADR-002 — A registered capability must be executable, or it must not be registered

**Date:** 2026-07-29 · **Status:** Accepted

### Context

Supplier `bank_consistency` is advertised in the capability registry, can be
selected by the Gemini planner, and appears in the plan the operator sees — but
no supplier operation implements it, so it silently never runs (D-001).

### Decision

The capability registry is a contract. Every registered capability must have an
executing operation in its workflow, enforced by an automated consistency test.
A capability that is not yet implemented must not appear in the registry.

### Rationale

An unexecuted-but-advertised capability is strictly worse than a missing one: it
tells the operator, the audit trail, and any reviewer that a check was
considered, when nothing happened. In a compliance product that is a
correctness and integrity failure, not a gap.

### Consequences

- Phase 2 either implements the supplier operation or removes the spec.
- A registry-vs-executor test runs in CI, making this class of defect
  structurally impossible to reintroduce.

---

## ADR-003 — Missing authoritative data fails closed, never defaults

**Date:** 2026-07-29 · **Status:** Accepted

### Context

The ERP worker substitutes the literal string `"Human-approved vendor"` when a
legal name is absent (D-002), silently creating a vendor record with fabricated
identity data.

### Decision

Absent authoritative data produces an explicit, reason-coded failure. No
placeholder, no default, no silent substitution — anywhere in a control or
write path.

### Rationale

The product's value rests on evidence integrity. A fabricated value that flows
into the vendor master and the audit trail undermines every downstream claim,
and does so invisibly.

### Consequences

- Phase 2 removes this fallback and adds a reason code.
- Any scenario relying on the fallback to "pass" was never actually passing;
  expect one or more scenarios to correctly start failing until upstream
  extraction is fixed. That is the intended outcome.

---

## ADR-004 — Prove before building

**Date:** 2026-07-29 · **Status:** Accepted

### Context

The audit's core finding is that architectural breadth ran ahead of scenario
completion and acceptance evidence. Most of the product exists; what is missing
is proof that it works end to end.

Four of the six defects found during the 2026-07-28 startup attempt (D-004 to
D-007) were invisible to a passing 82-test suite and clean lint/type checks.
They appeared only when the product actually ran.

### Decision

Prioritise executing and verifying existing capability over adding new
capability. The deferral list in `AUDIT.md` §13 is binding: no Kubernetes, no
cloud OCR, no real SAP/Oracle, no Langfuse, no episodic memory, no
personalization, until the workflow gates are green.

### Rationale

Unit tests prove implementation contracts. They do not prove that a distributed
system starts, connects, and completes a business journey. The highest-value
work available is closing that gap.

### Consequences

- Phase 5 (browser + failure acceptance) is treated as a first-class deliverable.
- `CURRENT_STATUS.md` adopts evidence-level labels; "unit-tested" never reads as
  "verified."
- New platform work requires an explicit decision recorded here.
