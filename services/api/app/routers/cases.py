from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.database import get_db
from app.models import Case, Tenant, User, CaseStatus
from app.schemas import CaseCreate, CaseResponse

router = APIRouter(prefix="/cases", tags=["cases"])

# STUB AUTHENTICATION
# In a real scenario, this comes from Keycloak JWT
async def get_current_user_stub(db: AsyncSession = Depends(get_db)):
    # Create or get a stub tenant and user to satisfy FK constraints
    tenant_result = await db.execute(select(Tenant).limit(1))
    tenant = tenant_result.scalar_one_or_none()
    
    if not tenant:
        tenant = Tenant(name="Default Tenant", slug="default")
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        
    user_result = await db.execute(select(User).limit(1))
    user = user_result.scalar_one_or_none()
    
    if not user:
        user = User(
            tenant_id=tenant.tenant_id,
            external_subject="stub-subject",
            email="stub@example.com",
            full_name="Stub User"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    return user

@router.post("/", response_model=CaseResponse)
async def create_case(
    case_in: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_stub)
):
    # Generate a dummy case number
    case_number = f"CAS-{str(uuid.uuid4())[:8].upper()}"
    
    new_case = Case(
        tenant_id=current_user.tenant_id,
        case_number=case_number,
        case_type=case_in.case_type,
        status=CaseStatus.DRAFT,
        requester_user_id=current_user.user_id,
        title=case_in.title,
        priority=case_in.priority
    )
    
    db.add(new_case)
    await db.commit()
    await db.refresh(new_case)
    
    return new_case

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_stub)
):
    result = await db.execute(select(Case).filter(Case.case_id == case_id, Case.tenant_id == current_user.tenant_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    return case
