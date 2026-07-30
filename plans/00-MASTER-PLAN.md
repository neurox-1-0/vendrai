# NeuroX Master Build Plan

**Created:** 2026-07-29
**Baseline commit:** `7affc95` (branch `dev`)
**Basis:** [`AUDIT.md`](../AUDIT.md) (2026-07-28, commit `392c67b`) + source verification
and a full native/Docker startup attempt performed 2026-07-28.

**Goal:** take NeuroX from "credible product-shaped beta" to a genuinely complete,
reliably startable, evidence-backed product.

---

## 1. What is actually true today

I re-verified the audit's headline claims directly against source rather than
trusting the document. All confirmed:

| Audit claim | Verified? | Evidence |
|---|---|---|
| Supplier `bank_consistency` registered but never executed | ✅ Real P0 bug | Registered [`planning.py:104-114`](../services/api/app/agents/planning.py#L104-L114); supplier worker executes only `duplicate_detection`, `sanctions_screening`, `policy_retrieval` ([`agent.py:353-372`](../services/api/app/workers/agent.py#L353-L372)). Invoice worker *does* execute it — supplier does not. |
| Mock ERP silently invents a vendor name | ✅ Real | `or "Human-approved vendor"` at [`erp.py:364`](../services/api/app/workers/erp.py#L364) and [`:368`](../services/api/app/workers/erp.py#L368). |
| Seed script does not load reference data | ✅ Real | [`seed.py`](../services/api/scripts/seed.py) is 32 lines — one tenant, four users, nothing else. |
| Reference data + policies exist but are never ingested | ✅ Real | `existing_vendor_master.csv`, `existing_invoice_history.csv`, and two policy PDFs sit in the corpus, loaded by nothing. |
| No browser E2E suite | ✅ Real | No Playwright config anywhere in `apps/web`. |
| 100 "cases" are a manifest, not executed evaluations | ✅ Real | `evaluation/cases.jsonl` has 100 declarative rows; no materializer, runner, or scorer exists. |

**One thing the audit missed, in our favour:** the corpus already ships
[`expected_case_outcomes.json`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/expected_case_outcomes.json)
with per-scenario expected status, risk, findings, and required human action.
That is the scoring oracle the evaluation harness needs — it does not have to be
invented.

### Issues found during the 2026-07-28 startup attempt (not in the audit)

The audit was written from static inspection with Docker stopped. Actually
running the stack surfaced six additional real defects. Four are already fixed
and committed in `f55cc3a`:

| Issue | Status |
|---|---|
| `langgraph-checkpoint-postgres` needs `psycopg` v3 with a binary backend; only `psycopg2-binary` was pinned, so `agent-worker` and `invoice-worker` crash-looped on every start | ✅ Fixed — added `psycopg[binary]==3.3.4` |
| MinIO was attached only to the `internal: true` `data` network, so Docker silently refused to publish ports 9000/9001 → browser `ERR_CONNECTION_REFUSED` on every document/quarantine link | ✅ Fixed — MinIO now on `[app, data]` |
| Generated Orval client double-prefixed every URL (`/api/v1/api/v1/...`) because `API_BASE` already contained `/api/v1` and generated paths do too → 404s across the app | ✅ Fixed — join against origin |
| `git core.autocrlf` rewrote committed LF shell scripts to CRLF, breaking `set -euo pipefail` inside Linux containers | ✅ Fixed in working tree — **needs a permanent guard (`.gitattributes`)** |
| Rate limiter uses `EXPIRE … NX` (Redis 7.0+); any older Redis returns an error the app misreports as `RATE_LIMIT_SERVICE_UNAVAILABLE` (503) | ⚠️ Worked around natively; **needs a real fix** — see Phase 0 |
| `erl_crash.dump` (1.5 MB) accidentally committed in `f55cc3a` | ❌ Open — remove + ignore |

**The lesson:** four of these were invisible to static analysis and unit tests.
They only appeared when the product actually ran. That is precisely why Phase 0
and Phase 5 of this plan exist.

---

## 2. Guiding principles

1. **Startability is a feature.** "Struggling to start" is the single biggest
   tax on every other task. It is Phase 0, not an afterthought.
2. **Fix correctness before adding capability.** A registered-but-unexecuted
   capability is worse than a missing one — it lies to the operator.
3. **Every phase ends in something runnable and observable**, not a document.
4. **Prefer proving over building.** Most of this product exists. The gap is
   proof that it works end to end.
5. **Do not add new platforms.** No Kubernetes, no cloud OCR, no real SAP. The
   existing boundaries are sufficient (audit §13 — I agree).
6. **Fail closed, visibly.** Silent fallbacks (`Human-approved vendor`) are
   worse than errors.

---

## 3. Phase map

Phases are ordered by dependency, not by ambition. Each phase is a separate
detailed plan file in this folder.

| # | Phase | Plan file | Why it is here |
|---|---|---|---|
| 0 | Make it start, every time | [`01-phase-0-startability.md`](./01-phase-0-startability.md) | Everything downstream depends on a reliable stack. |
| 1 | Clean-install bootstrap | [`02-phase-1-bootstrap.md`](./02-phase-1-bootstrap.md) | Without reference data, *no* scenario can pass. |
| 2 | Correctness & honesty fixes | [`03-phase-2-correctness.md`](./03-phase-2-correctness.md) | Small, high-value, unblocks scenario work. |
| 3 | Supplier workflow completion | [`04-phase-3-supplier.md`](./04-phase-3-supplier.md) | Largest functional gap vs. the proposal. |
| 4 | Invoice workflow stabilization | [`05-phase-4-invoice.md`](./05-phase-4-invoice.md) | Closest to done; make it the golden path. |
| 5 | Browser + failure acceptance | [`06-phase-5-acceptance.md`](./06-phase-5-acceptance.md) | Converts "implemented" into "verified". |
| 6 | Evaluation harness & metrics | [`07-phase-6-evaluation.md`](./07-phase-6-evaluation.md) | Turns 100 declared cases into 100 scored ones. |
| 7 | Production hardening | [`08-phase-7-hardening.md`](./08-phase-7-hardening.md) | Security, chaos, backup/restore, performance. |

Supporting reference documents:

| Document | Purpose |
|---|---|
| [`90-defect-register.md`](./90-defect-register.md) | Every known defect, with status and owner phase. |
| [`91-decisions.md`](./91-decisions.md) | Architectural decisions and their rationale. |

---

## 4. The phases

### Phase 0 — Make it start, every time

**Problem:** starting the project is currently a multi-hour ordeal with
platform-specific failures. That is unacceptable for a project meant to be
built out.

**Key decision — Docker is the supported path.** The 2026-07-28 native Windows
attempt got 11 of 12 services running but hit a hard wall: RabbitMQ hangs
indefinitely on native Windows boot (reproduced across RabbitMQ 4.1.0 *and*
3.13.7, Erlang 27 *and* 29; traced via `rabbitmqctl eval` to `rabbit:start_it/1`
blocked forever on an idle `application_controller`). Native Windows also forced
an outdated Redis, a reserved-port collision, and a path-with-spaces failure in
`kcadm.bat`. Fighting the platform is not a good use of build time.

Native stays documented as a fallback (already in `README.md`), but Docker gets
the investment.

**Work:**
- One-command startup with real preflight checks (disk, RAM, ports, Docker
  daemon) that fail with actionable messages instead of mysterious hangs.
- Fix the Redis `EXPIRE NX` fragility properly: pin a minimum Redis version and
  make the rate limiter degrade honestly instead of returning a misleading 503.
- Add `.gitattributes` to permanently prevent the CRLF class of bug.
- Remove `erl_crash.dump`; ignore `*.dump`.
- Health-gate the startup script so it reports business readiness, not just
  container liveness.

**Done when:** a clean clone + `.env` reaches a fully healthy stack via one
command, and a deliberately broken precondition produces a clear message within
seconds.

---

### Phase 1 — Clean-install bootstrap

**Problem:** the audit's single most important finding. A healthy stack can
still fail every business scenario because the vendor master, invoice history,
policies, and sanctions data are never loaded.

**Work:** one idempotent `demo-bootstrap` command that loads reference data,
publishes both policy PDFs through the *real* knowledge API, waits for Qdrant
indexing and verifies retrieval, imports sanctions with explicit failure, and
prints a secret-free readiness report. Replaces the ad-hoc root
`ingest_policies.py` (fixed tenant UUID, `/tmp` paths).

**Done when:** a fresh install reaches business-ready with no manual SQL, no
file copying, and no source edits — and re-running it changes nothing.

---

### Phase 2 — Correctness & honesty fixes

Small, surgical, high-value:
- Wire supplier `bank_consistency` (or remove it from the registry — the current
  state is the worst option).
- Remove the `Human-approved vendor` fallback; fail closed.
- Add a registry-vs-executor consistency test so this class of bug cannot recur.
- Provenance labelling: uploaded PO/GRN are *reference evidence*, not
  authoritative ERP feeds. The UI must not imply otherwise.
- Ensure the UI never presents projected timing as measured latency.

---

### Phase 3 — Supplier workflow completion

The largest functional gap. VO-003 and VO-005 cannot pass today.

Required-document matrix, country/currency/cross-border checks, bank-beneficiary
mismatch, certificate expiry/insurance/DPA checks, and case-specific
clarification questions generated from structured missing evidence rather than
generic templates.

**Done when:** VO-001, VO-002, VO-004, VO-005 complete end to end. VO-003 either
passes or is explicitly removed from promised scope.

---

### Phase 4 — Invoice workflow stabilization

Closest to complete. Make AP-001 the golden path, then AP-002 through AP-007
against bootstrapped reference data. Broaden invoice/PO/GRN extraction beyond
the current narrow regex/template approach.

---

### Phase 5 — Browser + failure acceptance

This phase converts the whole project from "implemented" to "verified."

Playwright with role-separated Keycloak users covering the golden journeys, plus
deliberate failure injection: specialist failure with surviving siblings, Gemini
quota exhaustion, SMTP outage, ERP timeout + idempotent retry, Qdrant outage
producing visible insufficient-evidence, and worker restart at a human interrupt.

---

### Phase 6 — Evaluation harness & metrics

Build materializer → runner → scorer → report over the existing 100-case
manifest, scored against the shipped `expected_case_outcomes.json`. Produce real
field F1, duplicate recall, policy Recall@10, and citation precision — then
publish whatever the numbers actually are.

---

### Phase 7 — Production hardening

Live two-tenant isolation, adversarial PII/prompt-injection fixtures, audit
mutation resistance, backup/restore drill, and performance tuning against
measured bottlenecks.

---

## 5. Sequencing

Phases 0 → 1 → 2 are strictly sequential and unlock everything else.

Phases 3 and 4 can proceed in parallel once Phase 2 lands (different workers,
different scenarios). Phase 5 needs at least one of them complete. Phase 6 needs
both. Phase 7 is genuinely deferrable.

```
0 ──> 1 ──> 2 ──┬──> 3 ──┬──> 5 ──> 6 ──> 7
                └──> 4 ──┘
```

**Recommended first move:** Phase 0 and Phase 2 together. Phase 2's fixes are
small and self-contained, and having them in place makes Phase 1's bootstrap
verification meaningful (a bootstrap that "succeeds" into a workflow with an
unexecuted capability is not a real success).

---

## 6. What "fully built" means

Adapted from the audit's demo-ready checklist (§15), extended for a product that
is no longer a demo:

- [ ] One command starts a clean stack; one command makes it business-ready.
- [ ] Both policies published; retrieval returns correct citations.
- [ ] Sanctions data present, current, and traceable.
- [ ] Every registered capability is actually executed, or is not registered.
- [ ] No silent fallbacks; missing authoritative data fails closed and visibly.
- [ ] All 12 corpus scenarios reach their expected outcome from
      `expected_case_outcomes.json`.
- [ ] Golden supplier and invoice journeys pass in a real browser with
      role-separated identities.
- [ ] Parallel specialist execution, human interrupt/resume, and at least one
      recoverable failure are each demonstrable.
- [ ] The 100-case suite executes and reports real measured metrics.
- [ ] Cross-tenant isolation proven live, not just unit-tested.
- [ ] No unmasked sensitive value reaches model payloads, logs, events, traces.
- [ ] Audit trail explains every transition via evidence and reason codes.
- [ ] Full gate green: backend tests, frontend lint/type/build, migrations,
      contract drift, and Playwright journeys.

---

## 7. Honest risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Extraction accuracy is regex-based and narrow | Scenarios fail on layout variation | Phase 4 broadens it; Phase 6 measures it honestly rather than claiming a number |
| Gemini quota/rate limits during evaluation | 100-case run stalls | Manifest already has `resumable_on_quota`; runner must checkpoint |
| Native Windows remains unusable for RabbitMQ | Contributors on Windows blocked | Docker is the supported path; native documented as best-effort |
| Sanctions EU source unconfigured | Sanctions fails closed, blocking VO scenarios | Phase 1 must surface this as one explicit setup message, not a silent block |
| Scope creep back into infrastructure | Delays functional completion | Audit §13 deferral list is binding |

---

## 8. Working agreement

- Update [`90-defect-register.md`](./90-defect-register.md) whenever a defect is
  found or closed.
- A phase is complete only when its acceptance criteria are demonstrated on a
  running stack — not when the code merges.
- `CURRENT_STATUS.md` must use evidence-level labels; "unit-tested" is not
  "verified" (audit §10.1 — a fair criticism).
- Prefer deleting a false claim over defending it.
