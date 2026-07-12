from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models import CaseType, CaseStatus

class CaseCreate(BaseModel):
    title: str = Field(..., example="New Vendor Onboarding - TechCorp")
    case_type: CaseType
    priority: Optional[str] = "NORMAL"

class CaseResponse(BaseModel):
    case_id: UUID
    tenant_id: UUID
    case_number: str
    case_type: CaseType
    status: CaseStatus
    title: str
    priority: str
    requester_user_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True

class DocumentUploadResponse(BaseModel):
    document_id: UUID
    case_id: Optional[UUID]
    original_filename: str
    size_bytes: int
    processing_status: str
    
    class Config:
        from_attributes = True
