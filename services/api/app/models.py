import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, JSON, Enum as SQLEnum, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.database import Base

class CaseType(str, enum.Enum):
    VENDOR_ONBOARDING = 'VENDOR_ONBOARDING'
    INVOICE_EXCEPTION = 'INVOICE_EXCEPTION'

class CaseStatus(str, enum.Enum):
    DRAFT = 'DRAFT'
    SUBMITTED = 'SUBMITTED'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    # Simplified for the stub, others exist in the DB

class Tenant(Base):
    __tablename__ = "tenants"
    tenant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, server_default="ACTIVE")

class User(Base):
    __tablename__ = "users"
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    external_subject = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="ACTIVE")

class Vendor(Base):
    __tablename__ = "vendors"
    vendor_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    legal_name = Column(Text, nullable=False)
    normalized_legal_name = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="PROPOSED")
    erp_vendor_id = Column(Text)

class Case(Base):
    __tablename__ = "cases"
    case_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    case_number = Column(Text, nullable=False)
    case_type = Column(SQLEnum(CaseType, name="case_type", create_type=False), nullable=False)
    status = Column(SQLEnum(CaseStatus, name="case_status", create_type=False), nullable=False, server_default="DRAFT")
    requester_user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.vendor_id"), nullable=True)
    title = Column(Text, nullable=False)
    priority = Column(Text, nullable=False, server_default="NORMAL")
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

class Document(Base):
    __tablename__ = "documents"
    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.case_id"), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.vendor_id"), nullable=True)
    document_type = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=False)
    sanitized_filename = Column(Text, nullable=False)
    mime_type = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(Text, nullable=False)
    processing_status = Column(Text, nullable=False, server_default="UPLOADED")
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=text("now()"))
