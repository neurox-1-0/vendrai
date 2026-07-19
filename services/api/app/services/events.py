import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.security import chained_audit_hash
from app.models import AuditLog, CaseEvent, OutboxEvent


async def append_case_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    event_type: str,
    actor_type: str,
    actor_id: str | None,
    payload: dict[str, Any],
) -> CaseEvent:
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"case-event:{case_id}"})
    sequence = await db.scalar(select(func.coalesce(func.max(CaseEvent.sequence), 0) + 1).where(CaseEvent.case_id == case_id))
    event = CaseEvent(
        tenant_id=tenant_id,
        case_id=case_id,
        sequence=int(sequence or 1),
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        payload=payload,
    )
    db.add(event)
    return event


def enqueue_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    aggregate_version: int,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any],
    correlation_id: uuid.UUID | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id or uuid.uuid4(),
        payload=payload,
    )
    db.add(event)
    return event


async def append_audit(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID | None,
    actor_type: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: dict[str, Any],
) -> AuditLog:
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"audit:{tenant_id}"})
    previous_hash = await db.scalar(
        select(AuditLog.record_hash)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.audit_log_id.desc())
        .limit(1)
    )
    record = {
        "tenant_id": str(tenant_id), "case_id": str(case_id) if case_id else None,
        "actor_type": actor_type, "actor_id": actor_id, "action": action,
        "resource_type": resource_type, "resource_id": resource_id, "metadata": metadata,
    }
    audit = AuditLog(
        tenant_id=tenant_id, case_id=case_id, actor_type=actor_type, actor_id=actor_id,
        action=action, resource_type=resource_type, resource_id=resource_id,
        metadata_json=metadata, previous_hash=previous_hash,
        record_hash=chained_audit_hash(previous_hash, record),
    )
    db.add(audit)
    return audit
