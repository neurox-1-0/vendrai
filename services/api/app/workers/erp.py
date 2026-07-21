import asyncio
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.config import settings
from app.domain.cases import CaseStatus
from app.domain.security import normalize_vendor_name
from app.models import ApprovalTask, Case, ErpOperation, InboxReceipt, Notification, Vendor
from app.services.events import append_audit, append_case_event, enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant


async def sync_erp(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    task_id = uuid.UUID(envelope["payload"]["approval_task_id"])
    evidence_hash = envelope["payload"]["evidence_hash"]
    idempotency_key = f"erp.vendor.create:{case_id}:{evidence_hash}"
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "erp-worker", "event_id": event_id}):
                return
            case = await session.get(Case, case_id, with_for_update=True)
            task = await session.get(ApprovalTask, task_id)
            if not case or case.tenant_id != tenant_id or not task:
                raise RuntimeError("ERP_CONTEXT_NOT_FOUND")
            if task.status != "APPROVED" or task.evidence_hash != evidence_hash or case.status != CaseStatus.ERP_SYNC_PENDING:
                raise RuntimeError("ERP_APPROVAL_GATE_REJECTED")
            existing = await session.scalar(select(ErpOperation).where(ErpOperation.tenant_id == tenant_id, ErpOperation.idempotency_key == idempotency_key))
            if existing and existing.status == "SUCCEEDED":
                session.add(InboxReceipt(consumer_name="erp-worker", event_id=event_id, tenant_id=tenant_id))
                return
            operation = existing or ErpOperation(
                tenant_id=tenant_id, case_id=case_id, approval_task_id=task_id,
                idempotency_key=idempotency_key, request_payload=task.proposed_action,
            )
            if not existing:
                session.add(operation)
            operation.attempts += 1
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        f"{settings.MOCK_ERP_URL}/v1/vendors",
                        json={**task.proposed_action.get("payload", {}), "approval_task_id": str(task_id), "evidence_hash": evidence_hash},
                        headers={"Idempotency-Key": idempotency_key},
                    )
                    response.raise_for_status()
                    result = response.json()
                operation.status = "SUCCEEDED"
                operation.response_payload = result
                operation.provider_reference = result["erp_vendor_id"]
                vendor_payload = task.proposed_action.get("payload", {})
                vendor = Vendor(
                    tenant_id=tenant_id, legal_name=vendor_payload.get("legal_name") or "Human-approved vendor",
                    normalized_legal_name=normalize_vendor_name(vendor_payload.get("legal_name") or "Human-approved vendor"),
                    registered_country=vendor_payload.get("registered_country"), status="ACTIVE",
                    erp_vendor_id=result["erp_vendor_id"],
                )
                session.add(vendor)
                await session.flush()
                case.vendor_id = vendor.vendor_id
                case.status = CaseStatus.COMPLETED
                case.current_version += 1
                case.resolved_at = datetime.now(UTC)
                await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="ERP_SYNC_COMPLETED", actor_type="SYSTEM", actor_id="erp-worker", payload={"erp_vendor_id": result["erp_vendor_id"]})
                await append_audit(session, tenant_id=tenant_id, case_id=case_id, actor_type="SYSTEM", actor_id="erp-worker", action="ERP_VENDOR_CREATED", resource_type="VENDOR", resource_id=str(vendor.vendor_id), metadata={"erp_vendor_id": result["erp_vendor_id"], "approval_task_id": str(task_id), "evidence_hash": evidence_hash})
                notification = Notification(
                    tenant_id=tenant_id, user_id=case.requester_user_id, case_id=case_id,
                    notification_type="CASE_COMPLETED", title=f"Case {case.case_number} completed",
                    body=f"Vendor creation was confirmed by the ERP as {result['erp_vendor_id']}.",
                )
                session.add(notification)
                await session.flush()
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="notification", aggregate_id=notification.notification_id,
                    aggregate_version=1, event_type="notification.delivery.requested.v1",
                    idempotency_key=f"notification.delivery:{notification.notification_id}:1",
                    payload={"notification_id": str(notification.notification_id), "user_id": str(case.requester_user_id), "attempt": 1},
                )
            except Exception as exc:
                operation.status = "FAILED"
                operation.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                case.status = CaseStatus.ERP_SYNC_FAILED
                case.current_version += 1
                await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="ERP_SYNC_FAILED", actor_type="SYSTEM", actor_id="erp-worker", payload={"retryable": True, "error_code": type(exc).__name__})
            session.add(InboxReceipt(consumer_name="erp-worker", event_id=event_id, tenant_id=tenant_id))


