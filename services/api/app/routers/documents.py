import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CASE_READ_ROLES, STAFF_ROLES, CurrentPrincipal
from app.config import settings
from app.database import get_db
from app.domain.security import (
    blind_index,
    canonical_hash,
    encrypt_sensitive_value,
    normalize_vendor_name,
)
from app.models import (
    Case,
    Document,
    DocumentPage,
    ExtractedField,
    IdempotencyRecord,
    OutboxEvent,
)
from app.schemas import (
    DocumentPageResponse,
    DocumentResponse,
    ExtractedFieldResponse,
    FieldCorrectionRequest,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from app.services.events import append_audit, append_case_event, enqueue_event
from app.services.storage import (
    inspect_quarantined_object,
    issue_upload_token,
    local_object_path,
    presigned_download_url,
    presigned_upload_url,
    quarantine_key,
    sanitize_filename,
    stream_to_quarantine,
    validate_upload_request,
    verify_upload_token,
)

router = APIRouter(tags=["documents"])
Db = Annotated[AsyncSession, Depends(get_db)]


async def _authorized_document(
    db: AsyncSession,
    principal,
    document_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> tuple[Document, Case]:
    statement = select(Document).where(
        Document.document_id == document_id,
        Document.tenant_id == principal.tenant_id,
    )
    if for_update:
        statement = statement.with_for_update()
    document = await db.scalar(statement)
    if not document:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    case = await db.scalar(
        select(Case).where(
            Case.case_id == document.case_id,
            Case.tenant_id == principal.tenant_id,
        )
    )
    if not case:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    elevated = principal.roles.intersection(STAFF_ROLES)
    if not elevated and case.requester_user_id != principal.user_id:
        raise HTTPException(404, detail={"code": "DOCUMENT_NOT_FOUND"})
    return document, case


@router.get(
    "/cases/{case_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_case_documents(
    case_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any(*CASE_READ_ROLES)
    case = await db.scalar(
        select(Case).where(
            Case.case_id == case_id,
            Case.tenant_id == principal.tenant_id,
        )
    )
    if (
        not case
        or principal.is_requester_only
        and case.requester_user_id != principal.user_id
    ):
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    return list(
        (
            await db.execute(
                select(Document)
                .where(
                    Document.case_id == case_id,
                    Document.tenant_id == principal.tenant_id,
                )
                .order_by(Document.created_at)
            )
        )
        .scalars()
        .all()
    )


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
    if (
        not case
        or principal.is_requester_only
        and case.requester_user_id != principal.user_id
    ):
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    if case.status != "DRAFT":
        raise HTTPException(409, detail={"code": "UPLOAD_NOT_ALLOWED", "status": case.status})
    validate_upload_request(body.content_type, body.size_bytes)
    sanitized = sanitize_filename(body.filename)
    scope = f"document.initiate:{principal.user_id}"
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_hash = canonical_hash(
        {"case_id": str(case_id), **body.model_dump(mode="json")}
    )
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == principal.tenant_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})
        existing_document = await db.scalar(
            select(Document).where(
                Document.document_id == existing.resource_id,
                Document.case_id == case_id,
                Document.tenant_id == principal.tenant_id,
            )
        )
        if existing_document:
            if settings.STORAGE_BACKEND == "s3":
                upload_url = presigned_upload_url(
                    existing_document.storage_key,
                    existing_document.mime_type,
                )
            else:
                raise HTTPException(409, detail={"code": "UPLOAD_URL_ALREADY_ISSUED"})
            return UploadInitiateResponse(
                document_id=existing_document.document_id,
                upload_url=upload_url,
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.UPLOAD_URL_TTL_SECONDS),
                required_headers={"Content-Type": existing_document.mime_type},
            )
    document_id = uuid.uuid4()
    token, token_hash, expires = issue_upload_token(str(document_id))
    object_key = quarantine_key(str(principal.tenant_id), str(document_id))
    document = Document(
        document_id=document_id, tenant_id=principal.tenant_id, case_id=case_id,
        document_type=body.document_type, original_filename=body.filename, sanitized_filename=sanitized,
        mime_type=body.content_type, size_bytes=body.size_bytes,
        storage_key=object_key, upload_token_hash=token_hash,
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
    db.add(
        IdempotencyRecord(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            resource_id=document_id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    upload_url = (
        presigned_upload_url(object_key, body.content_type)
        if settings.STORAGE_BACKEND == "s3"
        else f"{settings.API_PREFIX}/documents/{document_id}/content?token={token}"
    )
    return UploadInitiateResponse(
        document_id=document_id,
        upload_url=upload_url,
        expires_at=expires,
        required_headers={"Content-Type": body.content_type},
    )


@router.put("/documents/{document_id}/content", response_model=DocumentResponse)
async def upload_content(document_id: uuid.UUID, request: Request, db: Db, principal: CurrentPrincipal, token: Annotated[str, Query(min_length=20)]):
    if settings.STORAGE_BACKEND != "local":
        raise HTTPException(404, detail={"code": "DIRECT_UPLOAD_DISABLED"})
    document, _ = await _authorized_document(
        db,
        principal,
        document_id,
        for_update=True,
    )
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
    document, _ = await _authorized_document(
        db,
        principal,
        document_id,
        for_update=True,
    )
    if document.processing_status == "QUEUED":
        return document
    if settings.STORAGE_BACKEND == "s3":
        _, digest = await asyncio.to_thread(
            inspect_quarantined_object,
            document.storage_key,
            document.mime_type,
            document.size_bytes,
        )
        document.sha256 = digest
        document.processing_status = "QUARANTINED"
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
    principal.require_any(*CASE_READ_ROLES)
    document, _ = await _authorized_document(db, principal, document_id)
    return document


@router.get("/documents/{document_id}/pages", response_model=list[DocumentPageResponse])
async def list_document_pages(document_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any(*CASE_READ_ROLES)
    await _authorized_document(db, principal, document_id)
    return list(
        (
            await db.execute(
                select(DocumentPage)
                .where(
                    DocumentPage.document_id == document_id,
                    DocumentPage.tenant_id == principal.tenant_id,
                )
                .order_by(DocumentPage.page_number)
            )
        )
        .scalars()
        .all()
    )


@router.get(
    "/documents/{document_id}/fields",
    response_model=list[ExtractedFieldResponse],
)
async def list_document_fields(
    document_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any(*CASE_READ_ROLES)
    await _authorized_document(db, principal, document_id)
    return list(
        (
            await db.execute(
                select(ExtractedField)
                .where(
                    ExtractedField.document_id == document_id,
                    ExtractedField.tenant_id == principal.tenant_id,
                )
                .order_by(
                    ExtractedField.source_page,
                    ExtractedField.field_name,
                )
            )
        )
        .scalars()
        .all()
    )


@router.get("/documents/{document_id}/content", response_class=RedirectResponse)
async def get_document_content(document_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any(*CASE_READ_ROLES)
    document, _ = await _authorized_document(db, principal, document_id)
    if document.processing_status != "READY" or not document.storage_key.startswith("documents/"):
        raise HTTPException(409, detail={"code": "DOCUMENT_NOT_READY"})
    if settings.STORAGE_BACKEND == "s3":
        return RedirectResponse(
            presigned_download_url(document.storage_key, document.sanitized_filename),
            status_code=307,
            headers={"Cache-Control": "no-store"},
        )
    return FileResponse(
        local_object_path(document.storage_key),
        media_type=document.mime_type,
        filename=document.sanitized_filename,
        headers={"Cache-Control": "no-store"},
    )


@router.patch(
    "/documents/{document_id}/fields/{field_id}",
    response_model=ExtractedFieldResponse,
)
async def correct_document_field(
    document_id: uuid.UUID,
    field_id: uuid.UUID,
    body: FieldCorrectionRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
    if_match: Annotated[int, Header(alias="If-Match", ge=1)],
):
    principal.require_any("requester", "analyst", "admin")
    document, case = await _authorized_document(db, principal, document_id, for_update=True)
    if if_match != body.expected_version or case.current_version != body.expected_version:
        raise HTTPException(
            409,
            detail={"code": "STALE_CASE_VERSION", "current_version": case.current_version},
        )
    field = await db.scalar(
        select(ExtractedField)
        .where(
            ExtractedField.extracted_field_id == field_id,
            ExtractedField.document_id == document.document_id,
            ExtractedField.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if not field:
        raise HTTPException(404, detail={"code": "EXTRACTED_FIELD_NOT_FOUND"})
    scoped_key = f"document.field.correct:{field_id}:{idempotency_key}"
    if await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == principal.tenant_id,
            OutboxEvent.idempotency_key == scoped_key,
        )
    ):
        return field
    sensitive_fields = {"tax_id", "bank_account", "swift_code", "address", "email", "phone"}
    if field.field_name in sensitive_fields:
        field.field_value_masked = f"<{field.field_name.upper()}_HUMAN_VERIFIED>"
        field.field_value_ciphertext = encrypt_sensitive_value(
            body.value,
            settings.DATA_ENCRYPTION_SECRET,
        )
        field.normalized_value = blind_index(body.value, settings.BLIND_INDEX_SECRET).hex()
    else:
        field.field_value_masked = body.value
        field.normalized_value = (
            normalize_vendor_name(body.value)
            if field.field_name == "legal_name"
            else body.value.upper()
        )
    field.confidence = 1.0
    field.human_verified = True
    field.extractor_type = "human-correction"
    field.extractor_version = "1.0.0"
    case.current_version += 1
    await append_case_event(
        db,
        tenant_id=principal.tenant_id,
        case_id=case.case_id,
        event_type="DOCUMENT_FIELD_CORRECTED",
        actor_type="USER",
        actor_id=str(principal.user_id),
        payload={
            "document_id": str(document_id),
            "field_id": str(field_id),
            "field_name": field.field_name,
            "case_version": case.current_version,
        },
    )
    enqueue_event(
        db,
        tenant_id=principal.tenant_id,
        aggregate_type="document",
        aggregate_id=document_id,
        aggregate_version=case.current_version,
        event_type="document.field.corrected.v1",
        idempotency_key=scoped_key,
        payload={
            "document_id": str(document_id),
            "case_id": str(case.case_id),
            "field_id": str(field_id),
            "field_name": field.field_name,
        },
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=case.case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="DOCUMENT_FIELD_CORRECTED",
        resource_type="EXTRACTED_FIELD",
        resource_id=str(field_id),
        metadata={"field_name": field.field_name, "reason": body.reason},
    )
    return field
