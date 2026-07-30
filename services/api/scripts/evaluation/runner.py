"""Execute evaluation cases through the public API, resumably.

Two requirements drive every design choice here, and both come from the
manifest: all 100 cases need a real LLM, and a run therefore takes hours and
will hit quota.

* **Checkpoint after every case.** A run that dies at case 87 resumes at 87,
  not at 1. Anything less makes the harness too expensive to use twice.
* **Quota exhaustion is a state, not an error.** It is recorded distinctly, so
  the report can say "83 executed, 17 paused on quota" instead of "17 failed",
  which would read as a product defect.

Cases are submitted through the public API for the same reason the bootstrap
is: an evaluation that bypasses the API measures something other than the
product.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from scripts.evaluation.manifest import EvaluationCase
from scripts.evaluation.materializer import MaterializedCase
from scripts.evaluation.scorer import CaseOutcome

#: Statuses that mean the workflow has stopped and is waiting for a human.
TERMINAL_STATUSES = frozenset(
    {
        "APPROVAL_PENDING",
        "DUPLICATE_REVIEW",
        "RISK_REVIEW",
        "NEEDS_CLARIFICATION",
        "VERIFICATION_FAILED",
        "BLOCKED_DUPLICATE",
        "HOLD",
        "COMPLETED",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        "ERP_SYNC_FAILED",
    }
)

#: Reason codes that mean the provider refused for capacity reasons. These are
#: a pause, not a result.
QUOTA_REASON_CODES = frozenset(
    {"LLM_QUOTA_EXHAUSTED", "LLM_RATE_LIMITED", "LLM_RESOURCE_EXHAUSTED"}
)


@dataclass
class Checkpoint:
    """Everything needed to resume a run, written after every case."""

    run_id: str
    tenant_id: str
    completed: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Checkpoint | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            run_id=payload["run_id"],
            tenant_id=payload["tenant_id"],
            completed=payload.get("completed", {}),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written whole then moved, so an interrupted write cannot leave a
        # truncated checkpoint that loses the whole run.
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(path)


class QuotaExhausted(RuntimeError):
    """The provider refused for capacity reasons. Pause, do not fail."""


@dataclass
class RunnerConfig:
    api_url: str
    tenant_id: uuid.UUID
    headers: dict[str, str]
    #: Bounded so the evaluation does not become its own load test.
    concurrency: int = 2
    case_timeout_seconds: int = 900
    poll_seconds: float = 5.0
    #: Stop the whole run after this many consecutive quota refusals rather
    #: than burning through the remaining cases against a closed door.
    quota_patience: int = 3


async def submit_case(
    client: httpx.AsyncClient,
    case: EvaluationCase,
    materialized: MaterializedCase,
    config: RunnerConfig,
) -> str:
    """Create a case and upload its documents through the public API."""
    endpoint = (
        "/invoices" if case.workflow == "INVOICE_EXCEPTION" else "/cases"
    )
    response = await client.post(
        endpoint,
        json={
            "title": f"{case.case_id} ({case.scenario})",
            "case_type": (
                "INVOICE_EXCEPTION"
                if case.workflow == "INVOICE_EXCEPTION"
                else "VENDOR_ONBOARDING"
            ),
        },
        headers={"Idempotency-Key": f"eval-create-{case.case_id}"},
    )
    response.raise_for_status()
    case_id = response.json()["case_id"]

    for index, document in enumerate(materialized.documents):
        await _upload(client, case_id, document.path, case.case_id, index)

    submit = await client.post(
        f"/cases/{case_id}:submit",
        json={"expected_version": 1},
        headers={"Idempotency-Key": f"eval-submit-{case.case_id}"},
    )
    submit.raise_for_status()
    return case_id


async def _upload(
    client: httpx.AsyncClient,
    case_id: str,
    path: Path,
    evaluation_case_id: str,
    index: int,
) -> None:
    initiate = await client.post(
        f"/cases/{case_id}/documents",
        json={
            "original_filename": path.name,
            "content_type": "application/pdf",
            "size_bytes": path.stat().st_size,
        },
        headers={"Idempotency-Key": f"eval-doc-{evaluation_case_id}-{index}"},
    )
    initiate.raise_for_status()
    upload = initiate.json()

    async with httpx.AsyncClient(timeout=120) as uploader:
        put = await uploader.put(
            upload["upload_url"],
            content=path.read_bytes(),
            headers={"Content-Type": "application/pdf"},
        )
        put.raise_for_status()

    complete = await client.post(
        f"/cases/{case_id}/documents/{upload['document_id']}:complete",
        json={"upload_token": upload["upload_token"]},
        headers={"Idempotency-Key": f"eval-done-{evaluation_case_id}-{index}"},
    )
    complete.raise_for_status()


async def await_outcome(
    client: httpx.AsyncClient,
    case_id: str,
    config: RunnerConfig,
) -> dict[str, Any]:
    """Poll until the workflow stops, or the case times out."""
    deadline = time.monotonic() + config.case_timeout_seconds
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = await client.get(f"/cases/{case_id}")
        response.raise_for_status()
        detail = response.json()
        reason_codes = set(detail.get("reason_codes") or [])
        if reason_codes & QUOTA_REASON_CODES:
            raise QuotaExhausted(", ".join(sorted(reason_codes & QUOTA_REASON_CODES)))
        if detail.get("status") in TERMINAL_STATUSES:
            return detail
        await asyncio.sleep(config.poll_seconds)
    raise TimeoutError(
        f"case {case_id} did not reach a terminal status within "
        f"{config.case_timeout_seconds}s (last status: {detail.get('status')})"
    )


async def resolve_human_task(
    client: httpx.AsyncClient,
    case_id: str,
    detail: dict[str, Any],
    *,
    approve: bool,
) -> None:
    """Auto-resolve the human gate, and record that it was automated.

    Skipping the gate entirely would measure a different system - one without
    a human control - so the gate is passed through deterministically rather
    than bypassed.
    """
    tasks = await client.get(f"/cases/{case_id}/approval-tasks")
    if not tasks.is_success:
        return
    pending = [
        task
        for task in (tasks.json().get("items") or tasks.json())
        if task.get("status") == "PENDING"
    ]
    for task in pending:
        await client.post(
            f"/approval-tasks/{task['task_id']}/decisions",
            json={
                "decision": "APPROVED" if approve else "REJECTED",
                "comment": "Resolved automatically by the evaluation runner.",
                "expected_version": detail.get("current_version"),
                "evidence_hash": task.get("evidence_hash"),
                "edited_payload": {},
            },
            headers={
                "Idempotency-Key": f"eval-decide-{task['task_id']}",
            },
        )


def outcome_from_detail(
    case: EvaluationCase,
    detail: dict[str, Any],
    evidence: dict[str, Any],
) -> CaseOutcome:
    packet = detail.get("evidence_packet") or {}
    return CaseOutcome(
        case_id=case.case_id,
        scenario=case.scenario,
        workflow=case.workflow,
        base_scenario=case.base_scenario,
        status=detail.get("status"),
        reason_codes=list(detail.get("reason_codes") or []),
        duplicate_candidates=list(packet.get("duplicate_candidates") or []),
        policy_citations=[
            item["source_id"]
            for item in evidence.get("items", [])
            if item.get("source_type") == "POLICY" and item.get("source_id")
        ],
    )
