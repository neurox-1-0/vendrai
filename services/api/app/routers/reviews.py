import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.models import ApprovalTask
from app.routers.approvals import CONTROL_REVIEW_TASKS, decide_approval
from app.schemas import ApprovalDecisionRequest, ApprovalTaskResponse

router = APIRouter(prefix="/review-tasks", tags=["reviews"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[ApprovalTaskResponse])
async def list_review_tasks(
    db: Db,
    principal: CurrentPrincipal,
    task_status: str = "PENDING",
):
    principal.require_any(
        "analyst",
        "procurement_approver",
        "compliance_approver",
        "finance_approver",
        "auditor",
        "admin",
    )
    statement = select(ApprovalTask).where(
        ApprovalTask.tenant_id == principal.tenant_id,
        ApprovalTask.status == task_status,
        ApprovalTask.task_type.in_(CONTROL_REVIEW_TASKS),
    )
    if not principal.roles.intersection({"analyst", "auditor", "admin"}):
        statement = statement.where(
            ApprovalTask.assigned_role.in_(principal.roles)
        )
    tasks = (
        await db.execute(statement.order_by(ApprovalTask.created_at))
    ).scalars().all()
    return list(tasks)


@router.post("/{task_id}/decisions", response_model=ApprovalTaskResponse)
async def decide_review(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=160),
    ],
    if_match: Annotated[int, Header(alias="If-Match", ge=1)],
):
    return await decide_approval(
        task_id,
        body,
        db,
        principal,
        idempotency_key,
        if_match,
    )
