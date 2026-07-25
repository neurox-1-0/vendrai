"""Credential-safe live smoke test for the pinned structured-output model."""

import asyncio

from app.agents.contracts import ContradictionAnalysis
from app.llm_gateway import structured_reasoning_with_metadata


async def main() -> None:
    result = await structured_reasoning_with_metadata(
        (
            "Identify contradictions only. Use supplied evidence IDs and do not "
            "make an approval decision."
        ),
        {
            "_data_classification": "SYNTHETIC",
            "workflow_kind": "supplier",
            "reason_codes": [],
            "evidence": [
                {
                    "evidence_id": "synthetic-policy-1",
                    "source_type": "POLICY",
                    "reason_code": "POLICY_CLAUSE",
                    "claim": "Synthetic vendors require human approval.",
                }
            ],
        },
        ContradictionAnalysis,
    )
    print(
        {
            "status": "SUCCESS",
            "model": result.model,
            "model_version": result.model_version,
            "latency_ms": result.latency_ms,
            "contradiction_count": len(result.output.contradictions),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
