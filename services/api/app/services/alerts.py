from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models import (
    AlertInstance,
    AlertRule,
    ApprovalTask,
    Case,
    Notification,
    RiskFinding,
)
from app.services.events import enqueue_event
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_ALERT_RULES = (
    {
        "rule_key": "INVOICE_EXCEPTION_AGING",
        "name": "Aging invoice exceptions",
        "description": "Alert when three or more invoice exceptions exceed seven days.",
        "rule_type": "EXCEPTION_AGING",
        "configuration": {"minimum_count": 3, "older_than_days": 7},
        "severity": "HIGH",
    },
    {
        "rule_key": "APPROVAL_AGING",
        "name": "Aging approvals",
        "description": "Alert when an approval remains open for more than 48 hours.",
        "rule_type": "APPROVAL_AGING",
        "configuration": {"minimum_count": 1, "older_than_hours": 48},
        "severity": "MEDIUM",
    },
    {
        "rule_key": "BANK_ACCOUNT_CHANGE",
        "name": "Bank account change",
        "description": "Alert immediately for an open bank-account change finding.",
        "rule_type": "RISK_FINDING",
        "configuration": {"finding_types": ["BANK_ACCOUNT_CHANGE"]},
        "severity": "CRITICAL",
    },
    {
        "rule_key": "DUPLICATE_ENTITY",
        "name": "Possible duplicate",
        "description": "Alert for open duplicate vendor or invoice findings.",
        "rule_type": "RISK_FINDING",
        "configuration": {
            "finding_types": ["DUPLICATE_VENDOR", "DUPLICATE_INVOICE"]
        },
        "severity": "HIGH",
    },
    {
        "rule_key": "EXTRACTION_FAILURE",
        "name": "Document extraction failure",
        "description": "Alert for repeated low-confidence extraction findings.",
        "rule_type": "RISK_FINDING",
        "configuration": {"finding_types": ["LOW_CONFIDENCE_EXTRACTION"]},
        "severity": "MEDIUM",
    },
)


async def ensure_default_alert_rules(
    db: AsyncSession, tenant_id: uuid.UUID
) -> list[AlertRule]:
    existing = {
        rule.rule_key: rule
        for rule in (
            await db.execute(
                select(AlertRule).where(AlertRule.tenant_id == tenant_id)
            )
        ).scalars()
    }
    for definition in DEFAULT_ALERT_RULES:
        if definition["rule_key"] not in existing:
            rule = AlertRule(tenant_id=tenant_id, **definition)
            db.add(rule)
            existing[rule.rule_key] = rule
    await db.flush()
    return list(existing.values())


async def _trigger(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rule: AlertRule,
    deduplication_key: str,
    title: str,
    body: str,
    metric_snapshot: dict,
    case_id: uuid.UUID | None = None,
    risk_finding_id: uuid.UUID | None = None,
) -> AlertInstance:
    existing = await db.scalar(
        select(AlertInstance).where(
            AlertInstance.tenant_id == tenant_id,
            AlertInstance.deduplication_key == deduplication_key,
        )
    )
    if existing:
        existing.last_triggered_at = datetime.now(UTC)
        existing.metric_snapshot = metric_snapshot
        return existing
    alert = AlertInstance(
        tenant_id=tenant_id,
        alert_rule_id=rule.alert_rule_id,
        case_id=case_id,
        risk_finding_id=risk_finding_id,
        deduplication_key=deduplication_key,
        title=title,
        body=body,
        severity=rule.severity,
        grouping_key=rule.rule_key,
        metric_snapshot=metric_snapshot,
    )
    db.add(alert)
    await db.flush()
    notification = Notification(
        tenant_id=tenant_id,
        user_id=None,
        case_id=case_id,
        notification_type="OPERATIONAL_ALERT",
        title=title,
        body=body,
    )
    db.add(notification)
    await db.flush()
    enqueue_event(
        db,
        tenant_id=tenant_id,
        aggregate_type="notification",
        aggregate_id=notification.notification_id,
        aggregate_version=1,
        event_type="notification.delivery.requested.v1",
        idempotency_key=f"notification.delivery:{notification.notification_id}:1",
        payload={
            "notification_id": str(notification.notification_id),
            "target_role": "finance_approver",
            "attempt": 1,
        },
    )
    return alert


