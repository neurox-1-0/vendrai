import uuid
from typing import Annotated
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.database import get_db, AsyncSession
from app.domain.cases import CaseStatus
from app.models import Case, Document, Tenant, AgentRun
from app.schemas import ActionAccepted, InvoiceSubmissionRequest
from app.auth import CurrentPrincipal
from app.services.events import append_case_event, enqueue_event

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("", response_model=ActionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_invoice(
    request: InvoiceSubmissionRequest,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    tenant_id = principal.tenant_id
    user_id = principal.user_id
    case_id = uuid.uuid4()
    run_id = uuid.uuid4()
    
    case = Case(
        tenant_id=tenant_id,
        case_id=case_id,
        case_number=f"INV-{datetime.now(UTC).strftime('%y%m%d')}-{str(case_id)[:4].upper()}",
        case_type="INVOICE_EXCEPTION",
        status=CaseStatus.SUBMITTED,
        title=f"Invoice Exception: {request.invoice_number}",
        priority=request.priority,
        requester_user_id=user_id,
        vendor_id=request.vendor_id,
    )
    session.add(case)
    await session.flush()
    
    run = AgentRun(
        run_id=run_id, tenant_id=tenant_id, case_id=case_id, 
        thread_id=f"case:{case_id}:v{case.current_version}",
        status="QUEUED", current_node="document_processing", 
        state_json={"case_id": str(case_id)},
    )
    session.add(run)
    await session.flush()
    
    await append_case_event(
        session, tenant_id=tenant_id, case_id=case_id, event_type="CASE_CREATED",
        actor_type="USER", actor_id=str(user_id),
        payload={"case_type": "INVOICE_EXCEPTION", "title": case.title, "invoice_number": request.invoice_number}
    )
    await session.flush()
    
    if request.document_id:
        document = await session.get(Document, request.document_id)
        if document and document.tenant_id == tenant_id:
            document.case_id = case_id
            await append_case_event(
                session, tenant_id=tenant_id, case_id=case_id, event_type="DOCUMENT_ATTACHED",
                actor_type="USER", actor_id=str(user_id), payload={"document_id": str(request.document_id)}
            )
            
    enqueue_event(
        session, tenant_id=tenant_id, aggregate_type="case", aggregate_id=case_id,
        aggregate_version=case.current_version, event_type="invoice.submitted.v1",
        idempotency_key=f"invoice.submit:{case_id}",
        payload={"case_id": str(case_id), "run_id": str(run_id), "invoice_number": request.invoice_number}
    )
    
    return ActionAccepted(case_id=case_id, run_id=run_id, status="ACCEPTED")
