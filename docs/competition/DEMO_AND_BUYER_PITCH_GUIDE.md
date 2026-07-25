# Vendrai Demo and Buyer Pitch Guide

## Product in plain language

Vendrai investigates supplier onboarding and invoice exceptions before a human
makes the accountable decision. It reads messy documents, checks enterprise
records and policies, finds contradictions, asks for missing information,
prepares evidence, and carries an approved action into an ERP sandbox.

It does not replace procurement or finance accountability. It replaces the
manual searching, comparison, chasing, and evidence assembly that consumes
their time.

## The business problem

Supplier onboarding is slow because evidence arrives in different formats and
names, bank details, categories, and policies conflict. Invoice exceptions are
slow because AP staff must compare invoices, purchase orders, receipts, vendor
history, tolerances, and approvals across systems.

The result is:

- Delayed supplier activation and project starts.
- Delayed invoice resolution and supplier payment.
- Duplicate vendors and inconsistent master data.
- Fraud, sanctions, and bank-change exposure.
- Expensive manual investigation.
- Weak audit evidence scattered across messages and systems.

## Who buys it

- Chief Procurement Officer.
- Head of Accounts Payable.
- Shared-services leader.
- Finance controller.
- Vendor master-data owner.
- Compliance and internal audit.

## Value proposition

Vendrai turns an unstructured case into an evidence-backed, ERP-ready decision.
Humans spend time deciding, not searching.

Initial measurable outcomes:

- Lower supplier onboarding cycle time.
- Lower invoice exception handling time.
- Fewer duplicate vendor records.
- Higher first-time-right field extraction.
- Faster reviewer decisions.
- Complete evidence and audit coverage.
- Zero unauthorized ERP actions.

Do not claim a percentage improvement until it has been measured against the
synthetic evaluation baseline.

## Ninety-second pitch

“Supplier onboarding and invoice exceptions look like simple workflows, but the
hard part is not moving a form between people. The hard part is investigating
messy evidence across documents, policies, vendor records, purchase orders,
receipts, sanctions data, and human approvals.

Vendrai is a multi-agent investigation platform for that work. Specialist agents
collect evidence in parallel. A reasoning agent identifies contradictions and
chooses whether to investigate further, ask a targeted question, retry a failed
tool, or prepare a decision. A verifier rejects unsupported conclusions. Humans
remain in control of duplicate resolution, sanctions, bank changes, approvals,
and ERP execution.

In the product you can watch the actual path, latency, evidence, retries, and
human pauses. The result is not a chatbot answer—it is a traceable,
evidence-bound operation confirmed by the ERP sandbox.”

## Live demo navigation

### Opening

1. Open the work queue.
2. Explain that every row is live case state from PostgreSQL.
3. Start a new supplier case using an unseen synthetic document pack.
4. Do not begin by showing architecture slides.

### Supplier onboarding story

1. Upload the tax, bank, and supplier documents.
2. Show quarantine, scan, extraction, and local PII masking.
3. Open the execution map as document, entity, sanctions, and policy specialists
   run in parallel.
4. Point to real overlapping timing and the reason each agent was selected.
5. Show a contradiction or possible duplicate derived from the documents.
6. Resolve the targeted HITL task.
7. Show the graph resume from its checkpoint.
8. Open the evidence packet and source-page citation.
9. Approve using the correct role.
10. Confirm the ERP sandbox operation and open the audit record.

### Invoice exception story

1. Upload an invoice with a real synthetic variance.
2. Show invoice extraction and parallel PO, GRN, history, vendor, and policy
   investigation.
3. Show the three-way comparison and policy-supported tolerance.
4. Let the reasoning agent select the relevant review path.
5. Complete the human decision.
6. Show the exact ERP sandbox resolution and notification.

### Copilot story

Ask:

> Why is this case waiting, and how do I resolve it?

The copilot should answer with case evidence and then offer:

- “Show the blocking evidence.”
- “Highlight the required decision.”
- “Guide me through the review.”

Accept the guided action. The UI navigates and spotlights the correct component.
Then demonstrate a forbidden request:

> Approve this case for me.

The copilot must refuse and explain which authorized human role must decide.

### Failure recovery story

Use a controlled failure switch for a retryable non-production demo environment,
or temporarily stop one provider:

1. Show one specialist fail.
2. Show successful siblings remain complete.
3. Show retry status and reason code.
4. Restore the provider.
5. Resume and finish without replaying completed work.

Do not pre-script a successful result. A controlled fault is acceptable when it
changes a real service and the resulting events are genuine.

## What to say while the graph runs

- “These bars overlap because the checks are independent.”
- “The agent selected these capabilities from an allowlisted registry.”
- “This is the observable decision summary; private chain-of-thought is not
  stored or displayed.”
- “The policy citation and document location are the evidence for this route.”
- “Gemini may recommend the next investigation, but it cannot clear this control.”
- “The checkpoint means a human can respond later or a worker can restart
  without losing completed work.”

## What not to say

- “The AI makes all decisions.”
- “It can connect to any tool automatically.”
- “This is connected to SAP” unless it truly is.
- “The system is 100% accurate.”
- “The rules are all AI.”
- “We store the model’s reasoning.”
- “This dashboard is production-ready” before acceptance passes.

## Buyer-oriented navigation

For a procurement leader, show:

- Cycle time, queue age, ownership, supplier risk, and approval bottlenecks.

For AP, show:

- Exception category, three-way match, tolerance, missing evidence, and resolution.

For compliance, show:

- Dataset version, candidate evidence, human disposition, and audit trail.

For finance, show:

- Bank controls, segregation of duties, approval binding, and ERP confirmation.

For audit, show:

- Evidence lineage, versions, human decisions, hashes, and export.

## Demo preparation checklist

- Use only synthetic documents and identities.
- Use a fresh tenant and case.
- Confirm Gemini quota before the session.
- Refresh official sanctions snapshots in advance and show their timestamp.
- Keep the snapshot available if the public source is temporarily offline.
- Confirm policy documents are published and indexed.
- Run both golden paths twice from fresh state.
- Verify all demo users and roles.
- Verify the ERP sandbox starts with the expected synthetic records.
- Never hide a live failure; use the recovery story.
- Do not use a video, cached response or precomputed trace as the product demo.
  If a mandatory live dependency is unavailable, show the honest blocked state
  and recovery behavior or postpone that path.
