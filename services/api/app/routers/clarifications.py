import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.config import settings
from app.database import get_db
from app.domain.cases import CaseStatus, assert_transition
from app.domain.security import blind_index, encrypt_sensitive_value, normalize_vendor_name
from app.models import Case, ClarificationTask, Document, ExtractedField
from app.schemas import ClarificationResponseRequest
from app.services.events import append_audit, append_case_event, enqueue_event


router = APIRouter(prefix="/clarification-tasks", tags=["clarifications"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/{task_id}/responses")
async def respond(
    task_id: uuid.UUID, body: ClarificationResponseRequest, db: Db, principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
    if_match: Annotated[int, Header(alias="If-Match", ge=1)],
):
    principal.require_any("requester", "analyst", "admin")
    task = await db.scalar(select(ClarificationTask).where(
        ClarificationTask.clarification_task_id == task_id, ClarificationTask.tenant_id == principal.tenant_id,
    ).with_for_update())
    if not task:
        raise HTTPException(404, detail={"code": "CLARIFICATION_TASK_NOT_FOUND"})
    if task.status != "OPEN":
        raise HTTPException(409, detail={"code": "CLARIFICATION_ALREADY_ANSWERED"})
    case = await db.scalar(select(Case).where(Case.case_id == task.case_id).with_for_update())
    if principal.roles == {"requester"} and case.requester_user_id != principal.user_id:
        raise HTTPException(404, detail={"code": "CLARIFICATION_TASK_NOT_FOUND"})
    if if_match != body.expected_version or case.current_version != body.expected_version:
        raise HTTPException(409, detail={"code": "STALE_CASE_VERSION", "current_version": case.current_version})
    assert_transition(case.status, CaseStatus.SPECIALIST_ANALYSIS)
    task.status = "ANSWERED"
    first_document = await db.scalar(select(Document).where(Document.case_id == case.case_id).order_by(Document.created_at))
    if not first_document:
        raise HTTPException(409, detail={"code": "DOCUMENT_REQUIRED"})
    sensitive_fields = {"tax_id", "bank_account", "swift_code", "address", "email", "phone"}
    safe_response: dict[str, str] = {}
    for field_name, raw_answer in body.answers.items():
        answer = " ".join(raw_answer.split())
        if not answer:
            continue
        field = await db.scalar(
            select(ExtractedField).join(Document).where(Document.case_id == case.case_id, ExtractedField.field_name == field_name)
        )
        if not field:
            field = ExtractedField(
                tenant_id=principal.tenant_id, document_id=first_document.document_id,
                field_name=field_name, extractor_type="human-clarification", extractor_version="1.0.0",
                source_page=1, source_bbox={},
            )
            db.add(field)
        if field_name in sensitive_fields:
            field.field_value_masked = f"<{field_name.upper()}_CONFIRMED>"
            field.field_value_ciphertext = encrypt_sensitive_value(answer, settings.DATA_ENCRYPTION_SECRET)
            field.normalized_value = blind_index(answer, settings.BLIND_INDEX_SECRET).hex()
            safe_response[field_name] = "<SENSITIVE_VALUE_CONFIRMED>"
        else:
            field.field_value_masked = answer
            field.normalized_value = normalize_vendor_name(answer) if field_name == "legal_name" else answer.upper()
            safe_response[field_name] = answer
        field.confidence = 1.0
        field.human_verified = True
    task.response = safe_response
    task.responded_by = principal.user_id
    task.responded_at = datetime.now(UTC)
    case.status = CaseStatus.SPECIALIST_ANALYSIS
    case.current_version += 1
    await append_case_event(db, tenant_id=principal.tenant_id, case_id=case.case_id, event_type="CLARIFICATION_ANSWERED", actor_type="USER", actor_id=str(principal.user_id), payload={"task_id": str(task_id)})
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="case", aggregate_id=case.case_id,
        aggregate_version=case.current_version, event_type="agent.analysis.requested.v1",
        idempotency_key=f"clarification.response:{task_id}:{idempotency_key}",
        payload={"case_id": str(case.case_id), "run_id": str(task.run_id)},
    )
    await append_audit(db, tenant_id=principal.tenant_id, case_id=case.case_id, actor_type="USER", actor_id=str(principal.user_id), action="CLARIFICATION_ANSWERED", resource_type="CLARIFICATION_TASK", resource_id=str(task_id), metadata={"answer_keys": sorted(body.answers)})
    return {"task_id": task_id, "status": task.status, "case_status": case.status}
