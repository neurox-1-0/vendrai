# NeuroX defect register

Living record of every known defect. Update on discovery and on close.

**Legend:** 🔴 open · 🟡 worked around · ✅ fixed

## Status, 2026-07-30

Sixteen defects are closed in code with tests. Read that precisely: **closed in
code is not the same as demonstrated on a running stack**, and this project's
own history is the argument for the distinction — on 2026-07-28 an 82-test
green suite sat on top of a product that could not complete a single upload.

| Closed with unit/contract coverage | Still needs a live run to be called verified |
|---|---|
| D-001, D-002, D-003, D-007, D-008, D-009, D-011, D-012, D-014, D-015, D-016, D-021, D-022, D-023 | D-017 and D-018 ship as executable suites (Playwright, evaluation harness) that have not yet been run against a live stack here |

Still open: **D-010** (RabbitMQ on native Windows — accepted as a documented
limitation under [ADR-001](./91-decisions.md)), **D-013** (confidence
calibration, which needs the 100-case run to produce the data), **D-019** and
**D-020** (live infrastructure and two-tenant isolation — the tests are
written, the run is outstanding).

Two defects were found by this work rather than by the audit, and are recorded
at the end as D-024 and D-025.

---

## P0 — correctness / blocks a promised capability

### D-001 ✅ Supplier `bank_consistency` is registered but never executed
- **Where:** registered [`planning.py:104-114`](../services/api/app/agents/planning.py#L104-L114); supplier worker executes only `duplicate_detection`, `sanctions_screening`, `policy_retrieval` ([`agent.py:353-372`](../services/api/app/workers/agent.py#L353-L372)).
- **Impact:** Gemini can select the capability and the operator sees it as part of the plan, but nothing runs and no finding is produced. Blocks VO-005 (bank beneficiary mismatch). The invoice worker *does* implement it ([`invoice_agent.py:1364`](../services/api/app/workers/invoice_agent.py#L1364)) — only the supplier path is missing.
- **Why it matters beyond the bug:** a silently unexecuted capability is worse than a missing one — it misrepresents what the system checked.
- **Phase:** 2
- **Fix:** implement the supplier operation, or remove the spec until implemented. Add a registry-vs-executor consistency test to prevent recurrence.

### D-002 ✅ Mock ERP invents a vendor legal name
- **Where:** [`erp.py:364`](../services/api/app/workers/erp.py#L364), [`erp.py:368`](../services/api/app/workers/erp.py#L368) — `vendor_payload.get("legal_name") or "Human-approved vendor"`.
- **Impact:** missing authoritative vendor data silently produces a fabricated vendor record instead of failing. Corrupts the vendor master and the audit story.
- **Phase:** 2
- **Fix:** fail closed with an explicit reason code.

### D-003 ✅ No clean-install reference data bootstrap
- **Where:** [`seed.py`](../services/api/scripts/seed.py) is 32 lines (one tenant, four users). `existing_vendor_master.csv`, `existing_invoice_history.csv`, and both policy PDFs are loaded by nothing. Root `ingest_policies.py` uses a hardcoded tenant UUID and `/tmp` paths and is not wired into Compose.
- **Impact:** a fully healthy stack still fails most business scenarios. Duplicate detection, vendor resolution, bank-change checks, and policy citation all need this data.
- **Phase:** 1
- **Fix:** one idempotent `demo-bootstrap` command using public product interfaces.

---

## P1 — reliability / developer experience

### D-004 ✅ Missing `psycopg` v3 binary backend
- **Where:** [`requirements.txt`](../services/api/requirements.txt) pinned only `psycopg2-binary`, but `langgraph-checkpoint-postgres` imports `psycopg` v3.
- **Impact:** `agent-worker` and `invoice-worker` crash-looped with `ImportError: no pq wrapper available` on every start. Both agent workflows were dead.
- **Found:** 2026-07-28 startup attempt. Invisible to unit tests (they don't import the checkpointer).
- **Fixed:** added `psycopg[binary]==3.3.4` (commit `f55cc3a`).

### D-005 ✅ MinIO unreachable from the browser
- **Where:** [`docker-compose.yml`](../docker-compose.yml) attached MinIO only to the `internal: true` `data` network.
- **Impact:** Docker accepted the `ports:` declaration but never published it (`NetworkSettings.Ports` stayed empty), so every document/quarantine link returned `ERR_CONNECTION_REFUSED`. Presented as a mysterious networking fault.
- **Fixed:** MinIO now on `[app, data]`, matching every other externally-reachable service (commit `f55cc3a`).

### D-006 ✅ Generated API client double-prefixed every URL
- **Where:** [`generated-client.ts`](../apps/web/src/lib/generated-client.ts) joined `API_BASE` (which ends in `/api/v1`) with generated paths (which also start with `/api/v1`).
- **Impact:** every call through the Orval client hit `/api/v1/api/v1/...` → 404. The hand-written `lib/api.ts` was unaffected, which masked the severity.
- **Fixed:** join against origin (commit `f55cc3a`).

### D-007 ✅ CRLF corruption of committed shell scripts
- **Where:** `git core.autocrlf=true` rewrote LF scripts on checkout: `scripts/stack.sh`, `scripts/bootstrap-local-env.sh`, `infra/keycloak/bootstrap-acceptance.sh`, `infra/postgres/001-roles.sh`.
- **Impact:** `set -euo pipefail` fails inside Linux containers (`set: pipefail: invalid option name`); Keycloak acceptance bootstrap exited 2. Known enough to be documented in `RUN_PROJECT.md` §12 — which means it keeps happening.
- **Status:** working tree repaired, but nothing prevents recurrence.
- **Phase:** 0
- **Fix:** add `.gitattributes` forcing `eol=lf` on `*.sh` and related files.

### D-008 ✅ Rate limiter misreports old-Redis errors as an outage
- **Where:** [`rate_limit.py:34-38`](../services/api/app/services/rate_limit.py#L34-L38) catches every exception and returns 503 `RATE_LIMIT_SERVICE_UNAVAILABLE`.
- **Impact:** the pipeline uses `EXPIRE … NX` (Redis 7.0+). Any older Redis returns a `ResponseError`, which the app reports as "Redis is down" — a misleading diagnosis that cost real debugging time. Encountered live against a Redis 3.0.504 Windows build.
- **Status:** worked around by running Redis 8.8.1 natively on port 16379.
- **Phase:** 0
- **Fix:** assert a minimum Redis version at startup with a clear message, and distinguish "unsupported command" from "unreachable" in the error path.

### D-009 ✅ `erl_crash.dump` committed to the repository
- **Where:** repo root, 1.5 MB, added in `f55cc3a`.
- **Impact:** repository bloat; noise in diffs.
- **Phase:** 0
- **Fix:** `git rm` and add `*.dump` to `.gitignore`.

### D-010 🔴 RabbitMQ cannot start natively on Windows
- **Where:** native Windows only; Docker is unaffected.
- **Impact:** blocks all queue-dependent work (document processing, agent workers, outbox relay) for anyone attempting the native path.
- **Investigation:** reproduced across RabbitMQ 4.1.0 and 3.13.7, and Erlang 27 and 29. `rabbitmqctl eval` traced it to `rabbit:start_it/1` blocked indefinitely on `application_controller`, which is itself idle with an empty mailbox — an orphaned call. Most likely antivirus interference during boot; could not confirm without admin rights to set Defender exclusions.
- **Phase:** 0 (as a documented limitation, not a fix)
- **Decision:** Docker is the supported path. See [`91-decisions.md`](./91-decisions.md).

---

## P2 — accuracy / completeness

### D-011 ✅ Field extraction is narrow and regex-based
- Legal name, tax ID, bank account, SWIFT, address only; first-match behavior. No document classification, registration number, country, currency, dates/expiry, multiple candidates, tables, or cross-document reconciliation.
- **Phase:** 4

### D-012 ✅ Field validation is shallow
- Non-empty, identifier length, SWIFT length. No IBAN checksum, BIC semantics, country-specific tax rules, or date/expiry logic.
- **Phase:** 4

### D-013 🔴 OCR confidence values are heuristic constants, not calibrated probabilities
- **Phase:** 6 (calibrate during evaluation)

### D-014 ✅ No deterministic prompt-injection detector
- Prompts declare document content untrusted, but no `UNTRUSTED_DOCUMENT_INSTRUCTION` finding exists. Blocks VO-004's stated expected outcome.
- **Phase:** 3

### D-015 ✅ Supplier controls required by the proposal are absent
- Required-document matrix, country/currency/cross-border risk, bank-beneficiary mismatch, certificate expiry, insurance, DPA. Blocks VO-003 and VO-005.
- **Phase:** 3

### D-016 ✅ Clarification questions are generic templates
- Not derived from the specific missing or contradictory evidence.
- **Phase:** 3

### D-021 ✅ `email_domain` duplicate signal is dead code
- **Where:** [`agent.py:70-84`](../services/api/app/workers/agent.py#L70-L84) passes `email_domain` for the incoming case but never passes `candidate_email_domain`, because the [`Vendor`](../services/api/app/models.py#L54) model has no `email_domain` column.
- **Impact:** `score_duplicate` computes `email_domain_exact` ([`intelligence.py:73-90`](../services/api/app/domain/intelligence.py#L73-L90)) which is therefore **always `False`**. A real duplicate signal is silently inert, weakening VO-002 detection. The shipped `existing_vendor_master.csv` carries an `email_domain` column that cannot currently be stored or used.
- **Found:** 2026-07-29 planning research (not in `AUDIT.md`).
- **Phase:** 1 (schema + loader) and 3 (scoring verification)
- **Fix:** add `email_domain` to `Vendor` with a migration, populate it in the bootstrap loader, and pass it as `candidate_email_domain`.

### D-023 ✅ The mock risk service the corpus expects does not exist
- **Where:** nowhere. `grep` for `adverse_media`, `country_risk`, `risk_api` across `services/` returns zero matches.
- **Expected by:** the corpus README instructs evaluators to "configure the mock risk tool to return values from `mock_risk_api_results.json`", which supplies `sanctions`, `adverse_media`, `country_risk`, and `checked_at` per vendor.
- **Impact:** three expected findings are unreachable — VO-005's "possible adverse-media name match", VO-004's "risk service unavailable", and VO-003's country-risk contribution. These are not scoring nuances; they are the stated expected outcomes for those scenarios.
- **Found:** 2026-07-29 planning research (not in `AUDIT.md`).
- **Phase:** 3
- **Note:** this is distinct from sanctions screening, which does exist. Adverse media and country risk are separate signals.

### D-022 ✅ Supplier policy query is a hardcoded string
- **Where:** [`agent.py:351`](../services/api/app/workers/agent.py#L351) — a single fixed query string is used for every supplier case regardless of its actual content or risk profile.
- **Impact:** policy retrieval cannot surface clauses relevant to the specific case (cross-border, insurance, DPA), which directly undermines VO-003.
- **Phase:** 3

---

## P3 — verification gaps

### D-017 ✅ No browser E2E suite
- No Playwright config or journeys anywhere in `apps/web`.
- **Phase:** 5

### D-018 ✅ 100-case evaluation is a manifest, not an evaluation
- `evaluation/cases.jsonl` declares 100 cases; nothing materializes, executes, or scores them. **Mitigating factor:** [`expected_case_outcomes.json`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/expected_case_outcomes.json) already provides the scoring oracle.
- **Phase:** 6

### D-019 🔴 Live infrastructure behavior is unproven
- Tests substitute SQLite, mocks, and `MockTransport`. Real RabbitMQ retry/DLQ, MinIO presigned flows, ClamAV, Docling/Tesseract/EasyOCR, Qdrant hybrid retrieval, Keycloak PKCE, OPA decisions, and SMTP retry are all unexercised.
- **Phase:** 5, 7

### D-020 🔴 Cross-tenant isolation not proven live
- RLS, filters, and scoping exist with unit coverage; no live two-tenant test on current migrations.
- **Phase:** 7

---

## Found while implementing the plans

### D-024 ✅ Personal contact details were stored and emitted in plaintext
- **Where:** [`document.py`](../services/api/app/workers/document.py) `SENSITIVE_FIELDS` covered `tax_id`, `bank_account`, `swift_code`, and `registered_address`, but not `email`, `telephone`, `primary_contact`, `beneficial_owner`, or `received_by`.
- **Impact:** those fields were written to `ExtractedField.normalized_value` as plaintext, so any consumer of an extraction — including outbox event payloads, which cross a boundary into consumers with different retention rules — received an unmasked phone number, email address, and named individual. Page text was masked; the extracted fields were not.
- **Found:** 2026-07-30, by the PII leak sweep written for Phase 7.2 ([`test_pii_leak_sweep.py`](../services/api/tests/test_pii_leak_sweep.py)). It failed on its first run against the real corpus.
- **Why it survived:** the existing PII tests checked the masking *functions*. Nothing checked the *fields the pipeline actually persists*, so a field nobody read was a field nobody noticed leaking.
- **Fix:** the five fields are now blind-indexed and encrypted like every other sensitive field. `email_domain` and `bank_beneficiary_name` remain plaintext, deliberately and with the reasoning recorded in code — the first is public and feeds duplicate detection, the second is what the bank-consistency control compares against.

### D-025 🔴 Injection detection does not normalise Unicode confusables
- **Where:** [`injection.py`](../services/api/app/domain/injection.py) matches on the extracted text as-is.
- **Impact:** an instruction using homoglyphs (Cyrillic `о` for Latin `o`) or zero-width characters evades every pattern. Non-English instructions are likewise uncovered.
- **Found:** 2026-07-30, writing the adversarial corpus for Phase 7.2. Recorded as `xfail(strict=True)` in [`test_adversarial_injection.py`](../services/api/tests/test_adversarial_injection.py) rather than deleted, so closing it flips a test from expected-fail to passing.
- **Fix:** Unicode confusable folding in the extractor, before scanning. Deliberately *not* a wider regex, which would raise the false-positive rate on ordinary documents — and a false positive that routes a clean supplier to clarification teaches reviewers to dismiss the finding.
