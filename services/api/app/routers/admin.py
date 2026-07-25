import asyncio
import shutil
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.config import settings
from app.database import get_db
from app.domain.intelligence import current_sanctions_datasets
from app.llm_gateway import probe_provider
from app.models import OutboxEvent, SanctionsDataset, SanctionsImport
from app.sanctions import configured_source_url, validate_source_url
from app.schemas import (
    IntegrationCheck,
    IntegrationHealthResponse,
    SanctionsDatasetResponse,
    SanctionsImportRequest,
    SanctionsImportResponse,
)
from app.services.events import append_audit, enqueue_event
from app.services.storage import probe_storage
from app.workers.common import open_broker
from app.workers.notification import probe_smtp

router = APIRouter(prefix="/admin", tags=["admin"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]


def _check(
    status: str,
    *,
    error_code: str | None = None,
    action: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> IntegrationCheck:
    return IntegrationCheck(
        status=status,
        error_code=error_code,
        action=action,
        metadata=metadata or {},
    )


async def _redis_check() -> IntegrationCheck:
    client = Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        await client.ping()
        return _check("HEALTHY")
    except Exception:
        return _check(
            "UNAVAILABLE",
            error_code="REDIS_UNAVAILABLE",
            action="Restore Redis before accepting mutations.",
        )
    finally:
        await client.aclose()


async def _rabbit_check() -> IntegrationCheck:
    try:
        connection = await asyncio.wait_for(open_broker(), timeout=5)
        await connection.close()
        return _check("HEALTHY")
    except Exception:
        return _check(
            "UNAVAILABLE",
            error_code="BROKER_UNAVAILABLE",
            action="Restore RabbitMQ; queued database outbox events remain durable.",
        )


async def _http_check(url: str, error_code: str) -> IntegrationCheck:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            response.raise_for_status()
        return _check("HEALTHY")
    except Exception:
        return _check("UNAVAILABLE", error_code=error_code)


@router.get("/integrations/health", response_model=IntegrationHealthResponse)
async def integration_health(db: Db, principal: CurrentPrincipal):
    principal.require_any("admin")
    await db.execute(text("SELECT 1"))
    (
        redis_check,
        rabbit_check,
        qdrant_check,
        opa_check,
        erp_check,
        llm,
        storage,
        smtp,
    ) = (
        await asyncio.gather(
            _redis_check(),
            _rabbit_check(),
            _http_check(f"{settings.QDRANT_URL}/collections", "QDRANT_UNAVAILABLE"),
            _http_check(f"{settings.OPA_URL}/health", "OPA_UNAVAILABLE"),
            _http_check(f"{settings.MOCK_ERP_URL}/health", "ERP_UNAVAILABLE"),
            probe_provider(),
            asyncio.to_thread(probe_storage),
            asyncio.to_thread(probe_smtp),
        )
    )
    latest_datasets = (
        await db.execute(
            select(SanctionsDataset)
            .where(SanctionsDataset.status == "PUBLISHED")
            .order_by(SanctionsDataset.published_at.desc())
        )
    ).scalars().all()
    _, missing_sources, stale_sources = current_sanctions_datasets(
        list(latest_datasets),
        max_age_hours=settings.SANCTIONS_MAX_AGE_HOURS,
        now=datetime.now(UTC),
    )
    sanctions = (
        _check(
            "UNAVAILABLE",
            error_code="SANCTIONS_DATA_UNAVAILABLE",
            action="Import current OFAC, UN and EU datasets.",
            metadata={"missing_sources": ",".join(missing_sources)},
        )
        if missing_sources
        else _check(
            "DEGRADED",
            error_code="SANCTIONS_DATA_STALE",
            action="Refresh stale official sanctions datasets.",
            metadata={"stale_sources": ",".join(stale_sources)},
        )
        if stale_sources
        else _check("HEALTHY")
    )
    llm_status = str(llm.get("status", "UNAVAILABLE"))
    llm_action = None
    if llm.get("error_code") == "LLM_QUOTA_EXCEEDED":
        llm_action = "Increase Gemini project quota or enable billing."
    elif llm.get("error_code") == "LLM_AUTH_INVALID":
        llm_action = "Replace the server-side Gemini authorization key."
    checks = {
        "database": _check("HEALTHY"),
        "redis": redis_check,
        "rabbitmq": rabbit_check,
        "object_storage": _check(
            str(storage.get("status", "UNAVAILABLE")),
            error_code=storage.get("error_code"),
            metadata={"backend": storage.get("backend")},
        ),
        "qdrant": qdrant_check,
        "opa": opa_check,
        "ocr": _check(
            "HEALTHY" if shutil.which("tesseract") else "UNAVAILABLE",
            error_code=None if shutil.which("tesseract") else "TESSERACT_UNAVAILABLE",
        ),
        "gemini": _check(
            llm_status,
            error_code=str(llm.get("error_code")) if llm.get("error_code") else None,
            action=llm_action,
            metadata={
                "model": str(llm.get("model") or settings.DEFAULT_MODEL),
                "upgrade_required": bool(llm.get("upgrade_required", False)),
            },
        ),
        "sanctions": sanctions,
        "smtp": _check(
            str(smtp.get("status", "UNAVAILABLE")),
            error_code=smtp.get("error_code"),
        ),
        "erp": erp_check,
    }
    overall = (
        "HEALTHY"
        if all(item.status in {"HEALTHY", "DISABLED"} for item in checks.values())
        else "DEGRADED"
    )
    return IntegrationHealthResponse(status=overall, checks=checks)


@router.post(
    "/sanctions-imports",
    response_model=SanctionsImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_sanctions_import(
    body: SanctionsImportRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
):
    principal.require_any("admin")
    scoped_key = (
        f"sanctions.import:{principal.tenant_id}:{body.source}:{idempotency_key}"
    )
    existing_event = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == principal.tenant_id,
            OutboxEvent.idempotency_key == scoped_key,
        )
    )
    if existing_event:
        existing_job = await db.get(SanctionsImport, existing_event.aggregate_id)
        if existing_job:
            return existing_job

    source_url = configured_source_url(body.source)
    if not source_url:
        raise HTTPException(
            409,
            detail={
                "code": "SANCTIONS_SOURCE_NOT_CONFIGURED",
                "source": body.source,
            },
        )
    try:
        validate_source_url(body.source, source_url)
    except ValueError as exc:
        raise HTTPException(
            409,
            detail={
                "code": str(exc),
                "source": body.source,
            },
        ) from exc

    job = SanctionsImport(
        sanctions_import_id=uuid.uuid4(),
        tenant_id=principal.tenant_id,
        source=body.source,
        source_url=source_url,
        status="QUEUED",
        requested_by=principal.user_id,
    )
    db.add(job)
    await db.flush()
    enqueue_event(
        db,
        tenant_id=principal.tenant_id,
        aggregate_type="sanctions_import",
        aggregate_id=job.sanctions_import_id,
        aggregate_version=1,
        event_type="sanctions.import.requested.v1",
        idempotency_key=scoped_key,
        payload={
            "sanctions_import_id": str(job.sanctions_import_id),
            "source": body.source,
        },
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=None,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="SANCTIONS_IMPORT_REQUESTED",
        resource_type="SANCTIONS_IMPORT",
        resource_id=str(job.sanctions_import_id),
        metadata={"source": body.source},
    )
    return job


@router.get(
    "/sanctions-imports/{sanctions_import_id}",
    response_model=SanctionsImportResponse,
)
async def get_sanctions_import(
    sanctions_import_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any("admin", "auditor")
    job = await db.scalar(
        select(SanctionsImport).where(
            SanctionsImport.sanctions_import_id == sanctions_import_id,
            SanctionsImport.tenant_id == principal.tenant_id,
        )
    )
    if not job:
        raise HTTPException(
            404,
            detail={"code": "SANCTIONS_IMPORT_NOT_FOUND"},
        )
    return job


@router.get(
    "/sanctions-datasets",
    response_model=list[SanctionsDatasetResponse],
)
async def list_sanctions_datasets(
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any("admin", "auditor", "compliance_approver")
    return list(
        (
            await db.execute(
                select(SanctionsDataset).order_by(
                    SanctionsDataset.source,
                    SanctionsDataset.published_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
