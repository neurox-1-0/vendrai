# Phase 5 — Browser & failure acceptance

**Depends on:** Phase 3 or Phase 4 (at least one complete) · **Blocks:** Phase 6
**Defects addressed:** D-017, D-019

---

## Why this phase exists

This phase converts the project from "implemented" to "verified." It is the
single highest-credibility deliverable in the plan.

The evidence for its necessity is already in hand. On 2026-07-28 the repository
had **82 passing backend tests, clean ESLint, and clean TypeScript** — and the
product could not complete a single document upload, because:

- both agent workers were crash-looping on a missing `psycopg` backend (D-004)
- every MinIO URL returned connection-refused (D-005)
- every generated-client API call 404'd on a doubled path prefix (D-006)

Not one of those was detectable by the existing test suite, because the suite
substitutes SQLite, mocks, and `MockTransport` for the real infrastructure
(`AUDIT.md` §8). The tests verify contracts. They do not verify that the system
runs.

That gap is what this phase closes.

---

## Part A — Browser acceptance

### 5.1 — Playwright foundation

No Playwright configuration exists anywhere in `apps/web` (D-017).

**Setup decisions:**

- Live in `apps/web/e2e/` with its own `playwright.config.ts`.
- Target the **real running stack**, not a mocked backend. A Playwright suite
  against mocks would repeat precisely the mistake this phase exists to correct.
- Use `AUTH_MODE=keycloak` with the seven role-separated users from Phase 1.
  Development auth combines roles and cannot demonstrate segregation of duties
  (`AUDIT.md` §4.1).
- Storage-state fixtures per role so tests do not re-login constantly.
- Deterministic data: each test creates its own case; no cross-test dependence.

**Reliability rules** — non-negotiable, because a flaky acceptance suite gets
ignored and then deleted:

- Never `waitForTimeout`. Wait on API responses, SSE events, or explicit UI state.
- Bound every wait, with a message naming what was expected.
- Prefer role/label selectors over CSS. The app already self-registers semantic
  targets for the copilot (`AUDIT.md` §4.7) — reuse those IDs.

---

### 5.2 — Golden journeys

Two end-to-end journeys, each with role separation:

**Supplier (VO-001 or VO-002):**
`requester` logs in → creates case → uploads the five PDFs → submits →
SSE progress renders → execution map shows planner selection and parallel
specialists → `analyst` reviews evidence and citations →
`procurement` approves → ERP confirmation → notification appears in Mailpit.

**Invoice (AP-001):**
`requester` submits invoice + PO + GRN → three-way match evidence renders with
line-item highlights → `finance` approves → idempotent ERP write.

Each journey asserts on **evidence**, not just navigation: the citation is
present, the variance figure is correct, the audit entry exists. A test that
only proves pages render would pass against a product that computes nothing.

---

### 5.3 — Targeted UI behaviors

Smaller tests around the parts most likely to regress silently:

- **SSE reconnect**: restart the API mid-run; the case page resumes from
  `Last-Event-ID` without duplicate events.
- **Stale decision**: approve with a stale `expected_version`; expect a clear
  conflict, not a silent overwrite.
- **Document correction**: correct a field; evidence invalidates and re-analysis
  triggers.
- **Duplicate review** (VO-002): candidate is shown with its matching signals.
- **Projected vs measured timing**: assert projected nodes are visually and
  semantically distinct (Phase 2.6).
- **Copilot**: answers a question, performs an allowlisted spotlight action, and
  **cannot** approve or progress a case.

---

## Part B — Failure acceptance

This is the part reviewers probe hardest, and it is where a fail-closed design
earns its keep. Each scenario asserts on the **visible reason code and audit
entry**, not merely absence of a crash.

### 5.4 — The six failure scenarios

| # | Injection | Expected behavior |
|---|---|---|
| 1 | One specialist raises; siblings succeed | Successful sibling results persist; failed branch shows a typed error; case continues with partial evidence |
| 2 | Gemini invalid key / quota / 429 | Distinct reason codes per cause; **all deterministic checks still complete**; no fabricated reasoning |
| 3 | SMTP down (stop Mailpit) | Notification marked failed and retried; **case status and version unchanged** |
| 4 | Mock ERP timeout, then retry | Idempotent — exactly one vendor created; replay with the same key returns the original result |
| 5 | Qdrant stopped | Visible `INSUFFICIENT_POLICY_EVIDENCE`; **never a silent PASS** |
| 6 | Kill agent worker at a human interrupt, restart | LangGraph checkpoint resumes; no duplicate side effects; no duplicate ERP write |

**How to inject.** Prefer real infrastructure manipulation
(`docker compose stop qdrant`) over mocking — the point is to test the real
failure path, including timeouts and connection handling, which mocks
systematically get wrong.

Scenario 2 is the most important to get right: it demonstrates that the product
degrades to deterministic controls when the LLM is unavailable, which is the
central claim of the architecture.

---

### 5.5 — CI integration

`AUDIT.md` §4.8 notes no CI job boots the full product. Add one:

1. `docker compose --profile acceptance up -d`
2. `stack.sh doctor` (Phase 0) — fail fast if unhealthy
3. `stack.sh bootstrap` (Phase 1)
4. Playwright golden journeys
5. Upload traces/screenshots as artifacts **on failure only**

Failure scenarios run in a separate, non-blocking job initially — they are
slower and inherently more brittle. Promote to blocking once stable.

Keep it under ~20 minutes or it will be bypassed. Cache images aggressively.

---

## Acceptance criteria

- [ ] Both golden journeys pass from a clean stack with role-separated Keycloak
      users.
- [ ] Journeys assert on evidence values, not just page rendering.
- [ ] All six failure scenarios produce the expected visible reason code and
      audit entry.
- [ ] The ERP idempotency test proves exactly one vendor after a timeout+retry.
- [ ] The Gemini-outage test proves deterministic checks still complete.
- [ ] CI boots the full stack and runs the golden journeys.
- [ ] Suite passes ten consecutive runs without flake.
- [ ] No `waitForTimeout` anywhere in the suite.

---

## What this phase must not become

Not a screenshot gallery. Not a mock-backed UI test suite. Not a substitute for
running the product.

Its only purpose is to answer, automatically and repeatedly: *does this actually
work end to end?* Anything that does not serve that question is out of scope.

---

## Estimated effort

6–8 days. Part B often takes longer than expected — failure injection surfaces
real bugs, which is the point, but budget for fixing what it finds.
