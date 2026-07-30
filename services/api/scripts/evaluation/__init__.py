"""The 100-case evaluation harness.

The repository shipped a 100-case manifest and no evaluation. Nothing
materialised the mutated documents, submitted them, waited through the human
gates, scored the results, or reported metrics - so the thresholds the manifest
implies could not be claimed, and the audit was right to say so.

Four separable stages. Keeping them separate matters because they have very
different costs: materialisation is deterministic and cheap, execution is
expensive and flaky, and scoring gets re-run far more often than execution.

    materializer  ->  runner  ->  scorer  ->  reporter
    (deterministic)   (live,       (pure)     (pure)
                      resumable)

Two facts about the manifest shape everything here:

1. **All 100 cases require a real LLM.** A full run is 100 live workflows, so
   quota management is the primary operational constraint rather than an edge
   case. The runner checkpoints after every case.
2. **The scoring oracle already exists.** ``expected_case_outcomes.json`` gives
   per-scenario expected status, risk, findings, and required human action.
   Nothing subjective has to be invented.

See plans/07-phase-6-evaluation.md.
"""

from scripts.evaluation.materializer import materialize_case, materialize_manifest
from scripts.evaluation.scorer import score_run

__all__ = ["materialize_case", "materialize_manifest", "score_run"]
