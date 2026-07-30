# Phase 1 — Clean-install bootstrap

**Depends on:** Phase 0 · **Blocks:** Phases 3, 4, 5, 6
**Defects addressed:** D-003, D-021 (schema half)

---

## Why this phase exists

This is `AUDIT.md`'s single most important finding (§7), and I agree with its
severity assessment.

A completely healthy stack — every container green, every health check passing —
still fails most business scenarios, because the data those scenarios depend on
is never loaded:

| Asset | Ships in repo | Loaded by |
|---|---|---|
| `existing_vendor_master.csv` (vendor identities) | ✅ | **nothing** |
| `existing_invoice_history.csv` (duplicate detection) | ✅ | **nothing** |
| `PROC-001_Supplier_Onboarding_Policy.pdf` | ✅ | **nothing** |
| `AP-001_Invoice_Matching_and_Exception_Policy.pdf` | ✅ | **nothing** |
| Sanctions datasets (OFAC/UN/EU) | downloaded | manual admin API call |

[`seed.py`](../services/api/scripts/seed.py) is 32 lines: one tenant, four
users. Nothing else.

The consequence is subtle and dangerous: **scenarios fail for the wrong reason.**
VO-002 (duplicate vendor) cannot detect a duplicate when the vendor master is
empty — so it "passes" by finding nothing, or blocks on missing evidence. Either
way the result is meaningless, and a casual observer sees a working system.

---

## Current state of the ad-hoc script

The root [`ingest_policies.py`](../ingest_policies.py) is the closest thing to a
bootstrap. It should be deleted, not fixed:

- Hardcoded tenant UUID (line 22)
- Hardcoded `/tmp/knowledge_base/*.pdf` paths (lines 26, 34) — not where the
  PDFs actually live in the repo
- Imports `PyPDF2`, which is **not in `requirements.txt`** (the project pins
  `pypdf`) — so it cannot run in the API image as built
- Writes ORM models directly, bypassing the knowledge API entirely: no
  authorization, no idempotency key, no audit entry
