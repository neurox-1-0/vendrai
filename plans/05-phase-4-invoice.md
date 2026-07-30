# Phase 4 — Invoice workflow stabilization

**Depends on:** Phases 1, 2 · **Parallel with:** Phase 3 · **Blocks:** Phases 5, 6
**Defects addressed:** D-011, D-012

---

## Why this phase exists

The invoice workflow is the **closest thing to a complete journey** in the
product. `AUDIT.md` §4.4 is right that it should be stabilized first and used as
the golden path.

Unlike the supplier side, the deterministic logic largely exists: three-way
matching, duplicate detection, tax arithmetic, missing-PO handling, and
bank-change protection are all implemented
([`invoice_agent.py`](../services/api/app/workers/invoice_agent.py), 2,003
lines). What is missing is (a) the reference data those checks need — Phase 1 —
and (b) proof that any of it works end to end on real documents.

The strategic value here: **one complete, demonstrable journey is worth more
than seven partial ones.** Get AP-001 fully working first, then the exceptions
fall out of the same machinery.

---

## What each scenario needs

From
[`expected_case_outcomes.json`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/expected_case_outcomes.json):

| Scenario | Expected status | Exception | Blocker today |
|---|---|---|---|
| AP-001 | `READY_FOR_AP_APPROVAL` | `NONE` | Extraction reliability only |
| AP-002 | `PROCUREMENT_REVIEW_REQUIRED` | `PRICE_VARIANCE` | Needs unit-price extraction (7.02% over PO, 2% tolerance) |
| AP-003 | `HOLD` | `QUANTITY_VARIANCE` | Needs line quantities (50 invoiced vs 40 received) |
| AP-004 | `BLOCKED_DUPLICATE` | `DUPLICATE_INVOICE` | **Invoice history not loaded** (Phase 1) |
| AP-005 | `TAX_REVIEW_REQUIRED` | `TAX_MISMATCH` | Needs configured reference tax rate (15% vs 18%) |
| AP-006 | `CLARIFICATION_REQUIRED` | `MISSING_PO` | Needs service-description extraction |
| AP-007 | `HOLD` | `BANK_DETAIL_MISMATCH` | **Vendor master not loaded** (Phase 1) |

Note AP-002 and AP-003 both require **line-item level** extraction — unit price
and quantity — which the current regex approach does not do. That is the single
biggest technical lift in this phase.

---

## Work items

### 4.1 — Make AP-001 the golden path

Before touching extraction breadth, get one scenario fully green end to end:
upload three PDFs → extract → resolve vendor → retrieve PO/GRN → three-way match
→ policy citation → AP approval task → human approval → idempotent ERP write.

Every subsequent scenario reuses this spine. Debugging it once, in isolation,
is far cheaper than debugging it seven times concurrently.

**Deliverable:** a documented, repeatable run with the case ID, the resulting
evidence, and the audit trail.

---

### 4.2 — Line-item extraction (D-011)

**The core technical gap.** Current extraction is regex/template-based and
document-level. AP-002 (unit price variance) and AP-003 (quantity variance)
require structured line items from all three document types:

```
invoice_line  { description, quantity, unit_price, line_total, tax_rate }
po_line       { description, quantity, unit_price, line_total }
grn_line      { description, quantity_received }
```

