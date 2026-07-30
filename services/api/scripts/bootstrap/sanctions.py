"""Drive the sanctions imports, and report a missing source as a decision.

``SANCTIONS_EU_URL`` is empty by default, and sanctions screening fails closed
when a required source is missing. That behaviour is correct - an unavailable
check must never read as a pass - but it means a clean install blocks every
supplier scenario at screening, with a message that looks like a bug.

The remedy is not to weaken the control. It is to end the bootstrap with one
explicit, actionable sentence telling the operator exactly what to configure,
instead of a stack trace or a silent skip.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

from app.config import settings
from app.domain.intelligence import current_sanctions_datasets
from app.models import SanctionsDataset
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.bootstrap.api_client import AdminApiClient

SOURCES: tuple[str, ...] = ("OFAC", "UN", "EU")

EU_NOT_CONFIGURED_MESSAGE = """\
SANCTIONS_EU_URL is not configured. Supplier scenarios will block at
sanctions screening (fail-closed by design).

Set an approved official EU export URL in .env, or re-run with
--allow-missing-eu-sanctions to bootstrap for invoice-only testing."""


@dataclass
class ImportOutcome:
    source: str
    status: str
    detail: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCEEDED"


def configured_sources() -> dict[str, bool]:
    return {
        "OFAC": bool(settings.SANCTIONS_OFAC_URL),
        "UN": bool(settings.SANCTIONS_UN_URL),
        "EU": bool(settings.SANCTIONS_EU_URL),
    }


async def import_source(
    api: AdminApiClient,
    source: str,
    *,
    timeout_seconds: int = 300,
    poll_seconds: float = 3.0,
) -> ImportOutcome:
    response = await api.post(
        "/admin/sanctions-imports",
        json={"source": source},
        idempotency_key=f"bootstrap-sanctions-{source}",
    )
    if response.status_code == 409:
        detail = response.json().get("detail", {})
        return ImportOutcome(
            source=source,
            status="NOT_CONFIGURED",
            detail=str(detail.get("code", "SANCTIONS_SOURCE_NOT_CONFIGURED")),
        )
    if response.status_code not in {200, 202}:
        return ImportOutcome(
            source=source,
            status="FAILED",
            detail=f"HTTP {response.status_code}: {response.text[:200]}",
        )

    job = response.json()
    import_id = job["sanctions_import_id"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        # The worker's actual vocabulary (services/api/app/workers/sanctions.py)
        # is QUEUED -> RUNNING -> COMPLETED/FAILED. Checking for "SUCCEEDED"
        # here never matched, so a job that finished in seconds still burned
        # the full timeout before being reported - wrongly - as TIMED_OUT.
        if job.get("status") in {"COMPLETED", "FAILED"}:
            break
        await asyncio.sleep(poll_seconds)
        poll = await api.get(f"/admin/sanctions-imports/{import_id}")
        if poll.status_code != 200:
            return ImportOutcome(
                source=source,
                status="FAILED",
                detail=f"status poll returned HTTP {poll.status_code}",
            )
        job = poll.json()

    if job.get("status") == "COMPLETED":
        return ImportOutcome(
            source=source,
            status="SUCCEEDED",
            detail=f"{job.get('entity_count', 0)} entities",
        )
    if job.get("status") == "FAILED":
        return ImportOutcome(
            source=source,
            status="FAILED",
            detail=str(job.get("error_code") or "import failed"),
        )
    return ImportOutcome(
        source=source,
        status="TIMED_OUT",
        detail=f"still {job.get('status', 'unknown')} after {timeout_seconds}s",
    )


async def dataset_state(
    session: AsyncSession,
    _tenant_id: uuid.UUID,
) -> tuple[list[str], list[str], list[str]]:
    """Report which mandatory sanctions sources are current, missing, or stale.

    Delegates the judgement to the same domain function the supplier worker
    uses, so the bootstrap cannot report a state screening would disagree with.
    """
    published = (
        await session.execute(
            select(SanctionsDataset).where(SanctionsDataset.status == "PUBLISHED")
        )
    ).scalars().all()
    active, missing, stale = current_sanctions_datasets(
        list(published),
        max_age_hours=settings.SANCTIONS_MAX_AGE_HOURS,
    )
    return (
        [f"{item.source} {item.version}" for item in active],
        missing,
        stale,
    )
