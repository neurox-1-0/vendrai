from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.domain.analytics import summarize_metrics
from app.models import InvoiceException
from app.schemas import (
    AnalyticsQuestionRequest,
    AnalyticsQuestionResponse,
    AnalyticsSummaryResponse,
    ExceptionAnalyticsResponse,
    ExceptionBreakdown,
    MetricQuery,
    MetricSeries,
)
from app.services.analytics import (
    METRIC_PRESENTATION,
    bucket_start,
    metric_from_question,
    metric_payloads,
    metric_records,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=160)
]
ANALYTICS_ROLES = (
    "analyst",
    "approver",
    "procurement_approver",
    "compliance_approver",
    "finance_approver",
    "auditor",
    "admin",
)


def _period(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    resolved_end = end or datetime.now(UTC)
    resolved_start = start or resolved_end - timedelta(days=30)
    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=UTC)
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=UTC)
    if resolved_start >= resolved_end or resolved_end - resolved_start > timedelta(days=366):
        raise HTTPException(422, detail={"code": "INVALID_ANALYTICS_PERIOD"})
    return resolved_start, resolved_end


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(
    db: Db,
    principal: CurrentPrincipal,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    timezone: Annotated[str, Query(min_length=1, max_length=80)] = "UTC",
    case_type: Annotated[str | None, Query()] = None,
):
    principal.require_any(*ANALYTICS_ROLES)
    period_start, period_end = _period(start, end)
    metrics, aging = await metric_payloads(
        db,
        tenant_id=principal.tenant_id,
        start=period_start,
        end=period_end,
        case_type=case_type,
    )
    return AnalyticsSummaryResponse(
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
        metrics=metrics,
        approval_aging=aging,
        generated_at=datetime.now(UTC),
    )


@router.get("/timeseries", response_model=MetricSeries)
async def analytics_timeseries(
    metric: str,
    db: Db,
    principal: CurrentPrincipal,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    grain: Annotated[str, Query(pattern="^(day|week)$")] = "week",
    case_type: Annotated[str | None, Query()] = None,
):
    principal.require_any(*ANALYTICS_ROLES)
    if metric not in METRIC_PRESENTATION:
        raise HTTPException(422, detail={"code": "UNKNOWN_METRIC"})
    if metric == "pending_approval_count":
        raise HTTPException(
            422, detail={"code": "POINT_IN_TIME_METRIC_NOT_TIMESERIES"}
        )
    period_start, period_end = _period(start, end)
    records, _open_approvals = await metric_records(
        db,
        tenant_id=principal.tenant_id,
        start=period_start,
        end=period_end,
        case_type=case_type,
    )
    grouped = defaultdict(list)
    for record in records:
        if record.submitted_at:
            grouped[bucket_start(record.submitted_at, grain)].append(record)
    cursor = bucket_start(period_start, grain)
    step = timedelta(days=1 if grain == "day" else 7)
    points = []
    while cursor < period_end:
        values = summarize_metrics(
            grouped.get(cursor, []),
            open_approvals=0,
            period_end=min(cursor + step, period_end),
        )[metric]
        points.append(
            {
                "period_start": cursor,
                "value": values["value"],
                "numerator": values["numerator"],
                "denominator": values["denominator"],
            }
        )
        cursor += step
    return MetricSeries(key=metric, grain=grain, points=points)


@router.get("/exceptions", response_model=ExceptionAnalyticsResponse)
async def analytics_exceptions(db: Db, principal: CurrentPrincipal):
    principal.require_any(*ANALYTICS_ROLES)
    rows = (
        await db.execute(
            select(
                InvoiceException.exception_type,
                InvoiceException.severity,
                func.count(InvoiceException.invoice_exception_id),
                func.sum(
                    case(
                        (InvoiceException.resolution_status == "OPEN", 1),
                        else_=0,
                    )
                ),
            )
            .where(InvoiceException.tenant_id == principal.tenant_id)
            .group_by(
                InvoiceException.exception_type,
                InvoiceException.severity,
            )
            .order_by(func.count(InvoiceException.invoice_exception_id).desc())
        )
    ).all()
    items = [
        ExceptionBreakdown(
            exception_type=row[0],
            severity=row[1],
            count=int(row[2] or 0),
            open_count=int(row[3] or 0),
        )
        for row in rows
    ]
    return ExceptionAnalyticsResponse(
        items=items,
        total=sum(item.count for item in items),
    )


@router.post("/query", response_model=AnalyticsQuestionResponse)
async def analytics_query(
    body: AnalyticsQuestionRequest,
    db: Db,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
):
    principal.require_any(*ANALYTICS_ROLES)
    try:
        metric_key, duration = metric_from_question(body.question)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "ANALYTICS_QUESTION_UNSUPPORTED"}
        ) from exc
    end = datetime.now(UTC)
    start = end - duration
    metrics, _aging = await metric_payloads(
        db,
        tenant_id=principal.tenant_id,
        start=start,
        end=end,
    )
    metric = next(item for item in metrics if item["key"] == metric_key)
    value = "unavailable" if metric["value"] is None else str(metric["value"])
    unit = "%" if metric["unit"] == "percent" else metric["unit"]
    return AnalyticsQuestionResponse(
        answer=(
            f"{metric['label']} is {value}{unit if unit == '%' else f' {unit}'} "
            f"for {start.date().isoformat()} through {end.date().isoformat()}."
        ),
        query=MetricQuery(
            metric=metric_key,
            start=start,
            end=end,
            grain="week",
        ),
        metric=metric,
        citations=[
            {
                "label": "Metric definition",
                "detail": metric["definition"],
            },
            {
                "label": "Authorized source",
                "detail": "Tenant-scoped case events and operational records",
            },
        ],
        provider="GOVERNED_LOCAL",
    )
