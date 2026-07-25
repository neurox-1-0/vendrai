import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal, Principal
from app.database import get_db
from app.domain.cases import CaseStatus, InvalidTransition, assert_transition
from app.models import AgentRun, ApprovalTask, Case, Document, OutboxEvent
from app.schemas import ActionAccepted, CaseCreate, CaseListResponse, CaseResponse
from app.services.events import append_audit, append_case_event, enqueue_event


router = APIRouter(prefix="/cases", tags=["cases"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)]
ExpectedVersion = Annotated[int, Header(alias="If-Match", ge=1)]


async def _tenant_case(db: AsyncSession, principal: Principal, case_id: uuid.UUID, for_update: bool = False) -> Case:
    statement = select(Case).where(Case.case_id == case_id, Case.tenant_id == principal.tenant_id)
    if for_update:
        statement = statement.with_for_update()
    case = (await db.execute(statement)).scalar_one_or_none()
    if not case:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    return case


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(case_in: CaseCreate, db: Db, principal: CurrentPrincipal, idempotency_key: IdempotencyKey):
    principal.require_any("requester", "analyst", "admin")
    scoped_key = f"case.create:{principal.user_id}:{idempotency_key}"
    existing_event = await db.scalar(
        select(OutboxEvent).where(OutboxEvent.tenant_id == principal.tenant_id, OutboxEvent.idempotency_key == scoped_key)
    )
    if existing_event:
        return await _tenant_case(db, principal, existing_event.aggregate_id)

    case_id = uuid.uuid4()
    case = Case(
        case_id=case_id,
        tenant_id=principal.tenant_id,
        case_number=f"VND-{datetime.now(UTC):%Y%m%d}-{str(case_id)[:8].upper()}",
        case_type="VENDOR_ONBOARDING",
        status=CaseStatus.DRAFT,
        requester_user_id=principal.user_id,
        title=case_in.title,
        priority=case_in.priority,
    )
    db.add(case)
    await db.flush()
    await append_case_event(
        db, tenant_id=principal.tenant_id, case_id=case.case_id, event_type="CASE_CREATED",
        actor_type="USER", actor_id=str(principal.user_id), payload={"status": CaseStatus.DRAFT},
    )
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case.case_id,
        aggregate_version=case.current_version, event_type="case.created.v1", idempotency_key=scoped_key,
        payload={"case_id": str(case.case_id), "case_type": case.case_type},
    )
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=case.case_id, actor_type="USER",
        actor_id=str(principal.user_id), action="CASE_CREATED", resource_type="CASE",
        resource_id=str(case.case_id), metadata={"case_number": case.case_number},
    )
    return case


@router.get("", response_model=CaseListResponse)
async def list_cases(
    db: Db,
    principal: CurrentPrincipal,
    case_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    principal.require_any("requester", "analyst", "approver", "auditor", "admin")
    filters = [Case.tenant_id == principal.tenant_id]
    if case_status:
        filters.append(Case.status == case_status)
    if principal.roles == {"requester"}:
        filters.append(Case.requester_user_id == principal.user_id)
    total = await db.scalar(select(func.count()).select_from(Case).where(*filters))
    items = (
        await db.execute(select(Case).where(*filters).order_by(Case.created_at.desc()).limit(limit).offset(offset))
    ).scalars().all()
    return CaseListResponse(items=list(items), total=int(total or 0))


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any("requester", "analyst", "approver", "auditor", "admin")
    case = await _tenant_case(db, principal, case_id)
    if principal.roles == {"requester"} and case.requester_user_id != principal.user_id:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    return case


@router.post("/{case_id}:submit", response_model=ActionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_case(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal, idempotency_key: IdempotencyKey, expected_version: ExpectedVersion):
    principal.require_any("requester", "analyst", "admin")
    case = await _tenant_case(db, principal, case_id, for_update=True)
    scoped_key = f"case.submit:{case_id}:{idempotency_key}"
    existing = await db.scalar(select(OutboxEvent).where(OutboxEvent.tenant_id == principal.tenant_id, OutboxEvent.idempotency_key == scoped_key))
    if existing:
        run = await db.scalar(select(AgentRun).where(AgentRun.case_id == case_id).order_by(AgentRun.created_at.desc()))
        return ActionAccepted(case_id=case_id, run_id=run.run_id if run else None, status=case.status, event_url=f"/api/v1/cases/{case_id}/events")
    if case.current_version != expected_version:
        raise HTTPException(409, detail={"code": "STALE_CASE_VERSION", "current_version": case.current_version})
    if case.status != CaseStatus.DRAFT:
        raise HTTPException(409, detail={"code": "CASE_INVALID_TRANSITION", "status": case.status})
    document_count = await db.scalar(
        select(func.count()).select_from(Document).where(
            Document.case_id == case_id, Document.tenant_id == principal.tenant_id,
            Document.processing_status.in_(["QUARANTINED", "QUEUED", "READY"]),
        )
    )
    if not document_count:
        raise HTTPException(409, detail={"code": "DOCUMENT_REQUIRED"})
    assert_transition(case.status, CaseStatus.SUBMITTED)
    case.status = CaseStatus.SUBMITTED
    case.current_version += 1
    case.submitted_at = datetime.now(UTC)
    run = AgentRun(
        tenant_id=principal.tenant_id, case_id=case.case_id, thread_id=f"case:{case.case_id}:v{case.current_version}",
        graph_name="invoice_exception" if case.case_type == "INVOICE_EXCEPTION" else "vendor_onboarding",
        status="QUEUED", current_node="document_processing", state_json={"case_id": str(case.case_id)},
    )
    db.add(run)
    await db.flush()
    await append_case_event(
        db, tenant_id=principal.tenant_id, case_id=case.case_id, event_type="CASE_SUBMITTED",
        actor_type="USER", actor_id=str(principal.user_id), payload={"run_id": str(run.run_id), "status": case.status},
    )
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case.case_id,
        aggregate_version=case.current_version,
        event_type="invoice.submitted.v1" if case.case_type == "INVOICE_EXCEPTION" else "case.submitted.v1",
        idempotency_key=scoped_key,
        payload={"case_id": str(case.case_id), "run_id": str(run.run_id)},
    )
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=case.case_id, actor_type="USER", actor_id=str(principal.user_id),
        action="CASE_SUBMITTED", resource_type="CASE", resource_id=str(case.case_id), metadata={"run_id": str(run.run_id)},
    )
    return ActionAccepted(case_id=case.case_id, run_id=run.run_id, status=case.status, event_url=f"/api/v1/cases/{case.case_id}/events")


