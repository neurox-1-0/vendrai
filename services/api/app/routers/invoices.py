import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.domain.cases import CaseStatus
from app.models import AgentRun, Case, Document, InvoiceRecord, OutboxEvent, Vendor
from app.schemas import (
    ActionAccepted,
    CaseResponse,
    InvoiceDraftRequest,
    InvoiceSubmissionRequest,
)
from app.services.events import append_audit, append_case_event, enqueue_event

router = APIRouter(prefix="/invoices", tags=["invoices"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)]


async def _validate_vendor(db: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID | None) -> None:
    if vendor_id is None:
        return
    vendor = await db.scalar(
        select(Vendor).where(Vendor.vendor_id == vendor_id, Vendor.tenant_id == tenant_id)
    )
    if not vendor:
        raise HTTPException(404, detail={"code": "VENDOR_NOT_FOUND"})


@router.post(":draft", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice_draft(
    body: InvoiceDraftRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
):
    principal.require_any("requester", "analyst", "admin")
    scoped_key = f"invoice.draft:{principal.user_id}:{idempotency_key}"
    existing = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == principal.tenant_id,
            OutboxEvent.idempotency_key == scoped_key,
        )
    )
    if existing:
        case = await db.scalar(
            select(Case).where(
                Case.case_id == existing.aggregate_id,
                Case.tenant_id == principal.tenant_id,
            )
        )
        if case:
            return case

    await _validate_vendor(db, principal.tenant_id, body.vendor_id)
    case_id = uuid.uuid4()
    case = Case(
        case_id=case_id,
        tenant_id=principal.tenant_id,
        case_number=f"INV-{datetime.now(UTC):%Y%m%d}-{str(case_id)[:8].upper()}",
        case_type="INVOICE_EXCEPTION",
        status=CaseStatus.DRAFT,
        title=f"Invoice Exception: {body.invoice_number}",
        priority=body.priority,
        requester_user_id=principal.user_id,
        vendor_id=body.vendor_id,
    )
    db.add(case)
    await db.flush()
    db.add(
        InvoiceRecord(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            vendor_id=body.vendor_id,
            invoice_number=body.invoice_number,
            po_number=body.po_number,
            total_amount=0,
            tax_amount=0,
            currency=body.currency,
            status="DRAFT",
        )
    )
    await append_case_event(
        db,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        event_type="CASE_CREATED",
        actor_type="USER",
        actor_id=str(principal.user_id),
        payload={"case_type": "INVOICE_EXCEPTION", "status": CaseStatus.DRAFT},
    )
    enqueue_event(
        db,
        tenant_id=principal.tenant_id,
        aggregate_type="case",
        aggregate_id=case_id,
        aggregate_version=case.current_version,
        event_type="case.created.v1",
        idempotency_key=scoped_key,
        payload={"case_id": str(case_id), "case_type": "INVOICE_EXCEPTION"},
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="INVOICE_DRAFT_CREATED",
        resource_type="CASE",
        resource_id=str(case_id),
        metadata={"invoice_number": body.invoice_number, "po_number": body.po_number},
    )
    return case


@router.post("", response_model=ActionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_invoice_compatibility(
    body: InvoiceSubmissionRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
):
    """Compatibility endpoint; new clients should create a draft and submit the case."""
    principal.require_any("requester", "analyst", "admin")
    scoped_key = f"invoice.submit:{principal.user_id}:{idempotency_key}"
    existing = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == principal.tenant_id,
            OutboxEvent.idempotency_key == scoped_key,
        )
    )
    if existing:
        case = await db.scalar(
            select(Case).where(
                Case.case_id == existing.aggregate_id,
                Case.tenant_id == principal.tenant_id,
            )
        )
        run = await db.scalar(
            select(AgentRun)
            .where(AgentRun.case_id == existing.aggregate_id)
            .order_by(AgentRun.created_at.desc())
        )
        if case:
            return ActionAccepted(
                case_id=case.case_id,
                run_id=run.run_id if run else None,
                status=case.status,
                event_url=f"/api/v1/runs/{run.run_id}/events" if run else None,
            )

    await _validate_vendor(db, principal.tenant_id, body.vendor_id)
    document_ids = set(body.document_ids)
    if body.document_id:
        document_ids.add(body.document_id)
    documents = (
        await db.execute(
            select(Document).where(
                Document.tenant_id == principal.tenant_id,
                Document.document_id.in_(document_ids),
            )
        )
    ).scalars().all()
    if len(documents) != len(document_ids):
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    source_cases = (
        await db.execute(
            select(Case).where(
                Case.tenant_id == principal.tenant_id,
                Case.case_id.in_(
                    {document.case_id for document in documents}
                ),
            )
        )
    ).scalars().all()
    if (
        len(source_cases) != len({document.case_id for document in documents})
        or "admin" not in principal.roles
        and any(
            source_case.requester_user_id != principal.user_id
            or source_case.status != CaseStatus.DRAFT
            for source_case in source_cases
        )
    ):
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    if any(document.processing_status not in {"QUARANTINED", "QUEUED", "PROCESSING", "READY"} for document in documents):
        raise HTTPException(409, detail={"code": "DOCUMENT_NOT_UPLOAD_COMPLETE"})

    case_id = uuid.uuid4()
    run_id = uuid.uuid4()
    case = Case(
        tenant_id=principal.tenant_id,
        case_id=case_id,
        case_number=f"INV-{datetime.now(UTC):%Y%m%d}-{str(case_id)[:8].upper()}",
        case_type="INVOICE_EXCEPTION",
        status=CaseStatus.SUBMITTED,
        title=f"Invoice Exception: {body.invoice_number}",
        priority=body.priority,
        requester_user_id=principal.user_id,
        vendor_id=body.vendor_id,
        submitted_at=datetime.now(UTC),
    )
    db.add(case)
    await db.flush()
    for document in documents:
        document.case_id = case_id
    db.add(
        InvoiceRecord(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            vendor_id=body.vendor_id,
            invoice_number=body.invoice_number,
            po_number=body.po_number,
            total_amount=0,
            tax_amount=0,
            currency="LKR",
            status="RECEIVED",
        )
    )
    run = AgentRun(
        run_id=run_id,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        thread_id=f"{principal.tenant_id}:invoice:{case_id}:{run_id}",
        graph_name="invoice_exception",
        status="QUEUED",
        current_node="document_processing",
        state_json={
            "case_id": str(case_id),
            "invoice_number": body.invoice_number,
            "po_number": body.po_number,
        },
    )
    db.add(run)
    await append_case_event(
        db,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        event_type="CASE_SUBMITTED",
        actor_type="USER",
        actor_id=str(principal.user_id),
        payload={"run_id": str(run_id), "case_type": "INVOICE_EXCEPTION"},
    )
    enqueue_event(
        db,
        tenant_id=principal.tenant_id,
        aggregate_type="case",
        aggregate_id=case_id,
        aggregate_version=case.current_version,
        event_type="invoice.submitted.v1",
        idempotency_key=scoped_key,
        payload={"case_id": str(case_id), "run_id": str(run_id)},
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="INVOICE_SUBMITTED",
        resource_type="CASE",
        resource_id=str(case_id),
        metadata={"document_count": len(documents)},
    )
    return ActionAccepted(
        case_id=case_id,
        run_id=run_id,
        status=case.status,
        event_url=f"/api/v1/runs/{run_id}/events",
    )