async def evaluate_alerts_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
) -> list[AlertInstance]:
    reference = now or datetime.now(UTC)
    rules = await ensure_default_alert_rules(db, tenant_id)
    triggered: list[AlertInstance] = []
    active_exception_states = {
        "EXCEPTION_CLASSIFIED",
        "TOLERANCE_CHECK",
        "BLOCKED_DUPLICATE",
        "HOLD",
        "NEEDS_CLARIFICATION",
        "APPROVAL_PENDING",
    }
    for rule in rules:
        if not rule.enabled:
            continue
        config = rule.configuration or {}
        if rule.rule_type == "EXCEPTION_AGING":
            cutoff = reference - timedelta(
                days=int(config.get("older_than_days", 7))
            )
            count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Case)
                    .where(
                        Case.tenant_id == tenant_id,
                        Case.case_type == "INVOICE_EXCEPTION",
                        Case.status.in_(active_exception_states),
                        Case.submitted_at <= cutoff,
                    )
                )
                or 0
            )
            minimum = int(config.get("minimum_count", 3))
            if count >= minimum:
                triggered.append(
                    await _trigger(
                        db,
                        tenant_id=tenant_id,
                        rule=rule,
                        deduplication_key=f"{rule.rule_key}:tenant",
                        title=f"{count} invoice exceptions exceed SLA",
                        body=(
                            f"{count} invoice exceptions have remained active "
                            f"for more than {config.get('older_than_days', 7)} days."
                        ),
                        metric_snapshot={"count": count, "cutoff": cutoff.isoformat()},
                    )
                )
        elif rule.rule_type == "APPROVAL_AGING":
            cutoff = reference - timedelta(
                hours=int(config.get("older_than_hours", 48))
            )
            count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(ApprovalTask)
                    .where(
                        ApprovalTask.tenant_id == tenant_id,
                        ApprovalTask.status.in_(("OPEN", "PENDING")),
                        ApprovalTask.created_at <= cutoff,
                    )
                )
                or 0
            )
            if count >= int(config.get("minimum_count", 1)):
                triggered.append(
                    await _trigger(
                        db,
                        tenant_id=tenant_id,
                        rule=rule,
                        deduplication_key=f"{rule.rule_key}:tenant",
                        title=f"{count} approvals exceed SLA",
                        body=(
                            f"{count} approval tasks have been open for more "
                            f"than {config.get('older_than_hours', 48)} hours."
                        ),
                        metric_snapshot={"count": count, "cutoff": cutoff.isoformat()},
                    )
                )
        elif rule.rule_type == "RISK_FINDING":
            finding_types = list(config.get("finding_types", []))
            findings = (
                await db.execute(
                    select(RiskFinding).where(
                        RiskFinding.tenant_id == tenant_id,
                        RiskFinding.status == "OPEN",
                        RiskFinding.finding_type.in_(finding_types),
                    )
                )
            ).scalars()
            for finding in findings:
                triggered.append(
                    await _trigger(
                        db,
                        tenant_id=tenant_id,
                        rule=rule,
                        case_id=finding.case_id,
                        risk_finding_id=finding.risk_finding_id,
                        deduplication_key=(
                            f"{rule.rule_key}:{finding.risk_finding_id}"
                        ),
                        title=f"{finding.finding_type.replace('_', ' ').title()} detected",
                        body=(
                            f"{finding.severity} {finding.mode.lower()} finding "
                            f"requires review. ML findings do not change workflow authority."
                        ),
                        metric_snapshot={
                            "score": finding.score,
                            "threshold": finding.threshold,
                            "mode": finding.mode,
                        },
                    )
                )
    return triggered