@router.post("/{case_id}:cancel", response_model=ActionAccepted)
async def cancel_case(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal, idempotency_key: IdempotencyKey, expected_version: ExpectedVersion):
    principal.require_any("requester", "analyst", "admin")
    case = await _tenant_case(db, principal, case_id, for_update=True)
    if case.current_version != expected_version:
        raise HTTPException(409, detail={"code": "STALE_CASE_VERSION", "current_version": case.current_version})
    try:
        assert_transition(case.status, CaseStatus.CANCELLED)
    except InvalidTransition as exc:
        raise HTTPException(409, detail={"code": "CASE_INVALID_TRANSITION", "message": str(exc)}) from exc
    case.status = CaseStatus.CANCELLED
    case.current_version += 1
    await append_case_event(db, tenant_id=principal.tenant_id, case_id=case_id, event_type="CASE_CANCELLED", actor_type="USER", actor_id=str(principal.user_id), payload={})
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case_id,
        aggregate_version=case.current_version, event_type="case.cancelled.v1",
        idempotency_key=f"case.cancel:{case_id}:{idempotency_key}", payload={"case_id": str(case_id)},
    )
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=case_id, actor_type="USER", actor_id=str(principal.user_id),
        action="CASE_CANCELLED", resource_type="CASE", resource_id=str(case_id), metadata={"version": case.current_version},
    )
    return ActionAccepted(case_id=case_id, status=case.status)


@router.post("/{case_id}:retry-erp", response_model=ActionAccepted, status_code=202)
async def retry_erp(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal, idempotency_key: IdempotencyKey, expected_version: ExpectedVersion):
    principal.require_any("analyst", "approver", "admin")
    case = await _tenant_case(db, principal, case_id, for_update=True)
    if case.current_version != expected_version:
        raise HTTPException(409, detail={"code": "STALE_CASE_VERSION", "current_version": case.current_version})
    if case.status != CaseStatus.ERP_SYNC_FAILED:
        raise HTTPException(409, detail={"code": "ERP_RETRY_NOT_ALLOWED", "status": case.status})
    task = await db.scalar(select(ApprovalTask).where(
        ApprovalTask.case_id == case_id, ApprovalTask.status == "APPROVED",
    ).order_by(ApprovalTask.completed_at.desc()))
    if not task:
        raise HTTPException(409, detail={"code": "APPROVED_TASK_REQUIRED"})
    assert_transition(case.status, CaseStatus.ERP_SYNC_PENDING)
    case.status = CaseStatus.ERP_SYNC_PENDING
    case.current_version += 1
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case_id,
        aggregate_version=case.current_version, event_type="erp.sync.requested.v1",
        idempotency_key=f"erp.retry:{case_id}:{idempotency_key}",
        payload={"case_id": str(case_id), "approval_task_id": str(task.approval_task_id), "evidence_hash": task.evidence_hash},
    )
    await append_case_event(db, tenant_id=principal.tenant_id, case_id=case_id, event_type="ERP_SYNC_RETRY_QUEUED", actor_type="USER", actor_id=str(principal.user_id), payload={})
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=case_id, actor_type="USER", actor_id=str(principal.user_id),
        action="ERP_SYNC_RETRIED", resource_type="CASE", resource_id=str(case_id), metadata={"version": case.current_version},
    )
    return ActionAccepted(case_id=case_id, status=case.status)
