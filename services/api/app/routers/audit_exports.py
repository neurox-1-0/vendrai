import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.config import settings
from app.database import get_db
from app.models import AuditExport
from app.services.storage import local_object_path, presigned_download_url

router = APIRouter(prefix="/audit-exports", tags=["audit"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{export_id}/content")
async def download_audit_export(
    export_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any("auditor", "admin")
    record = await db.scalar(
        select(AuditExport).where(
            AuditExport.audit_export_id == export_id,
            AuditExport.tenant_id == principal.tenant_id,
        )
    )
    if not record:
        raise HTTPException(404, detail={"code": "AUDIT_EXPORT_NOT_FOUND"})
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(410, detail={"code": "AUDIT_EXPORT_EXPIRED"})
    filename = f"neurox-audit-{record.case_id}.json"
    if settings.STORAGE_BACKEND == "s3":
        return RedirectResponse(
            presigned_download_url(record.storage_key, filename),
            status_code=307,
        )
    path = local_object_path(record.storage_key)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "AUDIT_EXPORT_NOT_FOUND"})
    return FileResponse(
        path,
        media_type="application/json",
        filename=filename,
    )
