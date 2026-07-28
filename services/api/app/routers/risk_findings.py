import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.models import RiskFinding
from app.schemas import (
    RiskFindingDispositionRequest,
    RiskFindingResponse,
)
from app.services.events import append_audit, append_case_event

router = APIRouter(prefix="/risk-findings", tags=["risk-findings"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=160)
]
RISK_READ_ROLES = (
    "analyst",
    "approver",
    "procurement_approver",
    "compliance_approver",
    "finance_approver",
    "auditor",
    "admin",
)


@router.get("", response_model=list[RiskFindingResponse])
async def list_risk_findings(
    db: Db,
    principal: CurrentPrincipal,
    finding_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    mode: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    principal.require_any(*RISK_READ_ROLES)
    filters = [RiskFinding.tenant_id == principal.tenant_id]
    if finding_type:
        filters.append(RiskFinding.finding_type == finding_type)
    if status:
        filters.append(RiskFinding.status == status)
    if mode:
        filters.append(RiskFinding.mode == mode)
    return list(
        (
            await db.execute(
                select(RiskFinding)
                .where(*filters)
                .order_by(RiskFinding.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )


@router.post(
    "/{risk_finding_id}:disposition",
    response_model=RiskFindingResponse,
)
async def disposition_risk_finding(
    risk_finding_id: uuid.UUID,
    body: RiskFindingDispositionRequest,
    db: Db,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
):
    principal.require_any(
        "analyst",
        "procurement_approver",
        "compliance_approver",
        "finance_approver",
        "admin",
    )
    finding = await db.scalar(
        select(RiskFinding)
        .where(
            RiskFinding.risk_finding_id == risk_finding_id,
            RiskFinding.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if not finding:
        raise HTTPException(404, detail={"code": "RISK_FINDING_NOT_FOUND"})
    if finding.status == "CLOSED":
        if finding.disposition == body.disposition:
            return finding
        raise HTTPException(409, detail={"code": "RISK_FINDING_CLOSED"})
    finding.status = "CLOSED"
    finding.disposition = body.disposition
    finding.disposition_reason = body.reason
    finding.reviewed_by = principal.user_id
    finding.reviewed_at = datetime.now(UTC)
    if finding.case_id:
        await append_case_event(
            db,
            tenant_id=principal.tenant_id,
            case_id=finding.case_id,
            event_type="RISK_FINDING_DISPOSITIONED",
            actor_type="USER",
            actor_id=str(principal.user_id),
            payload={
                "risk_finding_id": str(finding.risk_finding_id),
                "disposition": body.disposition,
                "mode": finding.mode,
            },
        )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=finding.case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="RISK_FINDING_DISPOSITIONED",
        resource_type="RISK_FINDING",
        resource_id=str(finding.risk_finding_id),
        metadata={
            "disposition": body.disposition,
            "finding_type": finding.finding_type,
            "mode": finding.mode,
        },
    )
    return finding
