# Phase 6 — Evaluation harness & metrics

**Depends on:** Phases 3, 4, 5 · **Blocks:** nothing (final proof)
**Defects addressed:** D-013, D-018

---

## Why this phase exists

The repository contains a 100-case evaluation manifest. It does not contain an
evaluation.

`evaluation/cases.jsonl` declares 100 cases with mutations and expected reason
codes. Nothing materializes the mutated documents, submits them, waits through
human tasks, scores the results, or reports metrics. `AUDIT.md` §8 is blunt and
correct: **do not claim the thresholds until this exists.**

The gap between "100 declared cases" and "100 scored cases" is the difference
between a plan and a result.

---

## What the manifest actually contains

Verified by parsing it:

| Dimension | Distribution |
|---|---|
| Workflow | 50 supplier · 50 invoice |
| Requires real Gemini | **100 of 100** |
| Resumable on quota | yes (flag present per case) |

**Supplier scenarios (50):** `LOW_QUALITY_SCAN` 10 · `PROMPT_INJECTION` 10 ·
`RETRIEVAL_AMBIGUITY` 10 · `CLEAN_ONBOARDING` 5 · `DUPLICATE` 5 ·
`SANCTIONS_CANDIDATE` 5 · `BANK_MISMATCH` 5 · `MISSING_DOCUMENT` 5 ·
`TRANSLITERATED_DUPLICATE` 5 · `CRITICAL_ID_CORRECTION` 5

**Invoice scenarios (50):** `CLEAN_THREE_WAY_MATCH` 5 · `PRICE_VARIANCE` 5 ·
`QUANTITY_VARIANCE` 5 · `DUPLICATE_INVOICE` 5 · `TAX_MISMATCH` 5 ·
`MISSING_PO` 5 · `BANK_CHANGE` 5

Two observations that shape the design:

1. **Every case requires real Gemini.** A full run is 100 live LLM workflows.
   Quota management is not an edge case — it is the primary operational
   constraint.
2. **Several scenarios depend on Phase 3 work that does not exist yet**
   (`PROMPT_INJECTION` needs the detector, `MISSING_DOCUMENT` needs the
   completeness matrix, `TRANSLITERATED_DUPLICATE` needs transliteration
   handling). Running this phase before Phase 3 lands would produce a
   meaningless score.

---

## The scoring oracle already exists

Worth stating plainly because it was not in the audit:
[`expected_case_outcomes.json`](../Vendrai_Procurement_Document_Corpus_v2/ground_truth/expected_case_outcomes.json)
provides, per base scenario, the expected status, risk level, findings, and
required human action.

Combined with `cases.jsonl`'s per-case `expected_reason_codes`, the scoring
ground truth does not need to be invented. That removes the single most
subjective part of building an evaluation harness.

---

## Architecture

Four separable components. Keeping them separate matters: materialization is
deterministic and cheap, execution is expensive and flaky, and you will re-run
scoring far more often than execution.

```
materializer  →  runner  →  scorer  →  reporter
   (deterministic)  (live, resumable)  (pure)   (pure)
```

### 6.1 — Materializer

Applies each case's declared `mutation` (e.g. `{contrast: 0.9, rotate_degrees: 0,
seed: 1}`) to the source PDFs, producing the actual documents to submit.

- **Deterministic**: same seed → byte-identical output. Assert this in a test;
  it is what makes the whole evaluation reproducible.
- Cache by content hash — materializing 100 cases repeatedly is wasted time.
- Emit a manifest of produced artifacts with hashes.

### 6.2 — Runner

Submits cases through the **public API** — same rule as Phase 1's bootstrap. An
evaluation that bypasses the API measures something other than the product.

Requirements that follow from "100 live Gemini workflows":

- **Checkpoint after every case.** A run that dies at case 87 must resume at 87,
  not 1. The manifest's `resumable_on_quota` flag exists for this.
- **Handle quota exhaustion as a first-class state**, not an error: pause,
  record, resume. Distinguish it from a genuine failure in the report.
- **Auto-resolve human tasks** via a deterministic policy (approve when the
  expected outcome says approve), recording that it was automated. Do not
  silently skip the gate — that would measure a different system.
- Bounded concurrency; respect rate limits.
- Isolated tenant per run, so evaluation data never contaminates demo data.

### 6.3 — Scorer

Pure function over recorded outputs. Metrics required by the plan:

| Metric | Definition |
|---|---|
| Field macro-F1 | Per extracted field vs ground truth, macro-averaged |
| Duplicate recall | Detected duplicates / actual duplicates |
| Duplicate exact-match accuracy | Correct vendor identified among candidates |
| Policy Recall@10 | Relevant clause in top 10 retrieved |
| Citation precision | Cited clauses that actually support the finding |
| Reason-code accuracy | Emitted vs `expected_reason_codes` |
| Status accuracy | Final status vs `expected_status` |
| Cross-tenant leakage | Must be exactly zero |

Report per-scenario as well as aggregate. An 85% aggregate hiding a 30%
`PROMPT_INJECTION` score is not useful information.

### 6.4 — Reporter

Evidence-linked output — every score traceable to the case, the documents, and
the persisted evidence that produced it. HTML or Markdown, committed as an
artifact with the commit SHA, model version, and dataset versions.

**Report the numbers that come out.** If field F1 is 0.62, publish 0.62. A
credible mediocre number beats an unverifiable good one, and the audit's core
criticism is precisely about claims outrunning evidence.

---

## 6.5 — Confidence calibration (D-013)

OCR and extraction confidence values are currently heuristic constants
(`AUDIT.md` §4.2). With 100 scored cases there is finally enough data to
calibrate them.

Produce a reliability curve (predicted confidence vs observed accuracy) and
adjust thresholds so that "0.8 confidence" means roughly 80% correct. Until
then, label them **extraction confidence heuristics**, not probabilities.

If calibration data proves insufficient, say so and keep the honest label. That
is an acceptable outcome; claiming calibration without it is not.

---

## Acceptance criteria

- [ ] Materializer is deterministic (seed → identical bytes, asserted in a test).
- [ ] A full 100-case run completes and is resumable mid-run.
- [ ] Quota exhaustion pauses and resumes without data loss.
- [ ] All metrics computed per-scenario and aggregate.
- [ ] Report links every score to case, documents, and evidence.
- [ ] Report records commit SHA, model version, dataset versions.
- [ ] Cross-tenant leakage is exactly zero.
- [ ] Published numbers are the measured numbers.

---

## Sequencing warning

Do not start this before Phases 3 and 4 are complete. Roughly a third of the
supplier manifest targets capabilities that Phase 3 builds
(`PROMPT_INJECTION`, `MISSING_DOCUMENT`, `TRANSLITERATED_DUPLICATE`). Running
earlier produces a score that measures unfinished work and invites the wrong
conclusion about where the problem is.

---

## Estimated effort

6–8 days, plus wall-clock time for runs. Budget real Gemini quota — 100 live
workflows, plus re-runs after fixes.
