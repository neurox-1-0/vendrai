import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from app.config import settings
from app.domain.cases import CaseStatus
from app.domain.security import normalize_vendor_name
from app.models import (
    AgentRun,
    ApprovalDecision,
    ApprovalTask,
    Case,
    ErpOperation,
    InboxReceipt,
    InvoiceHistoryRecord,
    InvoiceRecord,
    Vendor,
)
from app.policy_gateway import authorize_erp_write
from app.services.events import append_audit, append_case_event, enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from sqlalchemy import select

CONTROL_REVIEW_TASKS = {
    "SANCTIONS_REVIEW",
    "BANK_CHANGE_REVIEW",
    "TAX_REVIEW",
    "PROCUREMENT_REVIEW",
    "DUPLICATE_REVIEW",
}


class ErpPolicyDenied(RuntimeError):
    pass


class ErpEvidenceIncomplete(RuntimeError):
    """Authoritative data needed for the write is absent.

    Substituting a placeholder here would write a fabricated identity into the
    vendor master, which then becomes reference data for future duplicate
    detection - the fabrication propagates, invisibly. Retrying will not
    conjure the missing field either, so this fails closed and non-retryably
    with a reason code the UI and audit trail can show.

    See plans/91-decisions.md ADR-003.
    """

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _vendor_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the vendor identity before anything is written anywhere.

    Runs before the ERP call, not after: a vendor created upstream and then
    rejected locally leaves the two systems disagreeing about what exists.
    """
    legal_name = (payload.get("legal_name") or "").strip()
    if not legal_name:
        raise ErpEvidenceIncomplete("VENDOR_LEGAL_NAME_UNAVAILABLE")
    return {
        "legal_name": legal_name,
        "normalized_legal_name": normalize_vendor_name(legal_name),
        "registered_country": payload.get("registered_country"),
        "email_domain": payload.get("email_domain"),
    }


@dataclass(frozen=True)
class PreparedOperation:
    event_id: uuid.UUID
    tenant_id: uuid.UUID
    case_id: uuid.UUID
    task_id: uuid.UUID
    operation_id: uuid.UUID
    run_id: uuid.UUID
    evidence_hash: str
    idempotency_key: str
    proposed_action: dict[str, Any]
    policy_input: dict[str, Any]


def _required_controls(case: Case, task: ApprovalTask) -> set[str]:
    packet = task.evidence_packet or {}
    reason_codes = set(packet.get("reason_codes", []))
    required: set[str] = set()
    if case.case_type == "VENDOR_ONBOARDING":
        if any(
            candidate.get("review_required")
            for candidate in packet.get("duplicate_candidates", [])
        ):
            required.add("DUPLICATE_REVIEW")
        if packet.get("risk", {}).get("disposition") == "POSSIBLE_MATCH":
            required.add("SANCTIONS_REVIEW")
        return required
    duplicate = bool(packet.get("risk", {}).get("duplicate_invoice_found"))
    bank_change = "UNVERIFIED_BANK_ACCOUNT_CHANGE" in reason_codes
    tax_review = "TAX_MISMATCH" in reason_codes
    if duplicate:
        required.add("DUPLICATE_REVIEW")
    if bank_change:
        required.add("BANK_CHANGE_REVIEW")
    if tax_review:
        required.add("TAX_REVIEW")
    if packet.get("exception") and not (duplicate or bank_change or tax_review):
        required.add("PROCUREMENT_REVIEW")
    return required


async def _erp_policy_input(
    session,
    *,
    case: Case,
    task: ApprovalTask,
    evidence_hash: str,
) -> dict[str, Any]:
    approval = await session.scalar(
        select(ApprovalDecision).where(
            ApprovalDecision.approval_task_id == task.approval_task_id
        )
    )
    run = await session.get(AgentRun, task.run_id)
    approved_control_types = set(
        (
            await session.execute(
                select(ApprovalTask.task_type).where(
                    ApprovalTask.run_id == task.run_id,
                    ApprovalTask.task_type.in_(CONTROL_REVIEW_TASKS),
                    ApprovalTask.status == "APPROVED",
                )
            )
        ).scalars()
    )
    required_controls = _required_controls(case, task)
    risk_disposition = (
        (task.evidence_packet or {}).get("risk", {}).get("disposition")
    )
    return {
        "tenant_id": str(case.tenant_id),
        "case_type": case.case_type,
        "case_status": case.status,
        "case_version": case.current_version,
        "requester_user_id": str(case.requester_user_id),
        "approval_status": task.status,
        "approval_case_version": task.case_version,
        "approval_evidence_hash": task.evidence_hash,
        "current_evidence_hash": evidence_hash,
        "approver_user_id": str(approval.decided_by) if approval else "",
        "deterministic_verified": bool(
            run
            and run.state_json.get("verification_result", {}).get("status")
            == "SUCCESS"
        ),
        "required_controls_resolved": required_controls.issubset(
            approved_control_types
        ),
        "sanctions_cleared": (
            risk_disposition == "CLEAR"
            or "SANCTIONS_REVIEW" in approved_control_types
        ),
    }


async def _prepare_operation(
    envelope: dict,
    *,
    idempotency_prefix: str,
) -> PreparedOperation | None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    task_id = uuid.UUID(envelope["payload"]["approval_task_id"])
    evidence_hash = str(envelope["payload"]["evidence_hash"])
    idempotency_key = f"{idempotency_prefix}:{case_id}:{evidence_hash}"
    async with WorkerSession() as session, session.begin():
        await set_worker_tenant(session, str(tenant_id))
        if await session.get(
            InboxReceipt,
            {"consumer_name": "erp-worker", "event_id": event_id},
        ):
            return None
        case = await session.get(Case, case_id, with_for_update=True)
        task = await session.get(ApprovalTask, task_id)
        if not case or case.tenant_id != tenant_id or not task:
            raise RuntimeError("ERP_CONTEXT_NOT_FOUND")
        if (
            task.status != "APPROVED"
            or task.evidence_hash != evidence_hash
            or case.status != CaseStatus.ERP_SYNC_PENDING
        ):
            raise RuntimeError("ERP_APPROVAL_GATE_REJECTED")
        existing = await session.scalar(
            select(ErpOperation)
            .where(
                ErpOperation.tenant_id == tenant_id,
                ErpOperation.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if existing and existing.status == "SUCCEEDED":
            session.add(
                InboxReceipt(
                    consumer_name="erp-worker",
                    event_id=event_id,
                    tenant_id=tenant_id,
                )
            )
            return None
        operation = existing or ErpOperation(
            tenant_id=tenant_id,
            case_id=case_id,
            approval_task_id=task_id,
            idempotency_key=idempotency_key,
            request_payload=task.proposed_action,
        )
        if not existing:
            session.add(operation)
        operation.status = "RUNNING"
        operation.attempts += 1
        await session.flush()
        return PreparedOperation(
            event_id=event_id,
            tenant_id=tenant_id,
            case_id=case_id,
            task_id=task_id,
            operation_id=operation.erp_operation_id,
            run_id=task.run_id,
            evidence_hash=evidence_hash,
            idempotency_key=idempotency_key,
            proposed_action=task.proposed_action,
            policy_input=await _erp_policy_input(
                session,
                case=case,
                task=task,
                evidence_hash=evidence_hash,
            ),
        )


async def _authorize(prepared: PreparedOperation) -> None:
    decision = await authorize_erp_write(prepared.policy_input)
    if not decision.allow:
        reasons = ",".join(decision.deny_reasons) or "POLICY_DENIED"
        raise ErpPolicyDenied(f"OPA_POLICY_DENIED:{reasons}")


# Failures that retrying cannot fix. A missing legal name will still be
# missing on the next attempt, and a denied policy will still deny.
NON_RETRYABLE_FAILURES = (ErpPolicyDenied, ErpEvidenceIncomplete)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ErpEvidenceIncomplete):
        return exc.reason_code
    if isinstance(exc, ErpPolicyDenied):
        return "OPA_POLICY_DENIED"
    message = str(exc)
    if message.startswith("OPA_"):
        return message[:80]
    if isinstance(exc, httpx.TimeoutException):
        return "ERP_PROVIDER_TIMEOUT"
    if isinstance(exc, httpx.HTTPError):
        return "ERP_PROVIDER_UNAVAILABLE"
    return type(exc).__name__[:80]


async def _record_failure(
    prepared: PreparedOperation,
    exc: Exception,
) -> None:
    blocked = isinstance(exc, NON_RETRYABLE_FAILURES)
    async with WorkerSession() as session, session.begin():
        await set_worker_tenant(session, str(prepared.tenant_id))
        if await session.get(
            InboxReceipt,
            {
                "consumer_name": "erp-worker",
                "event_id": prepared.event_id,
            },
        ):
            return
        case = await session.get(
            Case,
            prepared.case_id,
            with_for_update=True,
        )
        operation = await session.get(
            ErpOperation,
            prepared.operation_id,
            with_for_update=True,
        )
        if not case or not operation:
            raise RuntimeError("ERP_FAILURE_CONTEXT_NOT_FOUND")
        if operation.status == "SUCCEEDED":
            session.add(
                InboxReceipt(
                    consumer_name="erp-worker",
                    event_id=prepared.event_id,
                    tenant_id=prepared.tenant_id,
                )
            )
            return
        operation.status = "BLOCKED" if blocked else "FAILED"
        operation.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        case.status = (
            CaseStatus.VERIFICATION_FAILED
            if blocked
            else CaseStatus.ERP_SYNC_FAILED
        )
        case.current_version += 1
        await append_case_event(
            session,
            tenant_id=prepared.tenant_id,
            case_id=prepared.case_id,
            event_type=(
                "ERP_AUTHORIZATION_BLOCKED"
                if isinstance(exc, ErpPolicyDenied)
                else "ERP_EVIDENCE_INCOMPLETE"
                if isinstance(exc, ErpEvidenceIncomplete)
                else "ERP_SYNC_FAILED"
            ),
            actor_type="SYSTEM",
            actor_id="erp-worker",
            payload={
                "retryable": not blocked,
                "error_code": _error_code(exc),
            },
        )
        session.add(
            InboxReceipt(
                consumer_name="erp-worker",
                event_id=prepared.event_id,
                tenant_id=prepared.tenant_id,
            )
        )


async def sync_erp(envelope: dict) -> None:
    prepared = await _prepare_operation(
        envelope,
        idempotency_prefix="erp.vendor.create",
    )
    if not prepared:
        return
    try:
        await _authorize(prepared)
        _vendor_identity(prepared.proposed_action.get("payload", {}))
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.MOCK_ERP_URL}/v1/vendors",
                json={
                    **prepared.proposed_action.get("payload", {}),
                    "approval_task_id": str(prepared.task_id),
                    "evidence_hash": prepared.evidence_hash,
                },
                headers={"Idempotency-Key": prepared.idempotency_key},
            )
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        await _record_failure(prepared, exc)
        return

    async with WorkerSession() as session, session.begin():
        await set_worker_tenant(session, str(prepared.tenant_id))
        if await session.get(
            InboxReceipt,
            {
                "consumer_name": "erp-worker",
                "event_id": prepared.event_id,
            },
        ):
            return
        case = await session.get(
            Case,
            prepared.case_id,
            with_for_update=True,
        )
        operation = await session.get(
            ErpOperation,
            prepared.operation_id,
            with_for_update=True,
        )
        if not case or not operation:
            raise RuntimeError("ERP_FINALIZE_CONTEXT_NOT_FOUND")
        if operation.status == "SUCCEEDED":
            session.add(
                InboxReceipt(
                    consumer_name="erp-worker",
                    event_id=prepared.event_id,
                    tenant_id=prepared.tenant_id,
                )
            )
            return
        operation.status = "SUCCEEDED"
        operation.response_payload = result
        operation.provider_reference = result["erp_vendor_id"]
        identity = _vendor_identity(prepared.proposed_action.get("payload", {}))
        vendor = Vendor(
            tenant_id=prepared.tenant_id,
            legal_name=identity["legal_name"],
            normalized_legal_name=identity["normalized_legal_name"],
            registered_country=identity["registered_country"],
            email_domain=identity["email_domain"],
            status="ACTIVE",
            erp_vendor_id=result["erp_vendor_id"],
        )
        session.add(vendor)
        await session.flush()
        case.vendor_id = vendor.vendor_id
        await append_case_event(
            session,
            tenant_id=prepared.tenant_id,
            case_id=prepared.case_id,
            event_type="ERP_PROVIDER_CONFIRMED",
            actor_type="SYSTEM",
            actor_id="erp-worker",
            payload={"erp_vendor_id": result["erp_vendor_id"]},
        )
        await append_audit(
            session,
            tenant_id=prepared.tenant_id,
            case_id=prepared.case_id,
            actor_type="SYSTEM",
            actor_id="erp-worker",
            action="ERP_VENDOR_CONFIRMED",
            resource_type="VENDOR",
            resource_id=str(vendor.vendor_id),
            metadata={
                "erp_vendor_id": result["erp_vendor_id"],
                "approval_task_id": str(prepared.task_id),
                "evidence_hash": prepared.evidence_hash,
            },
        )
        enqueue_event(
            session,
            tenant_id=prepared.tenant_id,
            aggregate_type="agent_run",
            aggregate_id=prepared.run_id,
            aggregate_version=case.current_version,
            event_type="agent.erp.confirmed.v1",
            idempotency_key=f"agent.erp.confirmed:{operation.erp_operation_id}",
            payload={
                "case_id": str(prepared.case_id),
                "run_id": str(prepared.run_id),
                "operation_id": str(operation.erp_operation_id),
                "status": "SUCCEEDED",
                "provider_reference": result["erp_vendor_id"],
            },
        )
        session.add(
            InboxReceipt(
                consumer_name="erp-worker",
                event_id=prepared.event_id,
                tenant_id=prepared.tenant_id,
            )
        )


async def sync_invoice_resolution(envelope: dict) -> None:
    prepared = await _prepare_operation(
        envelope,
        idempotency_prefix="erp.invoice.resolve",
    )
    if not prepared:
        return
    try:
        await _authorize(prepared)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                (
                    f"{settings.MOCK_ERP_URL}/v1/invoice-exceptions/"
                    f"{prepared.case_id}/resolve"
                ),
                json={
                    **prepared.proposed_action.get("payload", {}),
                    "approval_task_id": str(prepared.task_id),
                    "evidence_hash": prepared.evidence_hash,
                },
                headers={"Idempotency-Key": prepared.idempotency_key},
            )
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        await _record_failure(prepared, exc)
        return

    async with WorkerSession() as session, session.begin():
        await set_worker_tenant(session, str(prepared.tenant_id))
        if await session.get(
            InboxReceipt,
            {
                "consumer_name": "erp-worker",
                "event_id": prepared.event_id,
            },
        ):
            return
        case = await session.get(
            Case,
            prepared.case_id,
            with_for_update=True,
        )
        operation = await session.get(
            ErpOperation,
            prepared.operation_id,
            with_for_update=True,
        )
        if not case or not operation:
            raise RuntimeError("ERP_FINALIZE_CONTEXT_NOT_FOUND")
        if operation.status == "SUCCEEDED":
            session.add(
                InboxReceipt(
                    consumer_name="erp-worker",
                    event_id=prepared.event_id,
                    tenant_id=prepared.tenant_id,
                )
            )
            return
        operation.status = "SUCCEEDED"
        operation.response_payload = result
        operation.provider_reference = result.get("resolution_id")
        invoice = await session.scalar(
            select(InvoiceRecord).where(
                InvoiceRecord.tenant_id == prepared.tenant_id,
                InvoiceRecord.case_id == prepared.case_id,
            )
        )
        if invoice:
            invoice.status = "RESOLVED"
            if invoice.vendor_id:
                history = await session.scalar(
                    select(InvoiceHistoryRecord).where(
                        InvoiceHistoryRecord.tenant_id
                        == prepared.tenant_id,
                        InvoiceHistoryRecord.vendor_id
                        == str(invoice.vendor_id),
                        InvoiceHistoryRecord.invoice_number
                        == invoice.invoice_number,
                    )
                )
                if not history:
                    session.add(
                        InvoiceHistoryRecord(
                            tenant_id=prepared.tenant_id,
                            vendor_id=str(invoice.vendor_id),
                            invoice_number=invoice.invoice_number,
                            gross_amount=invoice.total_amount,
                            currency=invoice.currency,
                            po_number=invoice.po_number,
                            status="RESOLVED",
                        )
                    )
        await append_case_event(
            session,
            tenant_id=prepared.tenant_id,
            case_id=prepared.case_id,
            event_type="ERP_PROVIDER_CONFIRMED",
            actor_type="SYSTEM",
            actor_id="erp-worker",
            payload={"resolution_id": result.get("resolution_id")},
        )
        await append_audit(
            session,
            tenant_id=prepared.tenant_id,
            case_id=prepared.case_id,
            actor_type="SYSTEM",
            actor_id="erp-worker",
            action="ERP_INVOICE_CONFIRMED",
            resource_type="CASE",
            resource_id=str(prepared.case_id),
            metadata={
                "approval_task_id": str(prepared.task_id),
                "evidence_hash": prepared.evidence_hash,
            },
        )
        enqueue_event(
            session,
            tenant_id=prepared.tenant_id,
            aggregate_type="agent_run",
            aggregate_id=prepared.run_id,
            aggregate_version=case.current_version,
            event_type="agent.erp.confirmed.v1",
            idempotency_key=f"agent.erp.confirmed:{operation.erp_operation_id}",
            payload={
                "case_id": str(prepared.case_id),
                "run_id": str(prepared.run_id),
                "operation_id": str(operation.erp_operation_id),
                "status": "SUCCEEDED",
                "provider_reference": result.get("resolution_id"),
            },
        )
        session.add(
            InboxReceipt(
                consumer_name="erp-worker",
                event_id=prepared.event_id,
                tenant_id=prepared.tenant_id,
            )
        )


async def dispatch(envelope: dict) -> None:
    event_type = envelope["event_type"]
    if event_type == "erp.sync.requested.v1":
        await sync_erp(envelope)
    elif event_type == "invoice.resolution.approved.v1":
        await sync_invoice_resolution(envelope)


if __name__ == "__main__":
    asyncio.run(
        consume(
            "erp-worker",
            ["erp.sync.requested.v1", "invoice.resolution.approved.v1"],
            dispatch,
        )
    )