- Emits `aggregate_type="POLICY"` where the real API emits `"policy"`
  ([`knowledge.py:87`](../services/api/app/routers/knowledge.py#L87)) — a
  case mismatch that likely breaks event routing
- `datetime.utcnow()` (naive) where the codebase standard is `datetime.now(UTC)`

---

## Design decision: bootstrap through public interfaces

The bootstrap must create data **the way a real operator would** — through the
product's own API — not by writing rows.

**Why this matters.** A bootstrap that writes ORM models directly proves
nothing and can create states the API would reject. Going through the API means
the bootstrap is simultaneously the product's first integration test: it
exercises authorization, idempotency, audit logging, event emission, and
indexing on every run.

Two exceptions where direct writes are acceptable, because no public interface
exists and none should be invented for this:

- Reference data (`vendors`, `invoice_history`) — these represent an external
  system of record, not user-created content.
- The tenant and users themselves — chicken-and-egg with authentication.

---

## Work items

### 1.1 — Add `email_domain` to the vendor model (D-021)

**Do this first** — it is a schema change, and the loader depends on it.

`score_duplicate` computes an `email_domain_exact` signal
([`intelligence.py:73-90`](../services/api/app/domain/intelligence.py#L73-L90)),
but [`agent.py:79-82`](../services/api/app/workers/agent.py#L79-L82) never
passes `candidate_email_domain` — because [`Vendor`](../services/api/app/models.py#L54)
has no such column. The signal is permanently `False`. The vendor master CSV
ships the data.

- Add `email_domain: Mapped[str | None] = mapped_column(Text)` to `Vendor`.
- Write a reversible Alembic migration.
- Pass `candidate_email_domain=vendor.email_domain` in `duplicate_score`.

---

### 1.2 — Reference data loader

Load [`existing_vendor_master.csv`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/existing_vendor_master.csv)
(`vendor_id, legal_name, tax_id, registration_no, bank_account, email_domain, status`)
into `vendors`.

**The critical detail:** `Vendor` stores `tax_id_hash` and `bank_account_hash`
as **blind indexes**, not plaintext
([`models.py:61-62`](../services/api/app/models.py#L61-L62)). The loader must
compute them with
[`blind_index(value, settings.BLIND_INDEX_SECRET)`](../services/api/app/domain/security.py#L20)
and `normalized_legal_name` with
[`normalize_vendor_name`](../services/api/app/domain/security.py#L14).

Getting this wrong is silent: duplicate detection simply never matches, and
VO-002 fails with no error. Add an assertion after load that a known CSV tax ID
produces a blind index matching the stored row.

Load [`existing_invoice_history.csv`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/existing_invoice_history.csv)
into `invoice_history`. Note `vendor_id` is the ERP string (`V000184`), not a FK
— match the existing model.

Idempotency: upsert on `(tenant_id, erp_vendor_id)` and
`(tenant_id, vendor_id, invoice_number)`, both of which already have unique
constraints.

---

### 1.3 — Policy publication through the real API

For each of the two policy PDFs:

1. Extract text with `pypdf` (**not** `PyPDF2` — match `requirements.txt`).
2. `POST /api/v1/knowledge/documents` with an `Idempotency-Key`, as an admin
   principal. Handle `409 POLICY_ALREADY_EXISTS` as success.
3. `POST /api/v1/knowledge/documents/{id}:publish`.
4. **Wait for indexing and verify it.** Publishing only enqueues
   `policy.published.v1` ([`knowledge.py:86-91`](../services/api/app/routers/knowledge.py#L86-L91));
   the retrieval worker consumes it asynchronously. A bootstrap that returns
   before indexing completes reports success while retrieval still returns
   nothing.

   Poll a retrieval query with a known-good phrase from each policy until it
   returns citations, with a bounded timeout and an explicit failure if it
   expires.

**Verification query examples** (must return the expected clause):
- PROC-001: a required-documents phrase
- AP-001: a tolerance-threshold phrase

This step is what makes the difference between "policies exist in Postgres" and
"policy retrieval works" — and only the second one matters to a scenario.

---

### 1.4 — Sanctions import with explicit failure

Drive [`POST /api/v1/admin/sanctions-imports`](../services/api/app/routers/admin.py#L196)
for each required source.

`SANCTIONS_EU_URL` is **empty by default** in `.env`. Sanctions screening fails
closed when a required source is missing — correct behavior, but it means every
supplier scenario blocks with a confusing message.

The bootstrap must therefore end with **one explicit, actionable message**:

```
SANCTIONS_EU_URL is not configured. Supplier scenarios will block at
sanctions screening (fail-closed by design).

Set an approved official EU export URL in .env, or run with
--allow-missing-eu-sanctions to bootstrap for invoice-only testing.
```

Not a stack trace, not a silent skip. This is exactly the class of problem that
makes a clean install look broken.

---

### 1.5 — Role-separated users

`seed.py` creates four users, but one of them (`auditor`) holds `["auditor",
"admin"]`. The audit is right that this undermines segregation-of-duties
demonstration (§4.1, "Development authentication").

Create users matching the seven Keycloak identities the acceptance bootstrap
already provisions (`requester`, `analyst`, `procurement`, `compliance`,
`finance`, `auditor`, `admin`) with **exactly one role each**, and map
`external_subject` to the Keycloak subject so `AUTH_MODE=keycloak` resolves the
same person.

---

### 1.6 — Readiness report

End with a secret-free report:

```
NeuroX bootstrap complete.

  Tenant                 neurox-demo (00000000-...-0001)
  Users                  7 (1 role each)
  Vendor master          24 vendors
  Invoice history        58 records
  Policies               PROC-001 v1.0 PUBLISHED, indexed (14 chunks)
                         AP-001   v1.0 PUBLISHED, indexed (11 chunks)
  Sanctions              OFAC 2026-07-28 OK · UN 2026-07-28 OK · EU NOT CONFIGURED
  Retrieval probe        PROC-001 OK · AP-001 OK

  Business-ready:        NO — EU sanctions source not configured
```

Never print passwords, keys, or signed URLs.

---

### 1.7 — Wire it in and delete the old script

- Expose as `python -m scripts.bootstrap` in the API image.
- Add `./scripts/stack.sh bootstrap`.
- Make `stack.sh doctor` tier 3 (from Phase 0) consume the same checks so the
  two cannot drift.
- **Delete** root `ingest_policies.py`.
- Keep `seed.py` as a thin entry point that calls the new bootstrap, or delete
  it and update the Compose `seed` service.

---

## Acceptance criteria

- [ ] From a clean volume: `product-up` then `bootstrap` reaches business-ready
      with no manual SQL, no file copying, no source edits.
- [ ] Running `bootstrap` twice changes nothing (verified by row counts and
      policy version IDs).
- [ ] A known CSV tax ID produces a blind index matching the stored vendor row.
- [ ] Retrieval returns correct citations for both policies immediately after
      bootstrap returns.
- [ ] With `SANCTIONS_EU_URL` empty, bootstrap completes and prints the explicit
      message above — not a stack trace.
- [ ] Seven users exist with exactly one role each.
- [ ] `stack.sh doctor` tier 3 goes green.
- [ ] `ingest_policies.py` is deleted.

---

## Estimated effort

4–5 days. Item 1.3's indexing wait is the subtle one — budget time to get the
polling and failure semantics right, because everything in Phase 3 and 4 depends
on retrieval actually working.
