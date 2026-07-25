import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CASE_READ_ROLES, CurrentPrincipal
from app.database import get_db
from app.models import (
    ApprovalTask,
    AuditExport,
    AuditLog,
    Case,
    EvidenceItem,
    OutboxEvent,
)
from app.schemas import AuditExportResponse, EvidenceResponse
from app.services.events import append_audit, enqueue_event
from app.services.storage import store_private_export

router = APIRouter(prefix="/cases", tags=["evidence", "audit"])
Db = Annotated[AsyncSession, Depends(get_db)]


async def _authorized_case(
    db: AsyncSession,
    principal,
    case_id: uuid.UUID,
) -> Case:
    case = await db.scalar(
        select(Case).where(
            Case.case_id == case_id,
            Case.tenant_id == principal.tenant_id,
        )
    )
    if (
        not case
        or principal.is_requester_only
        and case.requester_user_id != principal.user_id
    ):
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    return case


@router.get("/{case_id}/evidence", response_model=EvidenceResponse)
async def get_evidence(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any(*CASE_READ_ROLES)
    await _authorized_case(db, principal, case_id)
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
    await _authorized_case(db, principal, case_id)
    logs = (await db.execute(
        select(AuditLog).where(AuditLog.case_id == case_id, AuditLog.tenant_id == principal.tenant_id).order_by(AuditLog.created_at)
    )).scalars().all()
    return [{
        "audit_log_id": str(log.audit_log_id), "action": log.action, "actor_type": log.actor_type,
        "actor_id": log.actor_id, "resource_type": log.resource_type, "resource_id": log.resource_id,
        "metadata": log.metadata_json, "previous_hash": log.previous_hash, "record_hash": log.record_hash,
        "created_at": log.created_at,
    } for log in logs]


def _export_response(record: AuditExport) -> AuditExportResponse:
    return AuditExportResponse(
        audit_export_id=record.audit_export_id,
        case_id=record.case_id,
        status=record.status,
        sha256=record.sha256,
        expires_at=record.expires_at,
        download_url=(
            f"/api/v1/audit-exports/{record.audit_export_id}/content"
        ),
    )


@router.post(
    "/{case_id}/audit-exports",
    response_model=AuditExportResponse,
    status_code=201,
)
async def create_audit_export(
    case_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=160),
    ],
    if_match: Annotated[int, Header(alias="If-Match", ge=1)],
):
    principal.require_any("auditor", "admin")
    case = await db.scalar(
        select(Case)
        .where(
            Case.case_id == case_id,
            Case.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if not case:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    if case.current_version != if_match:
        raise HTTPException(
            409,
            detail={
                "code": "STALE_CASE_VERSION",
                "current_version": case.current_version,
            },
        )
    scoped_key = f"audit.export:{case_id}:{idempotency_key}"
    existing_event = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == principal.tenant_id,
            OutboxEvent.idempotency_key == scoped_key,
        )
    )
    if existing_event:
        existing = await db.get(AuditExport, existing_event.aggregate_id)
        if existing:
            return _export_response(existing)
    logs = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.case_id == case_id,
                AuditLog.tenant_id == principal.tenant_id,
            )
            .order_by(AuditLog.created_at, AuditLog.audit_log_id)
        )
    ).scalars().all()
    evidence = (
        await db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.case_id == case_id,
                EvidenceItem.tenant_id == principal.tenant_id,
            )
            .order_by(EvidenceItem.created_at)
        )
    ).scalars().all()
    safe_payload = {
        "schema_version": 1,
        "case": {
            "case_id": str(case.case_id),
            "case_number": case.case_number,
            "case_type": case.case_type,
            "status": case.status,
            "version": case.current_version,
        },
        "audit_chain": [
            {
                "audit_log_id": str(log.audit_log_id),
                "action": log.action,
                "actor_type": log.actor_type,
                "actor_id": log.actor_id,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "metadata": log.metadata_json,
                "previous_hash": log.previous_hash,
                "record_hash": log.record_hash,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "evidence": [
            {
                "evidence_item_id": str(item.evidence_item_id),
                "source_type": item.source_type,
                "source_id": item.source_id,
                "source_locator": item.source_locator,
                "claim": item.claim,
                "reason_code": item.reason_code,
                "confidence": item.confidence,
            }
            for item in evidence
        ],
    }
    encoded = json.dumps(
        safe_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    export_id = uuid.uuid4()
    storage_key = (
        f"audit-exports/{principal.tenant_id}/{case_id}/{export_id}.json"
    )
    store_private_export(storage_key, encoded)
    record = AuditExport(
        audit_export_id=export_id,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        requested_by=principal.user_id,
        storage_key=storage_key,
        sha256=digest,
        status="READY",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db.add(record)
    enqueue_event(
        db,
        tenant_id=principal.tenant_id,
        aggregate_type="audit_export",
        aggregate_id=export_id,
        aggregate_version=1,
        event_type="audit.export.created.v1",
        idempotency_key=scoped_key,
        payload={
            "case_id": str(case_id),
            "audit_export_id": str(export_id),
            "sha256": digest,
        },
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="AUDIT_EXPORT_CREATED",
        resource_type="AUDIT_EXPORT",
        resource_id=str(export_id),
        metadata={
            "sha256": digest,
            "expires_at": record.expires_at.isoformat(),
        },
    )
    return _export_response(record)
