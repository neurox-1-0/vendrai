from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid
import hashlib

from app.database import get_db
from app.models import Document, User
from app.schemas import DocumentUploadResponse
from app.routers.cases import get_current_user_stub

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    case_id: Optional[uuid.UUID] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_stub)
):
    # In a real app, we would upload to MinIO here
    # For now, we stub the upload and just write the DB record
    
    contents = await file.read()
    file_size = len(contents)
    sha256_hash = hashlib.sha256(contents).hexdigest()
    
    new_doc = Document(
        tenant_id=current_user.tenant_id,
        case_id=case_id,
        document_type="UNKNOWN",
        original_filename=file.filename or "unknown",
        sanitized_filename=f"sanitized_{file.filename}",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=file_size,
        sha256=sha256_hash,
        storage_key=f"documents/{uuid.uuid4()}",
        uploaded_by=current_user.user_id,
        processing_status="UPLOADED"
    )
    
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)
    
    return new_doc