async def sync_invoice_resolution(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    task_id = uuid.UUID(envelope["payload"]["approval_task_id"])
    evidence_hash = envelope["payload"]["evidence_hash"]
    idempotency_key = f"erp.invoice.resolve:{case_id}:{evidence_hash}"
    
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "erp-worker", "event_id": event_id}):
                return
                
            case = await session.get(Case, case_id, with_for_update=True)
            task = await session.get(ApprovalTask, task_id)
            if not case or case.tenant_id != tenant_id or not task:
                raise RuntimeError("ERP_CONTEXT_NOT_FOUND")
            if task.status != "APPROVED" or task.evidence_hash != evidence_hash or case.status != CaseStatus.ERP_SYNC_PENDING:
                raise RuntimeError("ERP_APPROVAL_GATE_REJECTED")
                
            existing = await session.scalar(select(ErpOperation).where(ErpOperation.tenant_id == tenant_id, ErpOperation.idempotency_key == idempotency_key))
            if existing and existing.status == "SUCCEEDED":
                session.add(InboxReceipt(consumer_name="erp-worker", event_id=event_id, tenant_id=tenant_id))
                return
                
            operation = existing or ErpOperation(
                tenant_id=tenant_id, case_id=case_id, approval_task_id=task_id,
                idempotency_key=idempotency_key, request_payload=task.proposed_action,
            )
            if not existing:
                session.add(operation)
            operation.attempts += 1
            
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        f"{settings.MOCK_ERP_URL}/v1/invoice-exceptions/{case_id}/resolve",
                        json={**task.proposed_action.get("payload", {}), "approval_task_id": str(task_id), "evidence_hash": evidence_hash},
                        headers={"Idempotency-Key": idempotency_key},
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                operation.status = "SUCCEEDED"
                operation.response_payload = result
                operation.provider_reference = result.get("resolution_id")
                
                case.status = CaseStatus.COMPLETED
                case.current_version += 1
                case.resolved_at = datetime.now(UTC)
                
                await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="ERP_SYNC_COMPLETED", actor_type="SYSTEM", actor_id="erp-worker", payload={"resolution_id": result.get("resolution_id")})
                await append_audit(session, tenant_id=tenant_id, case_id=case_id, actor_type="SYSTEM", actor_id="erp-worker", action="ERP_INVOICE_RESOLVED", resource_type="CASE", resource_id=str(case_id), metadata={"approval_task_id": str(task_id), "evidence_hash": evidence_hash})
                
                notification = Notification(
                    tenant_id=tenant_id, user_id=case.requester_user_id, case_id=case_id,
                    notification_type="CASE_COMPLETED", title=f"Case {case.case_number} completed",
                    body="Invoice exception resolution was confirmed by the ERP.",
                )
                session.add(notification)
                await session.flush()
                
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="notification", aggregate_id=notification.notification_id,
                    aggregate_version=1, event_type="notification.delivery.requested.v1",
                    idempotency_key=f"notification.delivery:{notification.notification_id}:1",
                    payload={"notification_id": str(notification.notification_id), "user_id": str(case.requester_user_id), "attempt": 1},
                )
            except Exception as exc:
                operation.status = "FAILED"
                operation.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                case.status = CaseStatus.ERP_SYNC_FAILED
                case.current_version += 1
                await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="ERP_SYNC_FAILED", actor_type="SYSTEM", actor_id="erp-worker", payload={"retryable": True, "error_code": type(exc).__name__})
                
            session.add(InboxReceipt(consumer_name="erp-worker", event_id=event_id, tenant_id=tenant_id))


async def dispatch(envelope: dict) -> None:
    event_type = envelope["event_type"]
    if event_type == "erp.sync.requested.v1":
        await sync_erp(envelope)
    elif event_type == "invoice.resolution.approved.v1":
        await sync_invoice_resolution(envelope)


if __name__ == "__main__":
    asyncio.run(consume("erp-worker", ["erp.sync.requested.v1", "invoice.resolution.approved.v1"], dispatch))
