import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.config import settings
from app.database import get_db
from app.models import Case, Document
from app.schemas import DocumentResponse, UploadInitiateRequest, UploadInitiateResponse
from app.services.events import append_audit, append_case_event, enqueue_event
from app.services.storage import issue_upload_token, sanitize_filename, stream_to_quarantine, validate_upload_request, verify_upload_token


router = APIRouter(tags=["documents"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/cases/{case_id}/documents:initiate", response_model=UploadInitiateResponse, status_code=201)
async def initiate_upload(
    case_id: uuid.UUID,
    body: UploadInitiateRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
):
    principal.require_any("requester", "analyst", "admin")
    case = await db.scalar(select(Case).where(Case.case_id == case_id, Case.tenant_id == principal.tenant_id))
    if not case:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    if case.status != "DRAFT":
        raise HTTPException(409, detail={"code": "UPLOAD_NOT_ALLOWED", "status": case.status})
    validate_upload_request(body.content_type, body.size_bytes)
    sanitized = sanitize_filename(body.filename)
    document_id = uuid.uuid4()
    token, token_hash, expires = issue_upload_token(str(document_id))
    document = Document(
        document_id=document_id, tenant_id=principal.tenant_id, case_id=case_id,
        document_type=body.document_type, original_filename=body.filename, sanitized_filename=sanitized,
        mime_type=body.content_type, size_bytes=body.size_bytes,
        storage_key=f"quarantine/{principal.tenant_id}/{document_id}", upload_token_hash=token_hash,
        uploaded_by=principal.user_id, processing_status="INITIATED", malware_status="PENDING",
    )
    db.add(document)
    await append_case_event(
        db, tenant_id=principal.tenant_id, case_id=case_id, event_type="DOCUMENT_UPLOAD_INITIATED",
        actor_type="USER", actor_id=str(principal.user_id), payload={"document_id": str(document_id), "filename": sanitized},
    )
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=case_id, actor_type="USER", actor_id=str(principal.user_id),
        action="DOCUMENT_UPLOAD_INITIATED", resource_type="DOCUMENT", resource_id=str(document_id), metadata={"content_type": body.content_type},
    )
    return UploadInitiateResponse(
        document_id=document_id,
        upload_url=f"{settings.API_PREFIX}/documents/{document_id}/content?token={token}",
        expires_at=expires,
        required_headers={"Content-Type": body.content_type},
    )


@router.put("/documents/{document_id}/content", response_model=DocumentResponse)
async def upload_content(document_id: uuid.UUID, request: Request, db: Db, principal: CurrentPrincipal, token: Annotated[str, Query(min_length=20)]):
    document = await db.scalar(select(Document).where(
        Document.document_id == document_id, Document.tenant_id == principal.tenant_id,
    ).with_for_update())
    if not document:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    verify_upload_token(token, document.upload_token_hash, str(document_id))
    if document.processing_status != "INITIATED":
        if document.sha256:
            return document
        raise HTTPException(409, detail={"code": "UPLOAD_ALREADY_CONSUMED"})
    content_type = request.headers.get("content-type", "")
    if content_type != document.mime_type:
        raise HTTPException(415, detail={"code": "CONTENT_TYPE_MISMATCH"})
    stored = await stream_to_quarantine(request, str(document.tenant_id), str(document_id), content_type)
    if stored.size_bytes != document.size_bytes:
        raise HTTPException(422, detail={"code": "CONTENT_LENGTH_MISMATCH", "expected": document.size_bytes, "actual": stored.size_bytes})
    document.sha256 = stored.sha256
    document.processing_status = "QUARANTINED"
    document.upload_token_hash = "consumed:" + document.upload_token_hash[:54]
    return document


@router.post("/documents/{document_id}:complete", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(
    document_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
):
    principal.require_any("requester", "analyst", "admin")
    document = await db.scalar(
        select(Document).where(Document.document_id == document_id, Document.tenant_id == principal.tenant_id).with_for_update()
    )
    if not document:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    if document.processing_status == "QUEUED":
        return document
    if document.processing_status != "QUARANTINED" or not document.sha256:
        raise HTTPException(409, detail={"code": "UPLOAD_INCOMPLETE"})
    duplicate = await db.scalar(
        select(Document).where(
            Document.tenant_id == principal.tenant_id, Document.case_id == document.case_id,
            Document.sha256 == document.sha256, Document.document_id != document.document_id,
        )
    )
    if duplicate:
        raise HTTPException(409, detail={"code": "DUPLICATE_DOCUMENT", "document_id": str(duplicate.document_id)})
    document.processing_status = "QUEUED"
    await append_case_event(
        db, tenant_id=principal.tenant_id, case_id=document.case_id, event_type="DOCUMENT_PROCESSING_QUEUED",
        actor_type="USER", actor_id=str(principal.user_id), payload={"document_id": str(document_id)},
    )
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="document", aggregate_id=document_id,
        aggregate_version=1, event_type="document.processing.requested.v1",
        idempotency_key=f"document.complete:{document_id}:{idempotency_key}",
        payload={"document_id": str(document_id), "case_id": str(document.case_id)},
    )
    return document


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any("requester", "analyst", "approver", "auditor", "admin")
    document = await db.scalar(select(Document).where(Document.document_id == document_id, Document.tenant_id == principal.tenant_id))
    if not document:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    return document
