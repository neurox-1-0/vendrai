import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.domain.cases import CaseStatus, assert_transition
from app.models import ApprovalDecision, ApprovalTask, Case, Notification, OutboxEvent
from app.schemas import ApprovalDecisionRequest, ApprovalTaskResponse
from app.services.events import append_audit, append_case_event, enqueue_event


router = APIRouter(prefix="/approval-tasks", tags=["approvals"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[ApprovalTaskResponse])
async def list_approval_tasks(db: Db, principal: CurrentPrincipal, task_status: str = "PENDING"):
    principal.require_any("approver", "analyst", "auditor", "admin")
    tasks = (await db.execute(
        select(ApprovalTask).where(
            ApprovalTask.tenant_id == principal.tenant_id,
            ApprovalTask.status == task_status,
        ).order_by(ApprovalTask.created_at)
    )).scalars().all()
    return list(tasks)


@router.post("/{task_id}/decisions", response_model=ApprovalTaskResponse)
async def decide_approval(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
    if_match: Annotated[int, Header(alias="If-Match", ge=1)],
):
    principal.require_any("approver", "procurement_approver", "compliance_approver", "finance_approver", "admin")
    task = await db.scalar(
        select(ApprovalTask).where(ApprovalTask.approval_task_id == task_id, ApprovalTask.tenant_id == principal.tenant_id).with_for_update()
    )
    if not task:
        raise HTTPException(404, detail={"code": "APPROVAL_TASK_NOT_FOUND"})
    if "admin" not in principal.roles and task.assigned_role not in principal.roles:
        raise HTTPException(403, detail={"code": "APPROVAL_SCOPE_REQUIRED", "required_role": task.assigned_role})
    scoped_key = f"approval.decision:{task_id}:{idempotency_key}"
    if await db.scalar(select(OutboxEvent).where(OutboxEvent.tenant_id == principal.tenant_id, OutboxEvent.idempotency_key == scoped_key)):
        return task
    if task.status != "PENDING":
        raise HTTPException(409, detail={"code": "APPROVAL_ALREADY_DECIDED"})
    case = await db.scalar(select(Case).where(Case.case_id == task.case_id, Case.tenant_id == principal.tenant_id).with_for_update())
    if not case:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    if case.requester_user_id == principal.user_id and "admin" not in principal.roles:
        raise HTTPException(403, detail={"code": "SEGREGATION_OF_DUTIES"})
    if if_match != body.expected_version or case.current_version != body.expected_version or task.case_version != body.expected_version:
        raise HTTPException(409, detail={"code": "STALE_APPROVAL", "current_version": case.current_version})
    if body.evidence_hash != task.evidence_hash:
        raise HTTPException(409, detail={"code": "EVIDENCE_CHANGED"})
    invoice_override_tasks = {
        "INVOICE_EXCEPTION_RESOLUTION",
        "TAX_REVIEW",
        "PROCUREMENT_REVIEW",
        "DUPLICATE_REVIEW",
    }
    if body.decision == "APPROVED" and task.task_type in invoice_override_tasks and not body.comment:
        raise HTTPException(422, detail={"code": "OVERRIDE_COMMENT_REQUIRED"})

    decision = ApprovalDecision(
        tenant_id=principal.tenant_id, approval_task_id=task_id, decided_by=principal.user_id,
        decision=body.decision, edited_payload=body.edited_payload, comment=body.comment,
        evidence_hash=body.evidence_hash,
    )
    db.add(decision)
    task.status = body.decision
    task.completed_at = datetime.now(UTC)
    if body.decision == "APPROVED":
        assert_transition(case.status, CaseStatus.APPROVED)
        case.status = CaseStatus.APPROVED
        event_type = "approval.approved.v1"
        if task.task_type in ("INVOICE_EXCEPTION_RESOLUTION", "TAX_REVIEW", "PROCUREMENT_REVIEW", "INVOICE_AP_APPROVAL", "DUPLICATE_REVIEW"):
            next_event = "invoice.resolution.approved.v1"
        else:
            next_event = "erp.sync.requested.v1"
        next_status = CaseStatus.ERP_SYNC_PENDING
    elif body.decision == "REJECTED":
        assert_transition(case.status, CaseStatus.REJECTED)
        case.status = CaseStatus.REJECTED
        case.resolved_at = datetime.now(UTC)
        event_type = "approval.rejected.v1"
        next_event = None
        next_status = None
    elif body.decision == "MORE_INFO":
        assert_transition(case.status, CaseStatus.NEEDS_CLARIFICATION)
        case.status = CaseStatus.NEEDS_CLARIFICATION
        event_type = "approval.more_info.v1"
        next_event = None
        next_status = None
    else:
        # Escalation closes this decision task but deliberately leaves the case
        # in its current safety state. A fresh admin task keeps the workflow
        # actionable without inventing an invalid state transition.
        event_type = "approval.escalated.v1"
        next_event = None
        next_status = None
    case.current_version += 1
    if body.decision == "ESCALATED":
        db.add(
            ApprovalTask(
                tenant_id=principal.tenant_id,
                case_id=case.case_id,
                run_id=task.run_id,
                task_type=f"{task.task_type}_ESCALATED",
                status="PENDING",
                assigned_role="admin",
                proposed_action=task.proposed_action,
                evidence_packet=task.evidence_packet,
                evidence_hash=task.evidence_hash,
                case_version=case.current_version,
            )
        )
    await append_case_event(
        db, tenant_id=principal.tenant_id, case_id=case.case_id, event_type="APPROVAL_DECIDED",
        actor_type="USER", actor_id=str(principal.user_id), payload={"decision": body.decision, "status": case.status},
    )
    await db.flush()
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case.case_id,
        aggregate_version=case.current_version, event_type=event_type, idempotency_key=scoped_key,
        payload={"case_id": str(case.case_id), "task_id": str(task_id), "decision": body.decision},
    )
    if next_event and next_status:
        assert_transition(case.status, next_status)
        case.status = next_status
        case.current_version += 1
        enqueue_event(
            db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case.case_id,
            aggregate_version=case.current_version, event_type=next_event,
            idempotency_key=f"erp.request:{task_id}:{body.evidence_hash}",
            payload={"case_id": str(case.case_id), "approval_task_id": str(task_id), "evidence_hash": body.evidence_hash},
        )
        await append_case_event(
            db, tenant_id=principal.tenant_id, case_id=case.case_id, event_type="ERP_SYNC_QUEUED",
            actor_type="SYSTEM", actor_id="approval-service", payload={"status": case.status},
        )
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=case.case_id, actor_type="USER", actor_id=str(principal.user_id),
        action="APPROVAL_DECIDED", resource_type="APPROVAL_TASK", resource_id=str(task_id),
        metadata={"decision": body.decision, "evidence_hash": body.evidence_hash, "comment": body.comment},
    )
    notification = Notification(
        tenant_id=principal.tenant_id, user_id=case.requester_user_id, case_id=case.case_id,
        notification_type="APPROVAL_DECIDED", title=f"Case {case.case_number}: {body.decision}",
        body=body.comment or f"Your vendor onboarding case was {body.decision.lower()}.",
    )
    db.add(notification)
    await db.flush()
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="notification", aggregate_id=notification.notification_id,
        aggregate_version=1, event_type="notification.delivery.requested.v1",
        idempotency_key=f"notification.delivery:{notification.notification_id}:1",
        payload={"notification_id": str(notification.notification_id), "user_id": str(case.requester_user_id), "attempt": 1},
    )
    return task
