# Phase 3 — Supplier workflow completion

**Depends on:** Phases 1, 2 · **Parallel with:** Phase 4 · **Blocks:** Phases 5, 6
**Defects addressed:** D-014, D-015, D-016, D-021 (verify), D-022, D-023

---

## Why this phase exists

This is the largest functional gap between what the proposal promises and what
the code does. Of five supplier scenarios, two cannot pass at all today (VO-003,
VO-005), and one cannot produce its stated finding (VO-004).

The supplier worker currently executes exactly three checks: duplicate
detection, sanctions screening, and policy retrieval
([`agent.py:352-375`](../services/api/app/workers/agent.py#L352-L375)). The
corpus expects considerably more.

---

## What each scenario actually needs

Read from
[`expected_case_outcomes.json`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/expected_case_outcomes.json)
and the shipped case folders. This table is the specification for this phase.

| Scenario | Expected status | Required findings | Buildable today? |
|---|---|---|---|
| VO-001 | `READY_FOR_APPROVAL` | required documents present · bank beneficiary matches legal name · risk checks clear | Partly — no document-completeness check, no beneficiary check |
| VO-002 | `HUMAN_REVIEW_REQUIRED` | exact tax ID match to V000233 · exact bank match · legal name variation | Yes, once Phase 1 loads the vendor master |
| VO-003 | `ENHANCED_REVIEW_REQUIRED` | bank in HK but registered SG · spend > LKR 5M · data access declared · data stored outside LK · **DPA unavailable** · **insurance expired** | **No** — none of these controls exist |
| VO-004 | `CLARIFICATION_REQUIRED` | low OCR confidence · **document instruction attempting to override controls** · **risk service unavailable** | **No** — no injection detector, no risk service |
| VO-005 | `HUMAN_REVIEW_REQUIRED` | **beneficiary is an individual, not the legal supplier** · spend > LKR 5M · **possible adverse-media match** | **No** — needs Phase 2's `bank_consistency` plus adverse media |

Note VO-003's case folder ships **four** documents and deliberately omits the
tax registration certificate — the missing-document condition is part of the
test, which only works if a completeness check exists.

---

## Work items

### 3.1 — Required-document matrix (D-015)

**Problem.** Uploaded documents are processed; no rule states which documents a
supplier case *requires*. VO-001's first expected finding is literally "required
documents present", and VO-003 tests the negative case.

**Design.** A declarative, versioned requirements table rather than hardcoded
conditionals — the rules are policy, and policy changes:

```
document_type            required_when
-----------------------  ---------------------------------
supplier_onboarding_form always
tax_registration         always
bank_confirmation        always
insurance_certificate    always
infosec_questionnaire    data_access_declared
dpa                      data_stored_outside_country
beneficial_ownership     spend_above_threshold
```

This needs **document classification** first — currently documents are processed
without being typed. Classify from filename plus first-page content markers;
keep it deterministic and inspectable rather than model-based.

Emit a `document_completeness` capability producing `COMPLETE` /
`MISSING_REQUIRED` with the specific missing types, feeding clarification (3.5).

---

### 3.2 — Cross-border and financial risk controls (D-015)

VO-003 requires four distinct checks that do not exist:

| Check | Signal |
|---|---|
| Bank country vs registered country | bank in HK, entity registered SG → `BANKING_COUNTRY_MISMATCH` |
| Annual spend threshold | > LKR 5,000,000 → elevated approval routing |
| Data residency | data stored outside Sri Lanka → infosec review |
| DPA presence | data access declared + no DPA → `DPA_UNAVAILABLE` |

Thresholds (spend limit, approved countries) must be **tenant configuration**,
not constants in code. They are business policy and will be questioned; hardcoding
them repeats the mistake `AUDIT.md` §6 catalogues.

Add `certificate_expiry` as well: parse validity dates from insurance and
registration certificates and emit `CERTIFICATE_EXPIRED` — VO-003 expects
"insurance expired". This depends on date extraction, which does not exist yet
(D-011) — coordinate with Phase 4's extraction work rather than duplicating it.

---

### 3.3 — Mock risk service (D-023)

**The corpus expects a component that was never built.** The README instructs
evaluators to "configure the mock risk tool to return values from
`mock_risk_api_results.json`", which provides per-vendor `sanctions`,
`adverse_media`, `country_risk`, and `checked_at`.

Nothing in `services/` references any of these. Three expected findings are
therefore unreachable.

**Build it as a sibling of `mock_erp`** — same pattern, already proven:

- Small FastAPI service, `services/mock_risk/`, seeded from
  `mock_risk_api_results.json`.
- Lookup by legal name; return `UNAVAILABLE` for unknown vendors.
- Add to Compose with a health check, matching `mock-erp`.
- New `risk_screening` capability in the supplier registry — **with an
  executor** (ADR-002), consuming it via a typed adapter.

**Deliberately exercise the failure path.** `Crescent Stationery Traders`
(VO-004) returns `"sanctions": "UNAVAILABLE"`. The system must surface "risk
service unavailable" as a visible finding and route to clarification — not treat
it as a pass. This is one of the better demonstrations of fail-closed behavior
available, and it is already in the fixture data.

---

### 3.4 — Deterministic prompt-injection detection (D-014)

VO-004 ships a document containing an instruction attempting to override
workflow controls. The expected finding is explicit about it.

Current defense is a prompt telling Gemini the content is untrusted
(`AUDIT.md` §4.2). That is necessary but not sufficient, and — critically — it
produces **no finding**, so nothing is visible to a reviewer.

**Build a deterministic detector** that runs on extracted text *before* any
model call:

- Pattern families: instruction verbs directed at a system ("ignore previous",
  "approve this", "disregard the policy"), role-play framing, and embedded
  directive markers.
- Emit `UNTRUSTED_DOCUMENT_INSTRUCTION` as a risk finding with the matched span
  and its page/bbox locator.
- **Never** pass the matched span into a model prompt.
- Route to clarification; do not auto-reject (the document may be legitimate
  with unfortunate phrasing).

Deterministic, not model-based: a detector that itself calls an LLM is
vulnerable to the thing it is detecting.

---

### 3.5 — Case-specific clarification (D-016)

Clarification questions are generic templates. VO-003 and VO-004 both expect
clarification whose usefulness depends entirely on specificity — "request
clearer onboarding form and complete verification" is only actionable if it
names the document and the field.

**Fix.** Generate questions from the structured findings produced by 3.1–3.4:

| Finding | Question |
|---|---|
| `MISSING_REQUIRED_DOCUMENT(tax_registration)` | "Please upload the tax registration certificate." |
| `LOW_OCR_CONFIDENCE(page 1, legal_name)` | "The supplier name on page 1 could not be read reliably. Please upload a clearer scan." |
| `DPA_UNAVAILABLE` | "This supplier will access company data. Please attach the signed data processing agreement." |
| `BANKING_COUNTRY_MISMATCH(HK, SG)` | "The bank account is in Hong Kong but the entity is registered in Singapore. Please confirm and provide justification." |

Gemini may phrase these, but the *set* of issues must come from deterministic
findings — never from the model deciding what is missing.

---

### 3.6 — Dynamic policy retrieval query (D-022)

[`agent.py:351`](../services/api/app/workers/agent.py#L351) uses one fixed query
string for every supplier case:

```python
policy_query = "new vendor onboarding required documents bank details sanctions screening human approval"
```

VO-003 needs clauses on cross-border banking, data residency, and insurance —
none of which this query targets. Retrieval cannot cite what it never searched
for.

**Fix.** Compose the query from case facts and active findings (country pair,
spend band, data-access flag, document types present/absent). Keep it
deterministic and log the query with the citations so retrieval is auditable.

---

### 3.7 — Verify the duplicate signals end to end (D-021)

With Phase 1's vendor master loaded and Phase 2's `email_domain` wired, run
VO-002 and confirm the expected findings appear: exact tax ID match to V000233,
exact bank match, and name variation.

This is the first scenario that can be verified purely by running it, and it
validates the blind-index work from Phase 1. Treat a failure here as a Phase 1
regression, not a Phase 3 bug.

---

## Acceptance criteria

- [ ] VO-001 → `READY_FOR_APPROVAL` with all three expected findings.
- [ ] VO-002 → `HUMAN_REVIEW_REQUIRED` with tax, bank, and name-variation findings.
- [ ] VO-003 → `ENHANCED_REVIEW_REQUIRED` with all six expected findings.
- [ ] VO-004 → `CLARIFICATION_REQUIRED` with OCR-confidence, injection, and
      risk-unavailable findings; the injected instruction demonstrably does not
      alter the outcome.
- [ ] VO-005 → `HUMAN_REVIEW_REQUIRED` with beneficiary-mismatch and
      adverse-media findings.
- [ ] Every new capability has an executor (registry test from 2.2 passes).
- [ ] Thresholds are tenant configuration, not code constants.
- [ ] Clarification questions name specific documents and fields.

---

## Scope note

`AUDIT.md` §11.2 offers the option of removing VO-003 from promised scope. I
recommend **building it**: it is the scenario that best demonstrates
multi-control reasoning, and 3.2's controls are largely shared with 3.1 and 3.5.
The corpus was clearly designed with it as the centrepiece.

---

## Estimated effort

8–10 days. Item 3.1 (classification + completeness) is the foundation the rest
depend on — sequence it first. 3.3 is small and self-contained; good parallel
work.
