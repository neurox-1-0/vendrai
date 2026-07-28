import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.models import AlertInstance, AlertRule
from app.schemas import (
    AlertInstanceResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
)
from app.services.alerts import (
    ensure_default_alert_rules,
    evaluate_alerts_for_tenant,
)
from app.services.events import append_audit

router = APIRouter(tags=["alerts"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=160)
]
ALERT_ROLES = (
    "analyst",
    "approver",
    "procurement_approver",
    "compliance_approver",
    "finance_approver",
    "auditor",
    "admin",
)


@router.get("/alert-rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(db: Db, principal: CurrentPrincipal):
    principal.require_any(*ALERT_ROLES)
    await ensure_default_alert_rules(db, principal.tenant_id)
    return list(
        (
            await db.execute(
                select(AlertRule)
                .where(AlertRule.tenant_id == principal.tenant_id)
                .order_by(AlertRule.rule_key)
            )
        ).scalars()
    )


@router.post("/alert-rules", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    body: AlertRuleCreate,
    db: Db,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
):
    principal.require_any("admin")
    rule = AlertRule(tenant_id=principal.tenant_id, **body.model_dump())
    db.add(rule)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, detail={"code": "ALERT_RULE_EXISTS"}) from exc
    return rule


@router.patch(
    "/alert-rules/{alert_rule_id}", response_model=AlertRuleResponse
)
async def update_alert_rule(
    alert_rule_id: uuid.UUID,
    body: AlertRuleUpdate,
    db: Db,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
):
    principal.require_any("admin")
    rule = await db.scalar(
        select(AlertRule)
        .where(
            AlertRule.alert_rule_id == alert_rule_id,
            AlertRule.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if not rule:
        raise HTTPException(404, detail={"code": "ALERT_RULE_NOT_FOUND"})
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    rule.version += 1
    return rule


@router.get("/alerts", response_model=list[AlertInstanceResponse])
async def list_alerts(db: Db, principal: CurrentPrincipal):
    principal.require_any(*ALERT_ROLES)
    return list(
        (
            await db.execute(
                select(AlertInstance)
                .where(AlertInstance.tenant_id == principal.tenant_id)
                .order_by(AlertInstance.created_at.desc())
                .limit(200)
            )
        ).scalars()
    )


@router.post("/alerts:evaluate", response_model=list[AlertInstanceResponse])
async def evaluate_alerts(
    db: Db,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
):
    principal.require_any("admin")
    return await evaluate_alerts_for_tenant(
        db, tenant_id=principal.tenant_id
    )


@router.post(
    "/alerts/{alert_instance_id}:acknowledge",
    response_model=AlertInstanceResponse,
)
async def acknowledge_alert(
    alert_instance_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
):
    principal.require_any(
        "analyst", "finance_approver", "compliance_approver", "admin"
    )
    alert = await db.scalar(
        select(AlertInstance)
        .where(
            AlertInstance.alert_instance_id == alert_instance_id,
            AlertInstance.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if not alert:
        raise HTTPException(404, detail={"code": "ALERT_NOT_FOUND"})
    if alert.status == "OPEN":
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_by = principal.user_id
        alert.acknowledged_at = datetime.now(UTC)
        await append_audit(
            db,
            tenant_id=principal.tenant_id,
            case_id=alert.case_id,
            actor_type="USER",
            actor_id=str(principal.user_id),
            action="ALERT_ACKNOWLEDGED",
            resource_type="ALERT",
            resource_id=str(alert.alert_instance_id),
            metadata={"severity": alert.severity},
        )
    return alert
