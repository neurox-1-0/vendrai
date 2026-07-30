# Phase 2 — Correctness & honesty fixes

**Depends on:** nothing (can run alongside Phase 0) · **Blocks:** Phases 3, 4
**Defects addressed:** D-001, D-002, D-021 (scoring half)

---

## Why this phase exists

Every defect here shares one property: **the system reports that something
happened when it did not.**

That is categorically worse than a missing feature. A missing feature is visible
and can be planned around. A capability that appears in the execution plan but
never runs, or a vendor record with a fabricated legal name, corrupts the
evidence trail that the entire product's value rests on.

This phase is small — perhaps two days of code — and it is the highest
value-per-hour work in the plan. It is deliberately placed before the workflow
phases because building on top of a lying substrate wastes the work above it.

---

## Work items

### 2.1 — Supplier `bank_consistency`: implement or deregister (D-001)

**The defect.** The capability is registered for the supplier workflow at
[`planning.py:104-114`](../services/api/app/agents/planning.py#L104-L114):

```python
CapabilitySpec(
    capability_id="bank_consistency",
    workflow_kind="supplier",
    purpose="Investigate available bank and registration-country evidence.",
    prerequisites=["bank_account_available", "registered_country_available"],
    dependencies=["document_intelligence"],
    failure_policy="RETRYABLE",
)
```

The supplier worker builds `selected_operations` at
[`agent.py:352-375`](../services/api/app/workers/agent.py#L352-L375) and handles
exactly three capabilities: `duplicate_detection`, `sanctions_screening`,
`policy_retrieval`. There is no `bank_consistency` branch.

**What actually happens at runtime:** Gemini sees the capability in the
registry, may select it, the plan validates (it is not mandatory), the selection
is persisted and rendered in the UI execution map — and nothing executes. No
`AgentStep`, no finding, no error. The operator sees a bank check in the plan
and reasonably concludes the bank evidence was checked.

The invoice worker *does* implement it
([`invoice_agent.py:1364-1400`](../services/api/app/workers/invoice_agent.py#L1364-L1400)),
which makes this clearly an omission rather than a design choice.

**Decision: implement it.** VO-005 (bank beneficiary mismatch) is a promised
scenario and cannot pass without it. Deregistering would be the honest
short-term move, but the capability is needed two phases later regardless.

**Implementation.** Model it on the invoice version, adapted to supplier
semantics — the supplier question is *"is the bank account consistent with the
registered entity and its country?"*, not *"does it match a resolved vendor?"*:

- Compare the extracted beneficiary name against the extracted legal name
  (`normalize_vendor_name` + `string_similarity`, reusing
  [`intelligence.py`](../services/api/app/domain/intelligence.py)).
- Compare the bank's country against `registered_country`.
- Emit an `AgentStep` named `bank_consistency` with a real
  `input_summary`/`output_summary`, matching the shape of every other step.
- Dispositions: `CLEAR` · `MISMATCH` (→ risk finding, human review) ·
  `UNVERIFIED` (evidence absent → `PARTIAL`, not silent success).

Note the registry declares `failure_policy="RETRYABLE"` for supplier vs
`"BLOCKING"` for invoice. Preserve that difference — a supplier bank check
failing transiently should retry; a mismatch is a finding, not a failure.

---

### 2.2 — Make this class of defect structurally impossible

A one-off fix leaves the door open. Add a test that fails if any registered
capability has no executor:

```python
def test_every_registered_capability_has_an_executor():
    """A capability in the registry that no worker executes is a silent lie:
    it appears in the plan and the UI, but nothing runs."""
```

Implementation approach: have each worker expose the set of capability IDs it
can execute (a module-level constant next to the `selected_operations`
construction, or a registration decorator), then assert:

```
{spec.capability_id for spec in CAPABILITY_REGISTRY if spec.workflow_kind == k}
    == EXECUTORS[k]
```

for each workflow kind. This is a five-line test that permanently closes the
defect class. It belongs in CI.

See [ADR-002](./91-decisions.md#adr-002--a-registered-capability-must-be-executable-or-it-must-not-be-registered).

---

### 2.3 — Remove the fabricated vendor name (D-002)

[`erp.py:362-369`](../services/api/app/workers/erp.py#L362-L369):

```python
legal_name=(vendor_payload.get("legal_name") or "Human-approved vendor"),
normalized_legal_name=normalize_vendor_name(
    vendor_payload.get("legal_name") or "Human-approved vendor"
),
```

When authoritative vendor data is absent, the system invents an identity and
writes it to the vendor master. That record then becomes reference data for
future duplicate detection — the fabrication propagates.

**Fix.** Fail closed before the ERP write:

```python
legal_name = vendor_payload.get("legal_name")
if not legal_name:
    raise OperationFailed("VENDOR_LEGAL_NAME_UNAVAILABLE")
```

Use the worker's existing typed-failure mechanism so the reason code reaches the
UI and audit trail like any other blocking condition.

**Expect this to break something.** Any scenario that currently reaches ERP
creation without a legal name will now correctly fail. That is the fix working.
Do not restore the fallback — trace the missing extraction upstream (Phase 3
work) instead.

See [ADR-003](./91-decisions.md#adr-003--missing-authoritative-data-fails-closed-never-defaults).

---

### 2.4 — Complete the `email_domain` duplicate signal (D-021)

Phase 1 adds the column and loads the data. Here, use it:

[`agent.py:71-83`](../services/api/app/workers/agent.py#L71-L83) passes
`email_domain` for the incoming case but omits `candidate_email_domain`, so
`email_domain_exact` in
[`intelligence.py:73-90`](../services/api/app/domain/intelligence.py#L73-L90)
is always `False`.

Add `candidate_email_domain=vendor.email_domain` and a unit test asserting the
signal fires for a matching domain. Without the test this silently regresses —
it already did once.

---

### 2.5 — Evidence provenance labelling

`AUDIT.md` §6 flags that uploaded PO/GRN documents are treated as matching
reference evidence. For a synthetic workflow that is acceptable; presenting them
as authoritative ERP data is not.

Add an explicit `source` / `provenance` field to evidence records
(`USER_UPLOADED` vs `ERP_SYSTEM_OF_RECORD` vs `EXTERNAL_OFFICIAL_LIST`) and
surface it in the case UI. Small change, meaningful honesty improvement, and it
pre-empts the obvious reviewer question.

---

### 2.6 — Never present projected timing as measured latency

The UI can render projected execution nodes before completion
(`AUDIT.md` §6, §4.7). That is genuinely good UX — but a projected duration
displayed in the same style as a measured one is a false claim about system
behavior.

Audit the execution-map components and ensure projected nodes are visually and
semantically distinct (different styling *and* an accessible label), and that
no projected value is ever labelled "latency" or "duration."

---

## Acceptance criteria

- [ ] Supplier `bank_consistency` emits a real `AgentStep` with correct
      disposition on a live case; a mismatch produces a risk finding and a
      human review task.
- [ ] The registry/executor consistency test exists, passes, and fails when a
      capability is deliberately removed from a worker.
- [ ] ERP creation with no legal name fails with `VENDOR_LEGAL_NAME_UNAVAILABLE`
      and writes no vendor row.
- [ ] `email_domain_exact` fires for a matching domain (unit test).
- [ ] Evidence records carry provenance and the UI shows it.
- [ ] No projected value is presented as a measured one.
- [ ] Full backend suite still passes.

---

## A note on sequencing

Run this alongside Phase 0 if capacity allows. These fixes are self-contained
and touch different files than the startup work.

They must land **before** Phase 1's acceptance is judged: a bootstrap that
reports "business-ready" for a workflow containing an unexecuted capability is
not reporting the truth.

---

## Estimated effort

2 days. Item 2.1 is most of it; 2.2 is thirty minutes and prevents a recurrence
class.
