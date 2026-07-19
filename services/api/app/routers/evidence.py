import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.models import ApprovalTask, AuditLog, Case, EvidenceItem
from app.schemas import EvidenceResponse


router = APIRouter(prefix="/cases", tags=["evidence", "audit"])
Db = Annotated[AsyncSession, Depends(get_db)]


async def _case_exists(db: AsyncSession, tenant_id: uuid.UUID, case_id: uuid.UUID) -> None:
    if not await db.scalar(select(Case.case_id).where(Case.case_id == case_id, Case.tenant_id == tenant_id)):
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})


@router.get("/{case_id}/evidence", response_model=EvidenceResponse)
async def get_evidence(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any("requester", "analyst", "approver", "auditor", "admin")
    await _case_exists(db, principal.tenant_id, case_id)
    items = (await db.execute(
        select(EvidenceItem).where(EvidenceItem.case_id == case_id, EvidenceItem.tenant_id == principal.tenant_id).order_by(EvidenceItem.created_at)
    )).scalars().all()
    task = await db.scalar(select(ApprovalTask).where(ApprovalTask.case_id == case_id).order_by(ApprovalTask.created_at.desc()))
    return EvidenceResponse(
        items=[{
            "evidence_item_id": str(item.evidence_item_id), "source_type": item.source_type,
            "source_id": item.source_id, "source_locator": item.source_locator, "claim": item.claim,
            "reason_code": item.reason_code, "confidence": item.confidence,
        } for item in items],
        evidence_hash=task.evidence_hash if task else None,
    )


@router.get("/{case_id}/audit")
async def get_audit(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any("auditor", "admin")
    await _case_exists(db, principal.tenant_id, case_id)
    logs = (await db.execute(
        select(AuditLog).where(AuditLog.case_id == case_id, AuditLog.tenant_id == principal.tenant_id).order_by(AuditLog.created_at)
    )).scalars().all()
    return [{
        "audit_log_id": str(log.audit_log_id), "action": log.action, "actor_type": log.actor_type,
        "actor_id": log.actor_id, "resource_type": log.resource_type, "resource_id": log.resource_id,
        "metadata": log.metadata_json, "previous_hash": log.previous_hash, "record_hash": log.record_hash,
        "created_at": log.created_at,
    } for log in logs]
