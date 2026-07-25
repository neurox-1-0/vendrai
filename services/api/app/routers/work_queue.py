from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.models import Case
from app.schemas import WorkQueueResponse

router = APIRouter(prefix="/work-queue", tags=["work-queue"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=WorkQueueResponse)
async def get_work_queue(
    db: Db,
    principal: CurrentPrincipal,
    case_status: Annotated[str | None, Query(alias="status")] = None,
    case_type: str | None = None,
    priority: str | None = None,
    ownership: Annotated[
        str,
        Query(pattern="^(ALL|UNCLAIMED|MINE)$"),
    ] = "ALL",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    principal.require_any(
        "analyst",
        "approver",
        "procurement_approver",
        "compliance_approver",
        "finance_approver",
        "auditor",
        "admin",
    )
    filters = [Case.tenant_id == principal.tenant_id]
    if case_status:
        filters.append(Case.status == case_status)
    if case_type:
        filters.append(Case.case_type == case_type)
    if priority:
        filters.append(Case.priority == priority)
    if ownership == "UNCLAIMED":
        filters.append(Case.assigned_user_id.is_(None))
    elif ownership == "MINE":
        filters.append(Case.assigned_user_id == principal.user_id)
    total = await db.scalar(
        select(func.count()).select_from(Case).where(*filters)
    )
    cases = (
        await db.execute(
            select(Case)
            .where(*filters)
            .order_by(
                Case.priority.desc(),
                Case.submitted_at.asc().nulls_last(),
                Case.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    now = datetime.now(UTC)
    items = []
    for case in cases:
        started_at = case.submitted_at or case.created_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        base = {
            column: getattr(case, column)
            for column in (
                "case_id",
                "tenant_id",
                "case_number",
                "case_type",
                "status",
                "title",
                "priority",
                "requester_user_id",
                "assigned_user_id",
                "current_version",
                "created_at",
                "updated_at",
            )
        }
        items.append(
            {
                **base,
                "age_seconds": max(
                    0,
                    int(
                        (
                            now - started_at
                        ).total_seconds()
                    ),
                ),
                "ownership": (
                    "UNCLAIMED"
                    if case.assigned_user_id is None
                    else "MINE"
                    if case.assigned_user_id == principal.user_id
                    else "OTHER"
                ),
            }
        )
    return WorkQueueResponse(items=items, total=int(total or 0))
