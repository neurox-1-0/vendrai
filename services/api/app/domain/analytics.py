from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean, median
from typing import Any, Iterable

HUMAN_TOUCH_EVENTS = frozenset(
    {
        "DOCUMENT_FIELD_CORRECTED",
        "CLARIFICATION_ANSWERED",
        "CLARIFICATION_REQUESTED",
        "APPROVAL_REQUIRED",
        "APPROVAL_DECIDED",
        "CASE_CLAIMED",
    }
)

METRIC_DEFINITIONS = {
    "invoice_stp_rate": (
        "Completed invoice cases with no human correction, clarification, "
        "review, approval, or claim after submission, divided by submitted "
        "non-cancelled invoice cases."
    ),
    "invoice_cycle_hours": (
        "Elapsed hours from invoice submission to ERP provider confirmation "
        "for completed invoice cases."
    ),
    "vendor_onboarding_cycle_hours": (
        "Elapsed hours from vendor onboarding submission to ERP provider "
        "confirmation."
    ),
    "vendor_activation_rate": (
        "ERP-confirmed vendor onboarding cases divided by submitted cases "
        "whose 48-hour SLA observation window has elapsed."
    ),
    "invoice_exception_rate": (
        "Submitted invoices with one or more persisted exceptions divided by "
        "submitted non-cancelled invoices."
    ),
    "pending_approval_count": "Distinct approval tasks whose status is OPEN.",
}


@dataclass(frozen=True)
class CaseMetricRecord:
    case_id: str
    case_type: str
    status: str
    submitted_at: datetime | None
    terminal_at: datetime | None
    human_touched: bool
    has_exception: bool


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def elapsed_hours(record: CaseMetricRecord) -> float | None:
    if not record.submitted_at or not record.terminal_at:
        return None
    return max(
        0.0,
        (record.terminal_at - record.submitted_at).total_seconds() / 3600,
    )


def summarize_metrics(
    records: Iterable[CaseMetricRecord],
    *,
    open_approvals: int,
    period_end: datetime,
) -> dict[str, dict[str, Any]]:
    items = list(records)
    invoices = [
        item
        for item in items
        if item.case_type == "INVOICE_EXCEPTION"
        and item.status != "CANCELLED"
        and item.submitted_at
    ]
    vendors = [
        item
        for item in items
        if item.case_type == "VENDOR_ONBOARDING"
        and item.status != "CANCELLED"
        and item.submitted_at
    ]
    completed_invoices = [
        item
        for item in invoices
        if item.status == "COMPLETED" and item.terminal_at
    ]
    stp = [item for item in completed_invoices if not item.human_touched]
    invoice_hours = [
        value
        for item in completed_invoices
        if (value := elapsed_hours(item)) is not None
    ]
    completed_vendors = [
        item
        for item in vendors
        if item.status == "COMPLETED" and item.terminal_at
    ]
    vendor_hours = [
        value
        for item in completed_vendors
        if (value := elapsed_hours(item)) is not None
    ]
    matured_vendors = [
        item
        for item in vendors
        if item.submitted_at
        and item.submitted_at <= period_end - timedelta(hours=48)
    ]
    matured_activated = [
        item for item in matured_vendors if item.status == "COMPLETED"
    ]
    exception_invoices = [item for item in invoices if item.has_exception]

    def rate(numerator: int, denominator: int) -> float | None:
        return (
            round(numerator / denominator * 100, 2) if denominator else None
        )

    return {
        "invoice_stp_rate": {
            "value": rate(len(stp), len(invoices)),
            "numerator": len(stp),
            "denominator": len(invoices),
            "statistics": {},
        },
        "invoice_cycle_hours": {
            "value": round(mean(invoice_hours), 2) if invoice_hours else None,
            "numerator": len(invoice_hours),
            "denominator": len(invoices),
            "statistics": {
                "median": (
                    round(median(invoice_hours), 2) if invoice_hours else None
                ),
                "p90": (
                    round(percentile(invoice_hours, 0.9) or 0, 2)
                    if invoice_hours
                    else None
                ),
            },
        },
        "vendor_onboarding_cycle_hours": {
            "value": round(mean(vendor_hours), 2) if vendor_hours else None,
            "numerator": len(vendor_hours),
            "denominator": len(vendors),
            "statistics": {
                "median": (
                    round(median(vendor_hours), 2) if vendor_hours else None
                ),
                "p90": (
                    round(percentile(vendor_hours, 0.9) or 0, 2)
                    if vendor_hours
                    else None
                ),
            },
        },
        "vendor_activation_rate": {
            "value": rate(len(matured_activated), len(matured_vendors)),
            "numerator": len(matured_activated),
            "denominator": len(matured_vendors),
            "statistics": {},
        },
        "invoice_exception_rate": {
            "value": rate(len(exception_invoices), len(invoices)),
            "numerator": len(exception_invoices),
            "denominator": len(invoices),
            "statistics": {},
        },
        "pending_approval_count": {
            "value": float(open_approvals),
            "numerator": open_approvals,
            "denominator": None,
            "statistics": {},
        },
    }


def approval_aging(
    created_times: Iterable[datetime], now: datetime | None = None
) -> dict[str, int]:
    reference = now or datetime.now(UTC)
    buckets: defaultdict[str, int] = defaultdict(int)
    for created_at in created_times:
        hours = max(0, (reference - created_at).total_seconds() / 3600)
        if hours < 24:
            buckets["lt_24h"] += 1
        elif hours < 48:
            buckets["24_48h"] += 1
        elif hours < 168:
            buckets["2_7d"] += 1
        else:
            buckets["gt_7d"] += 1
    return {
        key: buckets[key]
        for key in ("lt_24h", "24_48h", "2_7d", "gt_7d")
    }
