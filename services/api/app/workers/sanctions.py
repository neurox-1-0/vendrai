import asyncio
import uuid
from datetime import UTC, datetime

import httpx
from app.domain.security import normalize_vendor_name
from app.models import (
    InboxReceipt,
    SanctionsDataset,
    SanctionsEntityRecord,
    SanctionsImport,
)
from app.sanctions import (
    DownloadedDataset,
    configured_source_url,
    download_official_dataset,
    parse_official_dataset,
)
from app.services.events import enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from sqlalchemy import select


async def _download_with_retries(source: str, url: str) -> DownloadedDataset:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return await download_official_dataset(source, url)
        except (httpx.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(2 ** (attempt - 1))
    if last_error:
        raise last_error
    raise RuntimeError("SANCTIONS_DOWNLOAD_FAILED")


def _error_code(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "SANCTIONS_SOURCE_TIMEOUT"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"SANCTIONS_SOURCE_HTTP_{exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return "SANCTIONS_SOURCE_UNAVAILABLE"
    message = str(exc)
    if message.startswith("SANCTIONS_"):
        return message[:80]
    return "SANCTIONS_IMPORT_FAILED"


async def process_import(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    import_id = uuid.UUID(envelope["payload"]["sanctions_import_id"])
    source = str(envelope["payload"]["source"])
    source_url = configured_source_url(source)

    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(
                InboxReceipt,
                {"consumer_name": "sanctions-worker", "event_id": event_id},
            ):
                return
            job = await session.scalar(
                select(SanctionsImport)
                .where(SanctionsImport.sanctions_import_id == import_id)
                .with_for_update()
            )
            if not job or job.tenant_id != tenant_id:
                raise RuntimeError("SANCTIONS_IMPORT_NOT_FOUND")
            job.status = "RUNNING"
            job.started_at = datetime.now(UTC)

    try:
        downloaded = await _download_with_retries(source, source_url)
        records = await asyncio.to_thread(
            parse_official_dataset,
            source,
            downloaded.payload,
        )
        async with WorkerSession() as session:
            async with session.begin():
                await set_worker_tenant(session, str(tenant_id))
                job = await session.scalar(
                    select(SanctionsImport)
                    .where(SanctionsImport.sanctions_import_id == import_id)
                    .with_for_update()
                )
                existing = await session.scalar(
                    select(SanctionsDataset).where(
                        SanctionsDataset.source == source,
                        SanctionsDataset.version == downloaded.version,
                    )
                )
                dataset = existing or SanctionsDataset(
                    dataset_id=uuid.uuid4(),
                    source=source,
                    version=downloaded.version,
                    source_url=source_url,
                    sha256=downloaded.sha256,
                    status="STAGED",
                )
                if existing and existing.sha256 != downloaded.sha256:
                    raise ValueError("SANCTIONS_VERSION_HASH_CONFLICT")
                if not existing:
                    session.add(dataset)
                    await session.flush()
                    for record in records:
                        session.add(
                            SanctionsEntityRecord(
                                dataset_id=dataset.dataset_id,
                                external_id=record.external_id,
                                primary_name=record.primary_name,
                                normalized_name=normalize_vendor_name(
                                    record.primary_name
                                ),
                                aliases=record.aliases,
                                countries=record.countries,
                            )
                        )
                dataset.status = "PUBLISHED"
                dataset.published_at = datetime.now(UTC)
                job.status = "COMPLETED"
                job.dataset_id = dataset.dataset_id
                job.etag = downloaded.etag
                job.sha256 = downloaded.sha256
                job.entity_count = len(records)
                job.completed_at = datetime.now(UTC)
                session.add(
                    InboxReceipt(
                        consumer_name="sanctions-worker",
                        event_id=event_id,
                        tenant_id=tenant_id,
                    )
                )
                enqueue_event(
                    session,
                    tenant_id=tenant_id,
                    aggregate_type="sanctions_import",
                    aggregate_id=import_id,
                    aggregate_version=2,
                    event_type="sanctions.import.completed.v1",
                    idempotency_key=f"sanctions.import.completed:{import_id}",
                    payload={
                        "sanctions_import_id": str(import_id),
                        "source": source,
                        "dataset_id": str(dataset.dataset_id),
                        "entity_count": len(records),
                        "sha256": downloaded.sha256,
                    },
                )
    except Exception as exc:
        async with WorkerSession() as session:
            async with session.begin():
                await set_worker_tenant(session, str(tenant_id))
                job = await session.scalar(
                    select(SanctionsImport)
                    .where(SanctionsImport.sanctions_import_id == import_id)
                    .with_for_update()
                )
                if job:
                    job.status = "FAILED"
                    job.error_code = _error_code(exc)
                    job.completed_at = datetime.now(UTC)
                session.add(
                    InboxReceipt(
                        consumer_name="sanctions-worker",
                        event_id=event_id,
                        tenant_id=tenant_id,
                    )
                )
                enqueue_event(
                    session,
                    tenant_id=tenant_id,
                    aggregate_type="sanctions_import",
                    aggregate_id=import_id,
                    aggregate_version=2,
                    event_type="sanctions.import.failed.v1",
                    idempotency_key=f"sanctions.import.failed:{import_id}",
                    payload={
                        "sanctions_import_id": str(import_id),
                        "source": source,
                        "error_code": _error_code(exc),
                    },
                )


if __name__ == "__main__":
    asyncio.run(
        consume(
            "sanctions-worker",
            ["sanctions.import.requested.v1"],
            process_import,
        )
    )
