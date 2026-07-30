# NeuroX build plans

Working plans for taking NeuroX from a product-shaped beta to a fully built,
verified product. Grounded in [`AUDIT.md`](../AUDIT.md) plus direct source
verification and a full startup attempt on 2026-07-28.

## Status, 2026-07-30

All eight phases have been implemented. See
[`../CURRENT_STATUS.md`](../CURRENT_STATUS.md) for the delivery table with
evidence levels, and [`90-defect-register.md`](./90-defect-register.md) for
what closed and what did not.

The honest summary: the code and the tests exist, 269 backend tests pass, and
**nothing has been demonstrated on a running stack.** Phases 5, 6, and 7 ship
executable suites — Playwright journeys, failure injection, the 100-case
evaluation harness, live isolation tests, a restore drill — that have not been
run here. Per this document's own convention below, that means those phases are
not complete.

## Start here

**[`00-MASTER-PLAN.md`](./00-MASTER-PLAN.md)** — verified current state, guiding
principles, phase map, sequencing, and the definition of "fully built."

## Phase plans

| # | Plan | Focus | Effort |
|---|---|---|---|
| 0 | [`01-phase-0-startability.md`](./01-phase-0-startability.md) | One command starts it, or says exactly why not | 2–3 d |
| 1 | [`02-phase-1-bootstrap.md`](./02-phase-1-bootstrap.md) | Reference data, policies, sanctions — the clean-install blocker | 4–5 d |
| 2 | [`03-phase-2-correctness.md`](./03-phase-2-correctness.md) | Stop the system reporting things that did not happen | 2 d |
| 3 | [`04-phase-3-supplier.md`](./04-phase-3-supplier.md) | VO-001…VO-005 complete | 8–10 d |
| 4 | [`05-phase-4-invoice.md`](./05-phase-4-invoice.md) | AP-001…AP-007 complete | 7–9 d |
| 5 | [`06-phase-5-acceptance.md`](./06-phase-5-acceptance.md) | Playwright + failure injection = "verified" | 6–8 d |
| 6 | [`07-phase-6-evaluation.md`](./07-phase-6-evaluation.md) | 100 declared cases → 100 scored cases | 6–8 d |
| 7 | [`08-phase-7-hardening.md`](./08-phase-7-hardening.md) | Live isolation, adversarial, backup, performance | 8–10 d |

**Total: roughly 9–11 weeks** of focused work, with Phases 3 and 4 parallelizable.

## Sequencing

```
0 ──> 1 ──> 2 ──┬──> 3 ──┬──> 5 ──> 6 ──> 7
                └──> 4 ──┘
```

Phases 0 and 2 can run concurrently — they touch different files. Start there.

## Reference

| Document | Purpose |
|---|---|
| [`90-defect-register.md`](./90-defect-register.md) | Every known defect, status, and owning phase |
| [`91-decisions.md`](./91-decisions.md) | Architectural decisions and rationale |

## Conventions

- A phase is complete only when its acceptance criteria are demonstrated on a
  **running stack**, not when code merges.
- Log every newly discovered defect in the defect register immediately.
- These plans describe intended work. `CURRENT_STATUS.md` describes proven
  state. Do not conflate them.