**Approach.** Docling already produces table structure
(`do_table_structure = True` in
[`document.py:159`](../services/api/app/workers/document.py#L159)) — but the
current code path flattens everything to text and discards the table
information. Use it:

1. Extract tables via Docling's structured output rather than re-parsing text.
2. Map columns to the schema above using header matching, with a deterministic
   fallback for headerless tables.
3. Persist line items as first-class evidence with page/bbox locators, so the UI
   can highlight the exact row that caused a variance.
4. Match lines across documents by normalized description, then quantity.

**Failure mode to design for:** partial extraction. If three of four lines
parse, the system must say so and route to review — not silently match on the
three it understood. Emit `LINE_ITEM_EXTRACTION_INCOMPLETE`.

---

### 4.3 — Field validation worth the name (D-012)

Current validation is non-empty, identifier length, and SWIFT length
(`AUDIT.md` §4.2). Add:

- **IBAN checksum** (mod-97) and **BIC structural validation**
- **Date parsing and sanity**: invoice date not in the future; GRN date not
  before PO date
- **Arithmetic consistency**: `Σ(line_total) + tax == gross_amount`; flag
  `INVOICE_ARITHMETIC_INCONSISTENT` when it does not reconcile
- **Currency consistency** across invoice/PO/GRN

The arithmetic check is high value and cheap: it catches a large class of
extraction errors before they reach matching, converting silent wrong answers
into visible extraction failures.

---

### 4.4 — Configurable tax reference (AP-005)

AP-005 expects "invoice tax rate is 15 percent while configured reference is 18
percent". The phrase *configured reference* is doing real work: the expected
rate must be **tenant configuration**, not a constant.

Add tenant tax configuration (jurisdiction → expected rate, effective dates) and
have the tax check compare against it. Same principle as Phase 3's thresholds:
business policy belongs in configuration.

---

### 4.5 — Duplicate invoice detection against real history (AP-004)

The logic exists; the data does not. Once Phase 1 loads
`existing_invoice_history.csv`, AP-004 should detect that the submitted invoice
number already exists for that vendor with status `PAID`.

Verify the match is on `(vendor_id, invoice_number)` — the model's unique
constraint — and that the finding names the prior record and its status, since
the expected finding is "same supplier and invoice number already recorded as
paid."

---

### 4.6 — Bank-detail change protection (AP-007)

Also data-blocked until Phase 1. AP-007 expects two distinct findings:

1. remittance account differs from the verified vendor master account
2. **the invoice instruction is insufficient to change bank details**

The second is the interesting one — it is a *policy* judgment, not a comparison.
A document asserting new bank details is not authorization to change them. This
must produce a protected review task requiring independent verification, and the
system must never update the vendor master from invoice content.

This is one of the strongest fraud-prevention demonstrations in the corpus.
Make sure the UI narrates *why* it is blocked, not just that it is.

---

### 4.7 — Provenance for uploaded PO/GRN

Carrying forward Phase 2's provenance work: user-uploaded PO and GRN documents
are **reference evidence**, not an authoritative ERP feed
(`AUDIT.md` §4.4, §6). Three-way match evidence must record and display this
distinction.

Without it, the product implicitly claims an ERP integration it does not have.

---

## Acceptance criteria

- [ ] AP-001 → `READY_FOR_AP_APPROVAL` with quantity, unit-price, and tax
      findings, through to an idempotent mock-ERP write.
- [ ] AP-002 → `PROCUREMENT_REVIEW_REQUIRED`, variance reported as 7.02%
      against a 2% tolerance.
- [ ] AP-003 → `HOLD`, reporting 50 invoiced vs 40 received.
- [ ] AP-004 → `BLOCKED_DUPLICATE`, naming the prior paid invoice.
- [ ] AP-005 → `TAX_REVIEW_REQUIRED`, 15% vs configured 18%.
- [ ] AP-006 → `CLARIFICATION_REQUIRED`, noting no PO reference and the
      emergency-freight description.
- [ ] AP-007 → `HOLD`, with both expected findings, and no vendor-master
      mutation.
- [ ] Line items carry page/bbox locators and appear in the UI.
- [ ] Arithmetic inconsistency is detected and surfaced.
- [ ] Tolerances and tax rates are tenant configuration.

---

## Sequencing note

4.1 first, alone. Then 4.2 (the big lift). 4.4–4.6 are small and can proceed in
parallel once Phase 1 has landed the reference data.

Resist starting all seven scenarios at once — they share a spine, and fixing the
spine seven times in parallel is how a week becomes three.

---

## Estimated effort

7–9 days, dominated by 4.2. If line-item extraction proves harder than expected
on these layouts, AP-002/AP-003 are the correct scenarios to descope
temporarily — the other five do not depend on it.
