import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.cases import CaseStatus
from app.models import (
    AgentRun, ApprovalTask, Case, ClarificationTask, Document,
    ExtractedField, InboxReceipt,
)
from app.services.events import append_case_event, enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant

# Mock implementation of LangGraph dispatch for invoice analysis
# In a full implementation, this would import build_invoice_graph from agent.app.invoice_graph


async def handle_invoice_submitted(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    run_id = uuid.UUID(envelope["payload"]["run_id"])
    
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "invoice-worker", "event_id": event_id}):
                return
                
            documents = (await session.execute(select(Document).where(Document.case_id == case_id))).scalars().all()
            if not documents or all(document.processing_status == "READY" for document in documents):
                case = await session.get(Case, case_id, with_for_update=True)
                case.status = CaseStatus.INVOICE_MATCHING
                case.current_version += 1
                
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="case", aggregate_id=case_id,
                    aggregate_version=case.current_version, event_type="invoice.analysis.requested.v1",
                    idempotency_key=f"invoice.analysis:{case_id}:v{case.current_version}",
                    payload={"case_id": str(case_id), "run_id": str(run_id)},
                )
            else:
                await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="RUN_WAITING_FOR_DOCUMENTS", actor_type="SYSTEM", actor_id="invoice-worker", payload={"run_id": str(run_id)})
            
            session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))


async def run_invoice_analysis(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    run_id = uuid.UUID(envelope["payload"]["run_id"])
    
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "invoice-worker", "event_id": event_id}):
                return
                
            case = await session.get(Case, case_id, with_for_update=True)
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if not case or case.tenant_id != tenant_id or not run:
                raise RuntimeError("CASE_OR_RUN_NOT_FOUND")
                
            run.status = "RUNNING"
            run.current_node = "invoice_specialist_analysis"
            run.started_at = run.started_at or datetime.now(UTC)
            await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="INVOICE_ANALYSIS_STARTED", actor_type="SYSTEM", actor_id="invoice-worker", payload={"run_id": str(run_id)})
            await session.flush()

            # ---------------------------------------------------------
            # Mock graph execution
            # ---------------------------------------------------------
            
            # Simulated extracted data
            extracted_invoice = {
                "invoice_number": "148899",
                "vendor_name": "Keells",
                "total_amount": 480.00,
                "tax_amount": 0.00,
                "currency": "LKR",
                "line_items": [
                    {"line_number": 1, "description": "119172: CHELLO DRIN YOGHRT BASILSEED VANIL 180ML", "quantity": 1.0, "unit_price": 170.00, "amount": 170.00, "tax_rate": 0.0, "po_line_ref": "1"},
                    {"line_number": 2, "description": "3292: SCAN JUMBO PEANUT 70G", "quantity": 1.0, "unit_price": 310.00, "amount": 310.00, "tax_rate": 0.0, "po_line_ref": "2"}
                ]
            }
            
            match_result = {
                "match_status": "PARTIAL_MATCH",
                "line_matches": [
                    {"invoice_line": extracted_invoice["line_items"][0], "price_variance": 0.0, "quantity_variance": 0.0, "match_status": "MATCHED"},
                    {"invoice_line": extracted_invoice["line_items"][1], "price_variance": 10.0, "quantity_variance": 0.0, "match_status": "PARTIAL_MATCH"}
                ],
                "overall_variance_amount": 10.0,
                "overall_variance_pct": 2.1,
                "unmatched_invoice_lines": [],
                "unmatched_po_lines": []
            }
            
            exceptions = [
                {"exception_type": "PRICE_VARIANCE", "severity": "LOW", "confidence": 0.95, "mismatch_details": {"message": "Price variance found on SCAN JUMBO PEANUT (Expected 300.00, Actual 310.00)"}, "affected_lines": [2]}
            ]
            
            tolerance_result = {
                "within_tolerance": True,
                "threshold_amount": 50.0,
                "threshold_pct": 5.0,
                "actual_variance": 10.0,
                "policy_ref": "POLICY-INV-001",
                "exception_type": "PRICE_VARIANCE"
            }
            
            risk_result = {
                "disposition": "CLEAR",
                "fraud_signals": [],
                "duplicate_invoice_found": False
            }
            
            evidence_packet = {
                "case_id": str(case_id),
                "run_id": str(run_id),
                "recommendation": "RESOLVE_EXCEPTION",
                "reason_codes": ["WITHIN_TOLERANCE"],
                "extracted_invoice": extracted_invoice,
                "match_result": match_result,
                "exception": exceptions,
                "tolerance": tolerance_result,
                "risk": risk_result,
                "policy_clauses": [],
                "evidence": [],
                "unresolved_items": []
            }
            
            # In Phase 1 we require human approval for everything (No auto-resolve)
            case.status = CaseStatus.APPROVAL_PENDING
            case.current_version += 1
            
            run.status = "COMPLETED"
            run.current_node = "approval_interrupt"
            run.completed_at = datetime.now(UTC)
            
            # Create Approval Task
            session.add(ApprovalTask(
                tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                task_type="INVOICE_EXCEPTION_RESOLUTION", status="PENDING",
                assigned_role="finance_approver", proposed_action={"action": "RESOLVE_EXCEPTION"},
                evidence_packet=evidence_packet, evidence_hash="mock-hash", case_version=case.current_version
            ))
            
            await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="APPROVAL_REQUIRED", actor_type="SYSTEM", actor_id="invoice-worker", payload={"reason": "Manual review required for exceptions"})
            
            session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))


async def dispatch(envelope: dict) -> None:
    event_type = envelope["event_type"]
    if event_type == "invoice.submitted.v1":
        await handle_invoice_submitted(envelope)
    elif event_type == "invoice.analysis.requested.v1":
        await run_invoice_analysis(envelope)
    elif event_type == "invoice.resolution.approved.v1":
        # Handled by erp sync worker, but invoice worker can update case status if needed
        pass


if __name__ == "__main__":
    asyncio.run(consume("invoice-worker", [
        "invoice.submitted.v1",
        "invoice.analysis.requested.v1",
        "invoice.resolution.approved.v1",
    ], dispatch))
