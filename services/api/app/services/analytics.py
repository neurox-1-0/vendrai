from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.analytics import (
    HUMAN_TOUCH_EVENTS,
    METRIC_DEFINITIONS,
    CaseMetricRecord,
    approval_aging,
    summarize_metrics,
)
from app.models import ApprovalTask, Case, CaseEvent, InvoiceException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

METRIC_PRESENTATION = {
    "invoice_stp_rate": ("Invoice straight-through processing", "percent"),
    "invoice_cycle_hours": ("Invoice cycle time", "hours"),
    "vendor_onboarding_cycle_hours": ("Vendor onboarding cycle", "hours"),
    "vendor_activation_rate": ("Vendor activation rate", "percent"),
    "invoice_exception_rate": ("Invoice exception rate", "percent"),
    "pending_approval_count": ("Pending approvals", "count"),
}


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def metric_records(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
    case_type: str | None = None,
) -> tuple[list[CaseMetricRecord], list[datetime]]:
    filters = [
        Case.tenant_id == tenant_id,
        Case.submitted_at.is_not(None),
        Case.submitted_at >= start,
        Case.submitted_at < end,
    ]
    if case_type:
        filters.append(Case.case_type == case_type)
    cases = (await db.execute(select(Case).where(*filters))).scalars().all()
    case_ids = [item.case_id for item in cases]
    if case_ids:
        events = (
            await db.execute(
                select(CaseEvent).where(
                    CaseEvent.tenant_id == tenant_id,
                    CaseEvent.case_id.in_(case_ids),
                )
            )
        ).scalars().all()
        exception_case_ids = set(
            (
                await db.execute(
                    select(InvoiceException.case_id)
                    .where(
                        InvoiceException.tenant_id == tenant_id,
                        InvoiceException.case_id.in_(case_ids),
                    )
                    .distinct()
                )
            ).scalars()
        )
    else:
        events = []
        exception_case_ids = set()
    events_by_case: dict[uuid.UUID, list[CaseEvent]] = defaultdict(list)
    for event in events:
        events_by_case[event.case_id].append(event)
    records: list[CaseMetricRecord] = []
    for case in cases:
        case_events = events_by_case[case.case_id]
        terminal_events = [
            event
            for event in case_events
            if event.event_type == "ERP_PROVIDER_CONFIRMED"
        ]
        terminal_at = (
            min(utc(event.created_at) for event in terminal_events)
            if terminal_events
            else utc(case.resolved_at)
        )
        submitted_at = utc(case.submitted_at)
        human_touched = any(
            event.event_type in HUMAN_TOUCH_EVENTS
            and submitted_at
            and utc(event.created_at) >= submitted_at
            for event in case_events
        )
        records.append(
            CaseMetricRecord(
                case_id=str(case.case_id),
                case_type=case.case_type,
                status=case.status,
                submitted_at=submitted_at,
                terminal_at=terminal_at,
                human_touched=human_touched,
                has_exception=case.case_id in exception_case_ids,
            )
        )
    open_approvals = (
        await db.execute(
            select(ApprovalTask.created_at).where(
                ApprovalTask.tenant_id == tenant_id,
                ApprovalTask.status.in_(("OPEN", "PENDING")),
            )
        )
    ).scalars().all()
    return records, [utc(item) for item in open_approvals if utc(item)]


async def summary_data(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
    case_type: str | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    records, open_approval_times = await metric_records(
        db,
        tenant_id=tenant_id,
        start=start,
        end=end,
        case_type=case_type,
    )
    summary = summarize_metrics(
        records,
        open_approvals=len(open_approval_times),
        period_end=end,
    )
    return summary, approval_aging(open_approval_times, end)


async def metric_payloads(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
    case_type: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    current, aging = await summary_data(
        db,
        tenant_id=tenant_id,
        start=start,
        end=end,
        case_type=case_type,
    )
    duration = end - start
    previous, _ = await summary_data(
        db,
        tenant_id=tenant_id,
        start=start - duration,
        end=start,
        case_type=case_type,
    )
    payloads = []
    for key, result in current.items():
        label, unit = METRIC_PRESENTATION[key]
        payloads.append(
            {
                "key": key,
                "label": label,
                "value": result["value"],
                "unit": unit,
                "numerator": result["numerator"],
                "denominator": result["denominator"],
                "previous_value": (
                    None
                    if key == "pending_approval_count"
                    else previous[key]["value"]
                ),
                "definition": METRIC_DEFINITIONS[key],
                "statistics": result["statistics"],
            }
        )
    return payloads, aging


def metric_from_question(question: str) -> tuple[str, timedelta]:
    normalized = question.lower()
    if "stp" in normalized or "straight-through" in normalized:
        metric = "invoice_stp_rate"
    elif "exception" in normalized and (
        "rate" in normalized or "percent" in normalized
    ):
        metric = "invoice_exception_rate"
    elif "invoice" in normalized and (
        "cycle" in normalized or "time" in normalized
    ):
        metric = "invoice_cycle_hours"
    elif "onboarding" in normalized and (
        "cycle" in normalized or "time" in normalized
    ):
        metric = "vendor_onboarding_cycle_hours"
    elif "activation" in normalized:
        metric = "vendor_activation_rate"
    elif "approval" in normalized or "pending" in normalized:
        metric = "pending_approval_count"
    else:
        raise ValueError("ANALYTICS_QUESTION_UNSUPPORTED")
    if "7 day" in normalized or "week" in normalized:
        duration = timedelta(days=7)
    elif "90 day" in normalized or "quarter" in normalized:
        duration = timedelta(days=90)
    elif "year" in normalized or "12 month" in normalized:
        duration = timedelta(days=365)
    else:
        duration = timedelta(days=30)
    return metric, duration


def bucket_start(value: datetime, grain: str) -> datetime:
    value = utc(value) or datetime.now(UTC)
    start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    if grain == "week":
        start -= timedelta(days=start.weekday())
    return start
